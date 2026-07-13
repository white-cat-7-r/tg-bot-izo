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
