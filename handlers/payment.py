from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from database import async_session
from models import User, Payment
from payment import create_payment
from keyboards.inline import main_menu_keyboard, plans_keyboard, plan_confirm_keyboard
from token_manager import get_user_status, activate_plan
from config import settings, Plan, PLAN_CONFIGS

router = Router()


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one()
        status = await get_user_status(session, user)
    
    tokens_display = status["tokens"]
    plan_name = status["plan_name"]
    used = status["used_today"]
    limit = status["daily_limit"]
    
    text = (
        f"💰 {plan_name} план\n\n"
        f"🪙 Токены: {tokens_display}\n"
        f"📊 Использовано сегодня: {used} / {limit}\n"
    )
    
    if status["plan_expires"]:
        text += f"📅 Действует до: {status['plan_expires']}\n"
    
    text += "\nКупить тариф для увеличения лимита:"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить тариф", callback_data="plans")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "plans")
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


@router.callback_query(F.data.startswith("plan:"))
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
            await activate_plan(session, user, Plan.FREE)
        
        await callback.message.edit_text(
            "✅ Бесплатный тариф активирован!\n"
            "50 токенов начисляются ежедневно.",
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
        await callback.message.edit_text(
            f"{plan_names[plan]}\n\n"
            f"💰 Стоимость: {config['price']}₽/мес\n"
            f"🪙 Токенов в день: {config['daily_tokens'] or '∞'}\n\n"
            f"Купить тариф?",
            reply_markup=plan_confirm_keyboard(plan),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("plan_buy:"))
async def buy_plan(callback: CallbackQuery):
    plan_name = callback.data.split(":")[1]
    try:
        plan = Plan(plan_name)
    except ValueError:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    
    config = PLAN_CONFIGS[plan]
    price = config["price"]
    
    try:
        payment_id, confirmation_url = await create_payment(
            user_id=callback.from_user.id,
            amount=price,
        )
        
        async with async_session() as session:
            payment = Payment(
                user_id=callback.from_user.id,
                yookassa_payment_id=payment_id,
                amount=price,
            )
            session.add(payment)
            await session.commit()
        
        plan_names = {
            Plan.STANDARD: "⭐ Стандарт",
            Plan.EXTENDED: "💎 Расширенный",
            Plan.UNLIMITED: "♾️ Безлимит",
        }
        
        await callback.message.edit_text(
            f"💳 Оплата тарифа {plan_names[plan]}.\n"
            f"Сумма: {price}₽\n\n"
            "Нажми кнопку ниже для перехода к оплате:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=confirmation_url)],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="plans")],
            ]),
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка создания платежа: {str(e)}\n"
            "Попробуй позже.",
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()
