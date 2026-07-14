from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.styles import STYLES


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Создать картинку", callback_data="process_start"),
        InlineKeyboardButton(text="🪙 Мой баланс", callback_data="balance"),
    )
    builder.row(
        InlineKeyboardButton(text="📜 История", callback_data="history"),
    )
    return builder.as_markup()


def styles_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, style in STYLES.items():
        builder.row(InlineKeyboardButton(
            text=f"{style['name']} — {style['description']}",
            callback_data=f"style:{key}",
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, обработать", callback_data="confirm_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_no"),
    )
    return builder.as_markup()


def pay_keyboard(amount: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"💳 Оплатить {amount} ₽",
        callback_data="pay",
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
    return builder.as_markup()


from config import Plan, PLAN_CONFIGS


def plans_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🆓 Бесплатный — 50 токенов/день",
        callback_data="plan:free",
    ))
    builder.row(InlineKeyboardButton(
        text="⭐ Стандарт — 200 токенов/день — 500₽",
        callback_data="plan:standard",
    ))
    builder.row(InlineKeyboardButton(
        text="💎 Расширенный — 500 токенов/день — 900₽",
        callback_data="plan:extended",
    ))
    builder.row(InlineKeyboardButton(
        text="♾️ Безлимит — 1300₽/мес",
        callback_data="plan:unlimited",
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
    return builder.as_markup()


def plan_confirm_keyboard(plan: Plan) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    price = PLAN_CONFIGS[plan]["price"]
    builder.row(InlineKeyboardButton(
        text=f"💳 Купить за {price}₽",
        callback_data=f"plan_buy:{plan.value}",
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="plans"))
    return builder.as_markup()