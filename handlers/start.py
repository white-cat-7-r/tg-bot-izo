from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from keyboards.inline import main_menu_keyboard
from database import get_or_create_user, async_session
from token_manager import activate_plan
from config import settings, Plan

router = Router()


@router.message(F.command("start"))
async def cmd_start(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    
    # Auto-activate unlimited for test account
    if message.from_user.id == settings.TEST_USER_ID and user.plan != Plan.UNLIMITED:
        async with async_session() as session:
            await activate_plan(session, user, Plan.UNLIMITED)
        await message.answer(
            "🧪 Тестовый аккаунт активирован: безлимитный план!",
            reply_markup=main_menu_keyboard(),
        )
        return
    
    await message.answer(
        "👋 Привет! Я бот для AI-обработки фото.\n\n"
        "Загрузи фото, выбери стиль — и я создам уникальное изображение!",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()