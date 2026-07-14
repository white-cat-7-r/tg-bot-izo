import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import settings
from database import init_db
from handlers.start import router as start_router
from handlers.process import router as process_router
from handlers.payment import router as payment_router
from handlers.history import router as history_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(process_router)
    dp.include_router(payment_router)
    dp.include_router(history_router)

    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
