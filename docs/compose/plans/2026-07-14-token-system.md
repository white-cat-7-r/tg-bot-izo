# Token System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the direct ruble balance system with an internal token currency, add daily free tokens, paid subscription plans, and a test account.

**Architecture:** Extend the existing `users` table with token fields and plan type. Add a token manager module for daily reset logic. Update payment handlers to support plan purchases. Update process handlers to deduct tokens instead of rubles.

**Tech Stack:** Python 3.11, aiogram 3.4, SQLAlchemy 2.0 async, PostgreSQL 16, YooKassa

## Global Constraints

- 1 token = 5₽
- Free tier: 50 tokens/day (10 generations at 5 tokens each)
- Standard plan: 200 tokens/day (40 generations), 500₽/month
- Extended plan: 500 tokens/day (100 generations), 900₽/month
- Unlimited plan: ∞ tokens, 1300₽/month
- Tokens reset daily at midnight (Moscow time)
- Test account: `TEST_USER_ID` env var → automatic unlimited plan

---

### Task 1: Update Database Models

**Covers:** Token fields, plan type, daily tracking

**Files:**
- Modify: `models.py`
- Modify: `config.py`

**Interfaces:**
- Produces: `User.tokens`, `User.plan`, `User.plan_expires_at`, `User.daily_tokens_used`, `User.last_reset_at`
- Produces: `Plan` enum, `TOKEN_COST_PER_GENERATION`, `PLAN_CONFIGS`

- [ ] **Step 1: Add Plan enum and constants to config.py**

```python
# config.py - add after Settings class

TOKEN_COST_PER_GENERATION = 5

class Plan(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    EXTENDED = "extended"
    UNLIMITED = "unlimited"

PLAN_CONFIGS = {
    Plan.FREE: {"daily_tokens": 50, "price": 0},
    Plan.STANDARD: {"daily_tokens": 200, "price": 500},
    Plan.EXTENDED: {"daily_tokens": 500, "price": 900},
    Plan.UNLIMITED: {"daily_tokens": None, "price": 1300},
}
```

- [ ] **Step 2: Update User model in models.py**

```python
# models.py - User class

from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class Plan(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    EXTENDED = "extended"
    UNLIMITED = "unlimited"


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)  # Keep for backward compat
    tokens: Mapped[int] = mapped_column(Integer, default=50)
    plan: Mapped[Plan] = mapped_column(SAEnum(Plan), default=Plan.FREE)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    daily_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    history: Mapped[list["ProcessingHistory"]] = relationship(back_populates="user")
```

- [ ] **Step 3: Run migration**

```bash
# Since we use create_all, columns will be added on next restart
# For production, use alembic migration
python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
```

- [ ] **Step 4: Commit**

```bash
git add models.py config.py
git commit -m "feat: add token system fields to User model"
```

---

### Task 2: Create Token Manager Module

**Covers:** Daily reset logic, token operations, plan management

**Files:**
- Create: `token_manager.py`

**Interfaces:**
- Consumes: `User` model, `Plan` enum, `PLAN_CONFIGS`
- Produces: `reset_daily_tokens()`, `deduct_tokens()`, `activate_plan()`, `get_user_status()`

- [ ] **Step 1: Create token_manager.py**

```python
# token_manager.py

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import User, Plan
from config import PLAN_CONFIGS, TOKEN_COST_PER_GENERATION

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


async def reset_daily_tokens(session: AsyncSession, user: User) -> User:
    """Reset daily token allocation if it's a new day."""
    now = datetime.now(MOSCOW_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if user.last_reset_at is None or user.last_reset_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) < today_start:
        # Check if plan expired
        if user.plan != Plan.FREE and user.plan_expires_at:
            if user.plan_expires_at < now:
                user.plan = Plan.FREE
                user.plan_expires_at = None
        
        config = PLAN_CONFIGS[user.plan]
        user.tokens = config["daily_tokens"] if config["daily_tokens"] is not None else 999999
        user.daily_tokens_used = 0
        user.last_reset_at = now
        await session.commit()
    
    return user


async def deduct_tokens(session: AsyncSession, user: User, amount: int = TOKEN_COST_PER_GENERATION) -> bool:
    """Deduct tokens from user. Returns True if successful."""
    if user.plan == Plan.UNLIMITED:
        user.daily_tokens_used += amount
        await session.commit()
        return True
    
    if user.tokens < amount:
        return False
    
    user.tokens -= amount
    user.daily_tokens_used += amount
    await session.commit()
    return True


async def activate_plan(session: AsyncSession, user: User, plan: Plan) -> None:
    """Activate a subscription plan."""
    user.plan = plan
    if plan != Plan.FREE:
        user.plan_expires_at = datetime.now(MOSCOW_TZ) + timedelta(days=30)
    config = PLAN_CONFIGS[plan]
    user.tokens = config["daily_tokens"] if config["daily_tokens"] is not None else 999999
    user.daily_tokens_used = 0
    user.last_reset_at = datetime.now(MOSCOW_TZ)
    await session.commit()


async def get_user_status(session: AsyncSession, user: User) -> dict:
    """Get formatted user status for display."""
    user = await reset_daily_tokens(session, user)
    config = PLAN_CONFIGS[user.plan]
    
    return {
        "plan": user.plan.value,
        "plan_name": {
            Plan.FREE: "Бесплатный",
            Plan.STANDARD: "Стандарт",
            Plan.EXTENDED: "Расширенный",
            Plan.UNLIMITED: "Безлимит",
        }[user.plan],
        "tokens": user.tokens if user.plan != Plan.UNLIMITED else "∞",
        "daily_limit": config["daily_tokens"] if config["daily_tokens"] else "∞",
        "used_today": user.daily_tokens_used,
        "plan_expires": user.plan_expires_at.strftime("%d.%m.%Y") if user.plan_expires_at else None,
        "price": config["price"],
    }
```

