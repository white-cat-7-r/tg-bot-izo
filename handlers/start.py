from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from keyboards.inline import main_menu_keyboard
from database import get_or_create_user

router = Router()


@router.message(F.command("start"))
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


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
