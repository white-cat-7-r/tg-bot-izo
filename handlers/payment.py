from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from database import async_session
from models import User, Payment
from payment import create_payment
from keyboards.inline import main_menu_keyboard
from config import settings

router = Router()


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one()
    
    await callback.message.edit_text(
        f"💰 Твой баланс: {user.balance} ₽\n\n"
        f"Стоимость одной обработки: {settings.PRICE_PER_PROCESSING} ₽",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="topup")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "topup")
async def start_topup(callback: CallbackQuery):
    try:
        payment_id, confirmation_url = await create_payment(
            user_id=callback.from_user.id,
            amount=settings.PRICE_PER_PROCESSING * 5,
        )
        
        async with async_session() as session:
            payment = Payment(
                user_id=callback.from_user.id,
                yookassa_payment_id=payment_id,
                amount=settings.PRICE_PER_PROCESSING * 5,
            )
            session.add(payment)
            await session.commit()
        
        await callback.message.edit_text(
            "💳 Оплата через ЮKassa.\n\n"
            "Нажми кнопку ниже для перехода к оплате:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=confirmation_url)],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
            ]),
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка создания платежа: {str(e)}\n"
            "Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()