- [ ] **Step 2: Commit**

```bash
git add token_manager.py
git commit -m "feat: add token manager module"
```

---

### Task 3: Update Config and Environment

**Covers:** Configuration, test account support

**Files:**
- Modify: `config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `settings.TEST_USER_ID`, `TOKEN_COST_PER_GENERATION`

- [ ] **Step 1: Update config.py**

```python
# config.py

from pydantic_settings import BaseSettings
from pydantic import Field
import enum


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token")
    
    NANO_BANANA_API_KEY: str = Field(..., description="Nano Banana API Key")
    NANO_BANANA_API_URL: str = Field(default="https://api.nanobanana.ai/v1")
    
    YOOKASSA_SHOP_ID: str = Field(..., description="ЮKassa Shop ID")
    YOOKASSA_SECRET_KEY: str = Field(..., description="ЮKassa Secret Key")
    
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    
    PRICE_PER_PROCESSING: int = Field(default=100, description="Цена обработки в рублях (legacy)")
    WEBHOOK_URL: str = Field(default="", description="URL для webhook ЮKassa")
    
    TEST_USER_ID: int = Field(default=0, description="Telegram ID тестового аккаунта с безлимитом")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


class Plan(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    EXTENDED = "extended"
    UNLIMITED = "unlimited"


TOKEN_COST_PER_GENERATION = 5

PLAN_CONFIGS = {
    Plan.FREE: {"daily_tokens": 50, "price": 0},
    Plan.STANDARD: {"daily_tokens": 200, "price": 500},
    Plan.EXTENDED: {"daily_tokens": 500, "price": 900},
    Plan.UNLIMITED: {"daily_tokens": None, "price": 1300},
}
```

- [ ] **Step 2: Update .env.example**

```
BOT_TOKEN=your_bot_token_here
NANO_BANANA_API_KEY=your_api_key_here
NANO_BANANA_API_URL=https://api.nanobanana.ai/v1
YOOKASSA_SHOP_ID=your_shop_id_here
YOOKASSA_SECRET_KEY=your_secret_key_here
DATABASE_URL=postgresql+asyncpg://bot_user:password@localhost:5432/nano_banana_bot
PRICE_PER_PROCESSING=100
WEBHOOK_URL=https://your-domain.com/webhook
TEST_USER_ID=0
```

- [ ] **Step 3: Commit**

```bash
git add config.py .env.example
git commit -m "feat: add token system config and test user support"
```

---

### Task 4: Update Payment Handler for Plans

**Covers:** Plan purchase flow, balance display with tokens

**Files:**
- Modify: `handlers/payment.py`
- Modify: `keyboards/inline.py`

**Interfaces:**
- Consumes: `token_manager.get_user_status()`, `token_manager.activate_plan()`
- Produces: `buy_plan_keyboard()`, plan selection handlers

- [ ] **Step 1: Add plan keyboard to keyboards/inline.py**

```python
# keyboards/inline.py - add at end

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
```

- [ ] **Step 2: Update handlers/payment.py**

```python
# handlers/payment.py

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
```

- [ ] **Step 3: Commit**

```bash
git add handlers/payment.py keyboards/inline.py
git commit -m "feat: add plan purchase flow and token balance display"
```

---

### Task 5: Update Process Handler for Tokens

**Covers:** Token deduction, test account, error handling

**Files:**
- Modify: `handlers/process.py`

**Interfaces:**
- Consumes: `token_manager.deduct_tokens()`, `token_manager.reset_daily_tokens()`
- Produces: Token-based processing flow

- [ ] **Step 1: Update handlers/process.py**

```python
# handlers/process.py

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
from token_manager import deduct_tokens, reset_daily_tokens
from config import settings, TOKEN_COST_PER_GENERATION, Plan
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
        f"• Стоимость: {TOKEN_COST_PER_GENERATION} токенов\n\n"
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
        f"• Стоимость: {TOKEN_COST_PER_GENERATION} токенов\n\n"
        f"Подтвердить?",
        reply_markup=confirm_keyboard(),
    )
    await state.set_state(ProcessState.confirm)
    await callback.answer()


