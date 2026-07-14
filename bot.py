import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from config import settings, TOKEN_COST_PER_GENERATION, Plan
from database import init_db, async_session, get_or_create_user
from models import User, ProcessingHistory
from keyboards.inline import main_menu_keyboard, styles_keyboard, confirm_keyboard
from ai_processor import generate_image
from utils.styles import get_style_prompt, STYLES
from token_manager import deduct_tokens, reset_daily_tokens
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProcessState(StatesGroup):
    waiting_prompt = State()
    waiting_style = State()
    confirm = State()


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # === /start ===
    @dp.message(F.command("start"))
    async def cmd_start(message: Message):
        await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await message.answer(
            "👋 Привет! Я бот для генерации изображений.\n\n"
            "Напиши что хочешь увидеть — и я создам картинку!",
            reply_markup=main_menu_keyboard(),
        )

    # === Back to menu ===
    @dp.callback_query(F.data == "back_to_menu")
    async def back_to_menu(callback: CallbackQuery):
        await callback.message.edit_text("Выбери действие:", reply_markup=main_menu_keyboard())
        await callback.answer()

    # === Balance / Plans (stubs) ===
    @dp.callback_query(F.data == "balance")
    async def show_balance(callback: CallbackQuery):
        await callback.message.edit_text(
            "💰 Баланс\n\nТарифы и оплата скоро будут доступны.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
            ]),
        )
        await callback.answer()

    @dp.callback_query(F.data == "plans")
    async def show_plans(callback: CallbackQuery):
        await callback.message.edit_text(
            "🛒 Тарифы скоро будут доступны.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
            ]),
        )
        await callback.answer()

    # === History ===
    @dp.callback_query(F.data == "history")
    async def show_history(callback: CallbackQuery):
        async with async_session() as session:
            result = await session.execute(
                select(ProcessingHistory)
                .where(ProcessingHistory.user_id == callback.from_user.id)
                .order_by(ProcessingHistory.created_at.desc())
                .limit(10)
            )
            history = result.scalars().all()

        if not history:
            await callback.message.edit_text(
                "📜 История пуста.\n\nНапиши что хочешь — и я сгенерирую картинку!",
                reply_markup=main_menu_keyboard(),
            )
            await callback.answer()
            return

        lines = ["📜 Последние генерации:\n"]
        for h in history:
            style = STYLES.get(h.style, {}).get("name", h.style)
            status = "✅" if h.status == "completed" else "⏳"
            date = h.created_at.strftime("%d.%m.%Y %H:%M")
            lines.append(f"{status} {date} — {style}")

        await callback.message.edit_text("\n".join(lines), reply_markup=main_menu_keyboard())
        await callback.answer()

    # === Process: start ===
    @dp.callback_query(F.data == "process_start")
    async def process_start(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text(
            "✏️ Напиши, что хочешь получить на картинке.\n\n"
            "Например: \"кот в космосе\", \"закат над морем\", \"киберпанк город\""
        )
        await state.set_state(ProcessState.waiting_prompt)
        await callback.answer()

    # === Process: received prompt ===
    @dp.message(ProcessState.waiting_prompt, F.text)
    async def received_prompt(message: Message, state: FSMContext):
        await state.update_data(user_prompt=message.text)
        await message.answer("Отлично! Теперь выбери стиль:", reply_markup=styles_keyboard())
        await state.set_state(ProcessState.waiting_style)

    @dp.message(ProcessState.waiting_prompt)
    async def wrong_input(message: Message):
        await message.answer("❌ Пожалуйста, напиши текстовый промпт.")

    # === Process: selected style ===
    @dp.callback_query(F.data.startswith("style:"), ProcessState.waiting_style)
    async def selected_style(callback: CallbackQuery, state: FSMContext):
        style_key = callback.data.split(":")[1]
        style = STYLES.get(style_key)
        if not style:
            await callback.answer("Неизвестный стиль", show_alert=True)
            return

        await state.update_data(style_key=style_key)
        data = await state.get_data()
        full_prompt = get_style_prompt(style_key, data.get("user_prompt", ""))

        await callback.message.edit_text(
            f"✅ Стиль: {style['name']}\n"
            f"📝 Промпт: {full_prompt}\n\n"
            f"Стоимость: {TOKEN_COST_PER_GENERATION} токенов\n\nСгенерировать?",
            reply_markup=confirm_keyboard(),
        )
        await state.set_state(ProcessState.confirm)
        await callback.answer()

    # === Process: confirm yes ===
    @dp.callback_query(F.data == "confirm_yes", ProcessState.confirm)
    async def confirm_processing(callback: CallbackQuery, state: FSMContext, bot: Bot):
        data = await state.get_data()

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()
            user = await reset_daily_tokens(session, user)

            if user.plan != Plan.UNLIMITED:
                if user.tokens < TOKEN_COST_PER_GENERATION:
                    await callback.message.edit_text(
                        f"❌ Недостаточно токенов.\n"
                        f"Токенов: {user.tokens}\n"
                        f"Нужно: {TOKEN_COST_PER_GENERATION}\n\n"
                        "Пополни баланс или купи тариф.",
                        reply_markup=main_menu_keyboard(),
                    )
                    await callback.answer()
                    return

                success = await deduct_tokens(session, user, TOKEN_COST_PER_GENERATION)
                if not success:
                    await callback.message.edit_text("❌ Ошибка списания токенов.", reply_markup=main_menu_keyboard())
                    await callback.answer()
                    return
            else:
                user.daily_tokens_used += TOKEN_COST_PER_GENERATION
                await session.commit()

        await callback.message.edit_text("⏳ Генерирую изображение... Это займёт 30-60 секунд.")
        await callback.answer()

        try:
            full_prompt = get_style_prompt(data["style_key"], data.get("user_prompt", ""))
            result_photo = await generate_image(full_prompt)

            async with async_session() as session:
                history = ProcessingHistory(
                    user_id=user.id,
                    style=data["style_key"],
                    prompt=data.get("user_prompt", ""),
                    source_photo="text_prompt",
                    result_photo="generated",
                    status="completed",
                )
                session.add(history)
                await session.commit()

            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=InputFile(io.BytesIO(result_photo), filename="result.jpg"),
                caption="✅ Готово! Вот твоё изображение.",
            )
        except Exception as e:
            if user.plan != Plan.UNLIMITED:
                async with async_session() as session:
                    result = await session.execute(
                        select(User).where(User.telegram_id == callback.from_user.id)
                    )
                    u = result.scalar_one()
                    if u.plan != Plan.UNLIMITED:
                        u.tokens += TOKEN_COST_PER_GENERATION
                        u.daily_tokens_used -= TOKEN_COST_PER_GENERATION
                        await session.commit()
            await callback.message.answer(f"❌ Ошибка: {str(e)}", reply_markup=main_menu_keyboard())

        await state.clear()

    # === Process: cancel ===
    @dp.callback_query(F.data == "confirm_no", ProcessState.confirm)
    async def cancel_processing(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.message.edit_text("❌ Генерация отменена.", reply_markup=main_menu_keyboard())
        await callback.answer()

    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
