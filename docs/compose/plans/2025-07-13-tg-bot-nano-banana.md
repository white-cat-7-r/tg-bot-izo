# TG Bot Nano Banana — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram-бот для AI-обработки фото через Nano Banana API с оплатой через ЮKassa

**Architecture:** Python 3.11+ с aiogram 3, PostgreSQL через SQLAlchemy, ЮKassa SDK для платежей. Бот: загрузка фото → выбор стиля + промпт → оплата → вызов Nano Banana API → возврат результата.

**Tech Stack:** Python 3.11, aiogram 3.4, SQLAlchemy 2.0 (async), asyncpg, ЮKassa SDK, python-dotenv, aiohttp

## Global Constraints

- Python >= 3.11
- aiogram >= 3.4
- SQLAlchemy >= 2.0 (async mode)
- Все переменные окружения — через `.env`, не хардкодить
- README — на русском, без терминов без объяснения
- Не пушить в GitHub до ручного подтверждения

---

## File Structure

```
tg-bot-nano-banana/
├── bot.py                  # Точка входа, запуск polling
├── config.py               # Загрузка .env
├── database.py             # SQLAlchemy engine, session, модели
├── models.py               # ORM-модели: User, Payment, ProcessingHistory
├── payment.py              # ЮKassa: создание платежа, проверка статуса
├── ai_processor.py         # Nano Banana API клиент
├── handlers/
│   ├── __init__.py         # Регистрация роутеров
│   ├── start.py            # /start, главное меню
│   ├── process.py          # Загрузка фото, выбор стиля, промпт
│   ├── payment.py          # Оплата: ссылка, вебхук, баланс
│   └── history.py          # История обработок, баланс
├── keyboards/
│   ├── __init__.py
│   └── inline.py           # Инлайн-кнопки стилей, подтверждения
├── utils/
│   ├── __init__.py
│   └── styles.py           # Список стилей и промптов
├── requirements.txt
├── .env.example
├── README.md
└── docker-compose.yml      # PostgreSQL + бот
```

---

### Task 1: Проект, зависимости, .env

**Covers:** [S1], [S4]

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`

**Interfaces:**
- Consumes: (none — первый таск)
- Produces: модуль `config` с объектом `settings: Settings`, доступный через `from config import settings`

- [ ] **Step 1: Создай файлы проекта**

```bash
# Создай структуру каталогов
mkdir -p handlers keyboards utils
touch handlers/__init__.py keyboards/__init__.py utils/__init__.py
```

- [ ] **Step 2: Создай requirements.txt**

```txt
aiogram==3.4.0
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
python-dotenv==1.0.0
aiohttp==3.9.1
yookassa==3.0.0
pydantic==2.5.0
pydantic-settings==2.1.0
```

- [ ] **Step 3: Создай .env.example**

```env
# Telegram Bot Token (получить у @BotFather)
BOT_TOKEN=your_bot_token_here

# Nano Banana API
NANO_BANANA_API_KEY=your_api_key_here
NANO_BANANA_API_URL=https://api.nanobanana.ai/v1

# ЮKassa
YOOKASSA_SHOP_ID=your_shop_id_here
YOOKASSA_SECRET_KEY=your_secret_key_here

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://bot_user:password@localhost:5432/nano_banana_bot

# Настройки
PRICE_PER_PROCESSING=100
WEBHOOK_URL=https://your-domain.com/webhook
```

- [ ] **Step 4: Создай config.py**

```python
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token")
    
    NANO_BANANA_API_KEY: str = Field(..., description="Nano Banana API Key")
    NANO_BANANA_API_URL: str = Field(default="https://api.nanobanana.ai/v1")
    
    YOOKASSA_SHOP_ID: str = Field(..., description="ЮKassa Shop ID")
    YOOKASSA_SECRET_KEY: str = Field(..., description="ЮKassa Secret Key")
    
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    
    PRICE_PER_PROCESSING: int = Field(default=100, description="Цена обработки в рублях")
    WEBHOOK_URL: str = Field(default="", description="URL для webhook ЮKassa")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

- [ ] **Step 5: Проверь что .env.example читается корректно**

```bash
cp .env.example .env
# Заполни тестовыми значениями вручную или через sed
python -c "from config import settings; print('Config OK:', settings.PRICE_PER_PROCESSING)"
```
Ожидаемый результат: `Config OK: 100`

- [ ] **Step 6: Commit**

```bash
git init
git add -A
git commit -m "feat: project scaffold with config and dependencies"
```

---

### Task 2: База данных, модели

**Covers:** [S1], [S3]

