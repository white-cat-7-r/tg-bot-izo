import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from config import settings, TOKEN_COST_PER_GENERATION, Plan
from database import init_db, async_session, get_or_create_user
from models import User, ProcessingHistory
from keyboards.inline import main_menu_keyboard, styles_keyboard, confirm_keyboard, plans_keyboard
from ai_processor import generate_image
from utils.styles import get_style_prompt, STYLES
from token_manager import deduct_tokens, reset_daily_tokens, activate_plan
from config import PLAN_CONFIGS
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
    @dp.message(Command("start"))
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
    async def back_to_menu(callback: CallbackQuery, bot: Bot):
        try:
            await callback.message.edit_text("Выбери действие:", reply_markup=main_menu_keyboard())
        except Exception:
            await bot.send_message(callback.from_user.id, "Выбери действие:", reply_markup=main_menu_keyboard())
        await callback.answer()

    # === Balance ===
    @dp.callback_query(F.data == "balance")
    async def show_balance(callback: CallbackQuery):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()
            user = await reset_daily_tokens(session, user)

        plan_names = {
            Plan.FREE: "🆓 Бесплатный",
            Plan.STANDARD: "⭐ Стандарт",
            Plan.EXTENDED: "💎 Расширенный",
            Plan.UNLIMITED: "♾️ Безлимит",
        }
        config = PLAN_CONFIGS[user.plan]
        tokens_display = "∞" if user.plan == Plan.UNLIMITED else user.tokens
        limit_display = config["daily_tokens"] if config["daily_tokens"] else "∞"

        text = (
            f"💰 {plan_names[user.plan]}\n\n"
            f"🪙 Токены: {tokens_display}\n"
            f"📊 Использовано сегодня: {user.daily_tokens_used} / {limit_display}\n"
        )
        if user.plan_expires_at:
            text += f"📅 Действует до: {user.plan_expires_at.strftime('%d.%m.%Y')}\n"

        if user.plan == Plan.FREE:
            text += "\nКупи тариф для увеличения лимита:"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить тариф", callback_data="plans")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # === Plans ===
    @dp.callback_query(F.data == "plans")
    async def show_plans(callback: CallbackQuery):
        await callback.message.edit_text(
            "🛒 Выбери тариф:\n\n"
            "🆓 Бесплатный — 50 токенов/день\n"
            "⭐ Стандарт — 200 токенов/день — 500₽/мес\n"
            "💎 Расширенный — 500 токенов/день — 900₽/мес\n"
            "♾️ Безлимит — 1300₽/мес",
            reply_markup=plans_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("plan:"))
    async def select_plan(callback: CallbackQuery):
        plan_name = callback.data.split(":")[1]
        try:
            plan = Plan(plan_name)
        except ValueError:
            await callback.answer("Неизвестный тариф", show_alert=True)
            return

        config = PLAN_CONFIGS[plan]

        if plan == Plan.FREE:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
                user = result.scalar_one()
                if user.plan == Plan.FREE:
                    await callback.message.edit_text(
                        "ℹ️ Это уже ваш текущий тариф.\n50 токенов начисляются ежедневно.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
                        ]),
                    )
                else:
                    await activate_plan(session, user, Plan.FREE)
                    await callback.message.edit_text(
                        "✅ Бесплатный тариф активирован!\n50 токенов начисляются ежедневно.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
                        ]),
                    )
        else:
            plan_names = {
                Plan.STANDARD: "⭐ Стандарт",
                Plan.EXTENDED: "💎 Расширенный",
                Plan.UNLIMITED: "♾️ Безлимит",
            }
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"💳 Купить за {config['price']}₽",
                    callback_data=f"plan_buy:{plan.value}",
                )],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="plans")],
            ])
            await callback.message.edit_text(
                f"{plan_names[plan]}\n\n"
                f"💰 Стоимость: {config['price']}₽/мес\n"
                f"🪙 Токенов в день: {config['daily_tokens'] or '∞'}\n\n"
                f"Купить тариф?",
                reply_markup=kb,
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("plan_buy:"))
    async def buy_plan(callback: CallbackQuery):
        plan_name = callback.data.split(":")[1]
        try:
            plan = Plan(plan_name)
        except ValueError:
            await callback.answer("Неизвестный тариф", show_alert=True)
            return

        config = PLAN_CONFIGS[plan]

        try:
            from payment import create_payment
            payment_id, confirmation_url = await create_payment(
                user_id=callback.from_user.id,
                amount=config["price"],
            )

            async with async_session() as session:
                from models import Payment
                payment = Payment(
                    user_id=callback.from_user.id,
                    yookassa_payment_id=payment_id,
                    amount=config["price"],
                )
                session.add(payment)
                await session.commit()

            plan_names = {
                Plan.STANDARD: "⭐ Стандарт",
                Plan.EXTENDED: "💎 Расширенный",
                Plan.UNLIMITED: "♾️ Безлимит",
            }

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=confirmation_url)],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="plans")],
            ])
            await callback.message.edit_text(
                f"💳 Оплата тарифа {plan_names[plan]}.\n"
                f"Сумма: {config['price']}₽\n\n"
                "Нажми кнопку ниже для перехода к оплате:",
                reply_markup=kb,
            )
        except Exception as e:
            await callback.message.edit_text(
                f"❌ Ошибка: {str(e)}\n"
                "Попробуй позже.",
                reply_markup=main_menu_keyboard(),
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
    async def process_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
        try:
            await callback.message.edit_text(
                "✏️ Напиши, что хочешь получить на картинке.\n\n"
                "Например: \"кот в космосе\", \"закат над морем\", \"киберпанк город\""
            )
        except Exception:
            await bot.send_message(
                callback.from_user.id,
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

            # Показать остаток токенов
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
                fresh_user = result.scalar_one()
                tokens_left = "∞" if fresh_user.plan == Plan.UNLIMITED else fresh_user.tokens

            after_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎨 Ещё картинку", callback_data="process_start")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")],
            ])

            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=BufferedInputFile(result_photo, filename="result.jpg"),
                caption=f"✅ Готово! Вот твоё изображение.\n\n🪙 Остаток токенов: {tokens_left}",
                reply_markup=after_keyboard,
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
