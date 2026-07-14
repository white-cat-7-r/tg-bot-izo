from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.inline import main_menu_keyboard

router = Router()


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    await callback.message.edit_text(
        "💰 Баланс\n\n"
        "Тарифы и оплата скоро будут доступны.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "plans")
async def show_plans(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛒 Тарифы скоро будут доступны.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()