**Files:**
- Create: `models.py`
- Create: `database.py`

**Interfaces:**
- Consumes: `config.settings.DATABASE_URL`
- Produces: `async_session` (async generator для сессий SQLAlchemy), модели `User`, `Payment`, `ProcessingHistory`

- [ ] **Step 1: Создай models.py**

```python
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


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    history: Mapped[list["ProcessingHistory"]] = relationship(back_populates="user")


class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    yookassa_payment_id: Mapped[str] = mapped_column(String(100), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship(back_populates="payments")


class ProcessingHistory(Base):
    __tablename__ = "processing_history"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    style: Mapped[str] = mapped_column(String(50))
    prompt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_photo: Mapped[str] = mapped_column(String(500))
    result_photo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship(back_populates="history")
```

- [ ] **Step 2: Создай database.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings
from models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 3: Проверь что модели создаются**

```bash
# Временно создай .env с тестовым DATABASE_URL
python -c "
import asyncio
from database import init_db
asyncio.run(init_db())
print('Database tables created')
"
```
Ожидаемый результат: сообщение без ошибок, таблицы созданы в PostgreSQL.

- [ ] **Step 4: Commit**

```bash
git add models.py database.py
git commit -m "feat: database models and async session"
```

---

### Task 3: Хелпер стилей

**Covers:** [S2]

**Files:**
- Create: `utils/styles.py`

**Interfaces:**
- Consumes: (none)
- Produces: словарь `STYLES: dict[str, dict]` с ключами `name`, `description`, `prompt_template`

- [ ] **Step 1: Создай utils/styles.py**

```python
STYLES = {
    "anime": {
        "name": "Аниме",
        "description": "Стиль японской анимации",
        "prompt_template": "anime style, detailed, vibrant colors, {prompt}",
    },
    "cartoon": {
        "name": "Мультфильм",
        "description": "Яркий мультяшный стиль",
        "prompt_template": "cartoon style, colorful, fun, {prompt}",
    },
    "oil_painting": {
        "name": "Масляная живопись",
        "description": "Классическая картина маслом",
        "prompt_template": "oil painting, classical art, detailed brushstrokes, {prompt}",
    },
    "cyberpunk": {
        "name": "Киберпанк",
        "description": "Футуристический неоновый стиль",
        "prompt_template": "cyberpunk style, neon lights, futuristic, {prompt}",
    },
    "watercolor": {
        "name": "Акварель",
        "description": "Нежная акварельная живопись",
        "prompt_template": "watercolor painting, soft colors, artistic, {prompt}",
    },
    "pixel": {
        "name": "Пиксель-арт",
        "description": "Ретро 8-битный стиль",
        "prompt_template": "pixel art, 8-bit style, retro gaming, {prompt}",
    },
}


def get_style_prompt(style_key: str, user_prompt: str = "") -> str:
    style = STYLES.get(style_key)
    if not style:
        raise ValueError(f"Style '{style_key}' not found")
    
    prompt = style["prompt_template"].format(prompt=user_prompt or "portrait")
    return prompt


def get_styles_keyboard_text() -> str:
    lines = ["Выбери стиль обработки:\n"]
    for key, style in STYLES.items():
        lines.append(f"• {style['name']} — {style['description']}")
    return "\n".join(lines)
```

- [ ] **Step 2: Проверь импорт**

```bash
python -c "from utils.styles import STYLES, get_style_prompt; print(get_style_prompt('anime', 'girl with cat'))"
```
Ожидаемый результат: строка с промптом в стиле anime.

- [ ] **Step 3: Commit**

```bash
git add utils/styles.py
git commit -m "feat: style presets for photo processing"
```

---

### Task 4: Клиент Nano Banana API

**Covers:** [S1], [S2]

**Files:**
- Create: `ai_processor.py`

**Interfaces:**
- Consumes: `config.settings.NANO_BANANA_API_KEY`, `config.settings.NANO_BANANA_API_URL`
- Produces: `async def process_photo(photo_bytes: bytes, prompt: str) -> bytes` — возвращает байты обработанного фото

- [ ] **Step 1: Создай ai_processor.py**

```python
import aiohttp
from config import settings


async def process_photo(photo_bytes: bytes, prompt: str) -> bytes:
    """Отправить фото в Nano Banana API и получить обработанное."""
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("image", photo_bytes, filename="photo.jpg", content_type="image/jpeg")
        data.add_field("prompt", prompt)
        data.add_field("strength", "0.75")
        
        headers = {
            "Authorization": f"Bearer {settings.NANO_BANANA_API_KEY}",
        }
        
        async with session.post(
            f"{settings.NANO_BANANA_API_URL}/process",
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Nano Banana API error {resp.status}: {error_text}")
            
            result = await resp.read()
            return result
```