@router.callback_query(F.data == "confirm_yes", ProcessState.confirm)
async def confirm_processing(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    # Check test account first
    if callback.from_user.id == settings.TEST_USER_ID:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()
            # Ensure unlimited plan for test user
            if user.plan != Plan.UNLIMITED:
                from token_manager import activate_plan
                await activate_plan(session, user, Plan.UNLIMITED)
    else:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )
            user = result.scalar_one()
            
            # Reset daily tokens if needed
            user = await reset_daily_tokens(session, user)
            
            # Check if unlimited
            if user.plan != Plan.UNLIMITED:
                # Check if user has enough tokens
                if user.tokens < TOKEN_COST_PER_GENERATION:
                    await callback.message.edit_text(
                        f"❌ Недостаточно токенов.\n"
                        f"Токенов: {user.tokens}\n"
                        f"Нужно: {TOKEN_COST_PER_GENERATION}\n\n"
                        "Пополни баланс или купи тариф:",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🛒 Купить тариф", callback_data="plans")],
                            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
                        ]),
                    )
                    await callback.answer()
                    return
                
                # Deduct tokens
                success = await deduct_tokens(session, user, TOKEN_COST_PER_GENERATION)
                if not success:
                    await callback.message.edit_text(
                        "❌ Ошибка списания токенов. Попробуй позже.",
                        reply_markup=main_menu_keyboard(),
                    )
                    await callback.answer()
                    return
            else:
                # Unlimited - just track usage
                user.daily_tokens_used += TOKEN_COST_PER_GENERATION
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
        # Refund tokens on error (not for unlimited)
        if callback.from_user.id != settings.TEST_USER_ID:
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == callback.from_user.id)
                )
                user = result.scalar_one()
                if user.plan != Plan.UNLIMITED:
                    user.tokens += TOKEN_COST_PER_GENERATION
                    user.daily_tokens_used -= TOKEN_COST_PER_GENERATION
                    await session.commit()
        
        await callback.message.answer(
            f"❌ Ошибка обработки: {str(e)}\n"
            "Токены возвращены."
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
```

- [ ] **Step 2: Commit**

```bash
git add handlers/process.py
git commit -m "feat: replace ruble balance with token deduction in processing"
```

---

### Task 6: Update Start Handler for Test Account

**Covers:** Auto-activate unlimited plan for test user

**Files:**
- Modify: `handlers/start.py`

**Interfaces:**
- Consumes: `token_manager.activate_plan()`
- Produces: Auto-activation on /start

- [ ] **Step 1: Update handlers/start.py**

```python
# handlers/start.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from keyboards.inline import main_menu_keyboard
from database import get_or_create_user
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
```

- [ ] **Step 2: Commit**

```bash
git add handlers/start.py
git commit -m "feat: auto-activate unlimited plan for test account"
```

---

### Task 7: Update Main Menu Keyboard

**Covers:** UI update for token display

**Files:**
- Modify: `keyboards/inline.py`

**Interfaces:**
- Consumes: `token_manager.get_user_status()`

- [ ] **Step 1: Update main_menu_keyboard to show tokens**

```python
# keyboards/inline.py - update main_menu_keyboard

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.styles import STYLES
from config import Plan, PLAN_CONFIGS


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Обработать фото", callback_data="process_start"),
        InlineKeyboardButton(text="🪙 Мой баланс", callback_data="balance"),
    )
    builder.row(
        InlineKeyboardButton(text="📜 История", callback_data="history"),
    )
    return builder.as_markup()
```

- [ ] **Step 2: Commit**

```bash
git add keyboards/inline.py
git commit -m "feat: update main menu button text for tokens"
```

---

### Task 8: Test and Verify

**Covers:** End-to-end testing

**Files:**
- Test all handlers manually or with pytest

- [ ] **Step 1: Test database migration**

```bash
python -c "from database import init_db; import asyncio; asyncio.run(init_db())"
```

- [ ] **Step 2: Test token manager**

```bash
python -c "
from token_manager import reset_daily_tokens, deduct_tokens, activate_plan, get_user_status
from models import User, Plan
print('Token manager imports OK')
"
```

- [ ] **Step 3: Test bot starts without errors**

```bash
python -c "from bot import main; print('Bot imports OK')"
```

- [ ] **Step 4: Manual test in Telegram**

1. Start bot → verify free tier shows 50 tokens
2. Process photo → verify 5 tokens deducted
3. Buy standard plan → verify 200 tokens/day
4. Test unlimited plan → verify no token deduction
5. Test TEST_USER_ID → verify auto-activation

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete token system implementation"
```
