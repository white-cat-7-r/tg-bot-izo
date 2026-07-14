from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from models import User, Plan
from config import PLAN_CONFIGS, TOKEN_COST_PER_GENERATION

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


async def reset_daily_tokens(session: AsyncSession, user: User) -> User:
    """Reset daily token allocation if it's a new day."""
    now = datetime.now(MOSCOW_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    needs_reset = False
    if user.last_reset_at is None:
        needs_reset = True
    else:
        last_reset = user.last_reset_at
        if last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=MOSCOW_TZ)
        if last_reset < today_start:
            needs_reset = True

    if needs_reset:
        if user.plan != Plan.FREE and user.plan_expires_at:
            expires = user.plan_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=MOSCOW_TZ)
            if expires < now:
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