- [ ] **Step 2: Проверь что модуль импортируется**

```bash
python -c "from ai_processor import process_photo; print('Module OK')"
```

- [ ] **Step 3: Commit**

```bash
git add ai_processor.py
git commit -m "feat: nano banana API client"
```

---

### Task 5: ЮKassa — создание платежа

**Covers:** [S1], [S3]

**Files:**
- Create: `payment.py`

**Interfaces:**
- Consumes: `config.settings.YOOKASSA_SHOP_ID`, `config.settings.YOOKASSA_SECRET_KEY`, `config.settings.PRICE_PER_PROCESSING`
- Produces: `async def create_payment(user_id: int, amount: int) -> tuple[str, str]` — возвращает `(payment_id, confirmation_url)`, `async def check_payment(payment_id: str) -> bool`

- [ ] **Step 1: Создай payment.py**

```python
from yookassa import Configuration, Payment
from config import settings


Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


async def create_payment(user_id: int, amount: int) -> tuple[str, str]:
    """Создать платёж в ЮKassa. Возвращает (payment_id, confirmation_url)."""
    payment = Payment.create({
        "amount": {
            "value": str(amount),
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{settings.BOT_TOKEN.split(':')[0]}",
        },
        "capture": True,
        "metadata": {
            "user_id": user_id,
        },
        "description": f"Оплата обработки фото для пользователя {user_id}",
    })
    
    confirmation_url = payment.confirmation.confirmation_url
    return payment.id, confirmation_url


async def check_payment(payment_id: str) -> bool:
    """Проверить статус платежа."""
    payment = Payment.find_one(payment_id)
    return payment.status == "succeeded"
```

- [ ] **Step 2: Проверь импорт**

```bash
python -c "from payment import create_payment, check_payment; print('Payment module OK')"
```

- [ ] **Step 3: Commit**

```bash
git add payment.py
git commit -m "feat: yookassa payment integration"
```

---

### Task 6: Клавиатуры

**Covers:** [S2]

**Files:**
- Create: `keyboards/inline.py`

**Interfaces:**
- Consumes: `utils.styles.STYLES`
- Produces: функции для создания инлайн-клавиатур

- [ ] **Step 1: Создай keyboards/inline.py**

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.styles import STYLES


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Обработать фото", callback_data="process_start"),
        InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance"),
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
```

- [ ] **Step 2: Проверь импорт**

```bash
python -c "from keyboards.inline import main_menu_keyboard; print('Keyboards OK')"
```

- [ ] **Step 3: Commit**

```bash
git add keyboards/inline.py
git commit -m "feat: inline keyboards for bot interaction"
```

---

### Task 7: Хэндлер /start и главное меню

**Covers:** [S2]

**Files:**
- Create: `handlers/start.py`
- Create: `handlers/__init__.py`

**Interfaces:**
- Consumes: `database.async_session`, `models.User`, `keyboards.inline.main_menu_keyboard`
- Produces: роутер `router` для регистрации в боте

- [ ] **Step 1: Создай handlers/start.py**

```python
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from database import async_session
from models import User
from keyboards.inline import main_menu_keyboard

router = Router()


@router.message(F.command("start"))
async def cmd_start(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            )
            session.add(user)
            await session.commit()
    
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

- [ ] **Step 2: Создай handlers/__init__.py**

```python
from aiogram import Router
from handlers.start import router as start_router
from handlers.process import router as process_router
from handlers.payment import router as payment_router
from handlers.history import router as history_router


def register_handlers(main_router: Router):
    main_router.include_router(start_router)
    main_router.include_router(process_router)
    main_router.include_router(payment_router)
    main_router.include_router(history_router)
```

- [ ] **Step 3: Commit**

```bash
git add handlers/
git commit -m "feat: /start handler and main menu"
```

---

### Task 8: Хэндлер обработки фото

**Covers:** [S1], [S2]

**Files:**
- Create: `handlers/process.py`

**Interfaces:**
- Consumes: `ai_processor.process_photo`, `utils.styles.get_style_prompt`, `keyboards.inline.*`, `database.async_session`, `models.ProcessingHistory`, `models.User`
- Produces: роутер с хэндлерами загрузки фото, выбора стиля, подтверждения

- [ ] **Step 1: Создай handlers/process.py**

