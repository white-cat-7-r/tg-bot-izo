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