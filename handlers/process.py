from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from database import async_session
from models import User, ProcessingHistory
from keyboards.inline import styles_keyboard, confirm_keyboard, main_menu_keyboard
from ai_processor import generate_image
from utils.styles import get_style_prompt, STYLES
from token_manager import deduct_tokens, reset_daily_tokens
from config import settings, TOKEN_COST_PER_GENERATION, Plan
import io

router = Router()


class ProcessState(StatesGroup):
    waiting_prompt = State()
    waiting_style = State()
    confirm = State()


@router.callback_query(F.data == "process_start")
async def process_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ Напиши, что хочешь получить на картинке.\n\n"
        "Например: \"кот в космосе\", \"закат над морем\", \"киберпанк город\""
    )
    await state.set_state(ProcessState.waiting_prompt)
    await callback.answer()


@router.message(ProcessState.waiting_prompt, F.text)
async def received_prompt(message: Message, state: FSMContext):
    await state.update_data(user_prompt=message.text)

    await message.answer(
        "Отлично! Теперь выбери стиль обработки:",
        reply_markup=styles_keyboard(),
    )
    await state.set_state(ProcessState.waiting_style)


@router.message(ProcessState.waiting_prompt)
async def wrong_input(message: Message):
    await message.answer("❌ Пожалуйста, напиши текстовый промпт.")


@router.callback_query(F.data.startswith("style:"), ProcessState.waiting_style)
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
        f"Стоимость: {TOKEN_COST_PER_GENERATION} токенов\n\n"
        f"Сгенерировать?",
        reply_markup=confirm_keyboard(),
    )
    await state.set_state(ProcessState.confirm)
    await callback.answer()


@router.callback_query(F.data == "confirm_yes", ProcessState.confirm)
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
                await callback.message.edit_text(
                    "❌ Ошибка списания токенов. Попробуй позже.",
                    reply_markup=main_menu_keyboard(),
                )
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

        await callback.message.answer(
            f"❌ Ошибка генерации: {str(e)}\n"
            "Токены возвращены.",
            reply_markup=main_menu_keyboard(),
        )

    await state.clear()


@router.callback_query(F.data == "confirm_no", ProcessState.confirm)
async def cancel_processing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Генерация отменена.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