```python
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from database import async_session
from models import User, ProcessingHistory
from keyboards.inline import styles_keyboard, confirm_keyboard, pay_keyboard
from ai_processor import process_photo
from utils.styles import get_style_prompt, STYLES
from config import settings

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
            photo=InputFile(result_photo, filename="result.jpg"),
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
```

- [ ] **Step 2: Commit**

```bash
git add handlers/process.py
git commit -m "feat: photo processing handler with style selection"
```

---

### Task 9: Хэндлер оплаты

**Covers:** [S1], [S3]

**Files:**
- Create: `handlers/payment.py`

**Interfaces:**
- Consumes: `payment.create_payment`, `payment.check_payment`, `database.async_session`, `models.User`, `models.Payment`, `keyboards.inline.*`
- Produces: роутер с хэндлерами пополнения баланса

- [ ] **Step 1: Создай handlers/payment.py**

```python
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from sqlalchemy import select
from database import async_session
from models import User, Payment, PaymentStatus
from payment import create_payment, check_payment
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
            amount=settings.PRICE_PER_PROCESSING * 5,  # Минимум 5 обработок
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
```

- [ ] **Step 2: Commit**

```bash
git add handlers/payment.py
git commit -m "feat: payment handler with yookassa integration"
```

---

### Task 10: Хэндлер истории

**Covers:** [S2]

**Files:**
- Create: `handlers/history.py`

**Interfaces:**
- Consumes: `database.async_session`, `models.ProcessingHistory`, `utils.styles.STYLES`
- Produces: роутер с хэндлером просмотра истории

- [ ] **Step 1: Создай handlers/history.py**

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from database import async_session
from models import ProcessingHistory
from utils.styles import STYLES
from keyboards.inline import main_menu_keyboard

router = Router()


@router.callback_query(F.data == "history")
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
            "📜 История пуста.\n\nЗагрузи фото для обработки!",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()
        return
    
    lines = ["📜 Последние обработки:\n"]
    for h in history:
        style = STYLES.get(h.style, {}).get("name", h.style)
        status = "✅" if h.status == "completed" else "⏳"
        date = h.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"{status} {date} — {style}")
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add handlers/history.py
git commit -m "feat: processing history handler"
```

---

### Task 11: Точка входа bot.py

**Covers:** [S1]

**Files:**
- Create: `bot.py`

**Interfaces:**
- Consumes: `config.settings`, `database.init_db`, `handlers.register_handlers`
- Produces: запуск бота

- [ ] **Step 1: Создай bot.py**

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from config import settings
from database import init_db
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialized")
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    main_router = Router()
    register_handlers(main_router)
    dp.include_router(main_router)
    
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Проверь что бот запускается**

```bash
python bot.py
```
Ожидаемый результат: логи запуска, без ошибок (если токен валиден). Нажми Ctrl+C для остановки.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: bot entry point with polling"
```

---

### Task 12: Docker Compose

**Covers:** [S4]

**Files:**
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: `requirements.txt`, `.env`
- Produces: конфигурация для запуска PostgreSQL + бота

- [ ] **Step 1: Создай docker-compose.yml**

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: nano_banana_bot
      POSTGRES_USER: bot_user
      POSTGRES_PASSWORD: ${DB_PASSWORD:-password}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot_user -d nano_banana_bot"]
      interval: 5s
      timeout: 5s
      retries: 5

  bot:
    build: .
    command: python bot.py
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://bot_user:${DB_PASSWORD:-password}@db:5432/nano_banana_bot
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
```

- [ ] **Step 2: Создай Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml Dockerfile
git commit -m "feat: docker compose for PostgreSQL and bot"
```

---

### Task 13: README.md

**Covers:** [S4], [S5]

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: все предыдущие файлы
- Produces: пошаговая инструкция на русском для не-программиста

- [ ] **Step 1: Создай README.md**

