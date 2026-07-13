from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from database import async_session
from models import User, ProcessingHistory
from keyboards.inline import styles_keyboard, confirm_keyboard, pay_keyboard
from ai_processor import process_photo
from utils.styles import get_style_prompt, STYLES
from config import settings
import io

router = Router()


class ProcessState(StatesGroup):
    waiting_photo = State()
    waiting_style = State()
    waiting_prompt = State()
    confirm = State()


@router.callback_query(F.data == "process_start")
async def process_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 Отправь мне фото для обработки.\n\n"
        "Поддерживаются форматы: JPG, PNG, WebP"
    )
    await state.set_state(ProcessState.waiting_photo)
    await callback.answer()


@router.message(ProcessState.waiting_photo, F.photo)
async def received_photo(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    photo_bytes = await bot.download_file(file.file_path)
    
    await state.update_data(photo_bytes=photo_bytes.read())
    
    await message.answer(
        "Отлично! Фото получено.\n\n"
        "Теперь выбери стиль обработки:",
        reply_markup=styles_keyboard(),
    )
    await state.set_state(ProcessState.waiting_style)


@router.message(ProcessState.waiting_photo)
async def wrong_photo(message: Message):
    await message.answer("❌ Пожалуйста, отправь именно фото (не документ, не стикер).")


@router.callback_query(F.data.startswith("style:"), ProcessState.waiting_style)
async def selected_style(callback: CallbackQuery, state: FSMContext):
    style_key = callback.data.split(":")[1]
    style = STYLES.get(style_key)
    if not style:
        await callback.answer("Неизвестный стиль", show_alert=True)
        return
    
    await state.update_data(style_key=style_key)
    
    await callback.message.edit_text(
        f"✅ Стиль: {style['name']}\n\n"
        "Теперь напиши промпт (что добавить/изменить) или нажми «Пропустить»:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="prompt_skip")],
        ]),
    )
    await state.set_state(ProcessState.waiting_prompt)
    await callback.answer()


@router.message(ProcessState.waiting_prompt, F.text)
async def received_prompt(message: Message, state: FSMContext):
    await state.update_data(user_prompt=message.text)
    data = await state.get_data()
    
    style = STYLES[data["style_key"]]
    full_prompt = get_style_prompt(data["style_key"], data.get("user_prompt", ""))
    
    await message.answer(
        f"🎨 Обработка:\n"
        f"• Стиль: {style['name']}\n"
        f"• Промпт: {full_prompt}\n"
        f"• Стоимость: {settings.PRICE_PER_PROCESSING} ₽\n\n"
        f"Подтвердить?",
        reply_markup=confirm_keyboard(),
    )
    await state.set_state(ProcessState.confirm)


@router.callback_query(F.data == "prompt_skip", ProcessState.waiting_prompt)
async def skip_prompt(callback: CallbackQuery, state: FSMContext):
    await state.update_data(user_prompt="")
    data = await state.get_data()
    
    style = STYLES[data["style_key"]]
    full_prompt = get_style_prompt(data["style_key"])
    
    await callback.message.edit_text(
        f"🎨 Обработка:\n"
        f"• Стиль: {style['name']}\n"
        f"• Промпт: {full_prompt}\n"
        f"• Стоимость: {settings.PRICE_PER_PROCESSING} ₽\n\n"
        f"Подтвердить?",
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
        
        if user.balance < settings.PRICE_PER_PROCESSING:
            await callback.message.edit_text(
                f"❌ Недостаточно средств.\n"
                f"Баланс: {user.balance} ₽\n"
                f"Нужно: {settings.PRICE_PER_PROCESSING} ₽\n\n"
                "Пополни баланс:",
                reply_markup=pay_keyboard(settings.PRICE_PER_PROCESSING),
            )
            await callback.answer()
            return
        
        user.balance -= settings.PRICE_PER_PROCESSING
        await session.commit()
    
    await callback.message.edit_text("⏳ Обрабатываю фото... Это займёт 30-60 секунд.")
    await callback.answer()
    
    try:
        full_prompt = get_style_prompt(data["style_key"], data.get("user_prompt", ""))
        result_photo = await process_photo(data["photo_bytes"], full_prompt)
        
        async with async_session() as session:
            history = ProcessingHistory(
                user_id=user.id,
                style=data["style_key"],
                prompt=data.get("user_prompt", ""),
                source_photo="uploaded",
                result_photo="processed",
                status="completed",
            )
            session.add(history)
            await session.commit()
        
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=InputFile(io.BytesIO(result_photo), filename="result.jpg"),
            caption="✅ Готово! Вот твоё обработанное фото.",
        )
    except Exception as e:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()
            user.balance += settings.PRICE_PER_PROCESSING
            await session.commit()
        
        await callback.message.answer(
            f"❌ Ошибка обработки: {str(e)}\n"
            "Средства возвращены на баланс."
        )
    
    await state.clear()


@router.callback_query(F.data == "confirm_no", ProcessState.confirm)
async def cancel_processing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Обработка отменена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()
