# Telegram-бот для AI-обработки фото

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

**Никогда не публикуй файл `.env` — это как пароль!**

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
bot.py              <- Точка входа (запуск бота)
config.py           <- Настройки из .env
database.py         <- Подключение к БД
models.py           <- Структура таблиц (пользователи, платежи)
payment.py          <- Оплата через ЮKassa
ai_processor.py     <- AI-обработка фото
handlers/           <- Логика действий бота
keyboards/          <- Кнопки в Telegram
utils/styles.py     <- Список стилей
```

## Остановка

```bash
docker compose down
```

Для полного удаления данных:
```bash
docker compose down -v
```