```markdown
# 🎨 Telegram-бот для AI-обработки фото

Бот, который превращает твои фото в произведения искусства с помощью нейросетей.

## Что умеет

- Загрузить фото и выбрать стиль обработки (аниме, мультфильм, киберпанк и др.)
- Добавить своё описание к стилю
- Оплатить обработку прямо в Telegram
- Смотреть историю обработок

## Что нужно для запуска

| Параметр | Где взять | Зачем |
|----------|-----------|-------|
| **Telegram Bot Token** | Напиши [@BotFather](https://t.me/BotFather) в Telegram → `/newbot` | Идентификатор бота |
| **Nano Banana API Key** | Зарегистрируйся на сайте Nano Banana → Получи API-ключ | AI-обработка фото |
| **ЮKassa Shop ID** | Зарегистрируйся на [kassa.yandex.ru](https://kassa.yandex.ru) → Получи Shop ID | Приём платежей |
| **ЮKassa Secret Key** | Там же → Секретный ключ | Подключение к ЮKassa |
| **PostgreSQL** | Уже есть в Docker | Хранение данных |

## Пошаговая установка

### Шаг 1: Установи Docker

Docker — программа, которая запускает всё в изолированном контейнере.

1. Скачай Docker с [docker.com](https://docker.com/products/docker-desktop)
2. Установи и перезагрузи компьютер
3. Проверь: открой терминал и напиши `docker --version`

### Шаг 2: Скачай проект

```bash
git clone <ссылка-на-проект>
cd tg-bot-nano-banana
```

### Шаг 3: Настрой переменные окружения

1. Скопируй файл `.env.example` в `.env`
2. Открой `.env` в любом текстовом редакторе (Блокнот, VS Code)
3. Заполни значения:

```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
NANO_BANANA_API_KEY=nb_xxxxxxxxxxxxxxxxxxxxxxxx
NANO_BANANA_API_URL=https://api.nanobanana.ai/v1
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=live_xxxxxxxxxxxxxxxxxxxxxxxx
DATABASE_URL=postgresql+asyncpg://bot_user:password@db:5432/nano_banana_bot
PRICE_PER_PROCESSING=100
```

**⚠️ Никогда не публикуй файл `.env` — это как пароль!**

### Шаг 4: Запусти

```bash
docker compose up -d
```

Это запустит:
- PostgreSQL (базу данных) на порту 5432
- Бота, который сразу начнёт работу

### Шаг 5: Проверь

1. Открой Telegram
2. Найди своего бота по имени
3. Напиши `/start`
4. Бот должен ответить приветствием

## Настройка цен

В файле `.env` параметр `PRICE_PER_PROCESSING` — стоимость одной обработки в рублях.

## Оплата через ЮKassa

### Настройка вебхука (для авто-подтверждения платежей)

1. Зайди в личный кабинет ЮKassa
2. Раздел «Вебхуки»
3. Добавь URL: `https://твой-домен/webhook/yookassa`
4. Выбери событие: «Платёж завершён»

**Если нет домена:** бот работает в режиме ручной проверки — пользователь нажимает «Проверить оплату» после перевода.

## Частые вопросы

### Бот не отвечает на /start
- Проверь, что Docker запущен: `docker compose ps`
- Проверь логи: `docker compose logs bot`
- Убедись, что BOT_TOKEN правильный

### Ошибка при обработке фото
- Проверь, что NANO_BANANA_API_KEY правильный
- Убедись, что фото не слишком большое (< 10 МБ)
- Попробуй другой стиль

### Платёж не прошёл
- Проверь, что YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY правильные
- Убедись, что ЮKassa в тестовом режиме (для тестов) или боевом (для реальных денег)

### Как добавить новый стиль

Открой файл `utils/styles.py` и добавь новый элемент в словарь `STYLES`:

```python
"new_style": {
    "name": "Новый стиль",
    "description": "Описание стиля",
    "prompt_template": "new style, artistic, {prompt}",
},
```

## Структура проекта

```
bot.py              ← Точка входа (запуск бота)
config.py           ← Настройки из .env
database.py         ← Подключение к БД
models.py           ← Структура таблиц (пользователи, платежи)
payment.py          ← Оплата через ЮKassa
ai_processor.py     ← AI-обработка фото
handlers/           ← Логика действий бота
keyboards/          ← Кнопки в Telegram
utils/styles.py     ← Список стилей
```

## Остановка

```bash
docker compose down
```

Для полного удаления данных:
```bash
docker compose down -v
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: readme with step-by-step setup guide"
```

---

### Task 14: .gitignore и финальная проверка

**Covers:** [S1], [S4]

**Files:**
- Create: `.gitignore`

**Interfaces:**
- Consumes: (none)
- Produces: .gitignore для защиты секретов

- [ ] **Step 1: Создай .gitignore**

```gitignore
.env
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/
.idea/
.vscode/
*.db
*.sqlite3
docker-compose.override.yml
```

- [ ] **Step 2: Финальная проверка**

```bash
# Убедись что .env не в git
git status
# Не должно быть .env в списке отслеживаемых файлов

# Проверь что бот запускается
python -c "from config import settings; from database import init_db; from payment import create_payment; from ai_processor import process_photo; print('All modules OK')"
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add gitignore to protect secrets"
```
