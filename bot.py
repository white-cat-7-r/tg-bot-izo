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
