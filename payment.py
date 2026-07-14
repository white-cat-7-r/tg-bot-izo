import aiohttp
import uuid
from config import settings

YOOMONEY_API_URL = "https://yoomoney.ru/api"


async def create_payment(user_id: int, amount: int) -> tuple[str, str]:
    """Создать платёж через YouMoney.

    Возвращает (payment_id, confirmation_url).
    """
    if settings.YOOMONEY_SHOP_ID == "YOUR_SHOP_ID":
        raise NotImplementedError(
            "YouMoney не настроен. Заполни YOOMONEY_SHOP_ID и YOOMONEY_SECRET_KEY в .env"
        )

    payment_id = str(uuid.uuid4())

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{YOOMONEY_API_URL}/payments",
            json={
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
                "description": f"Тариф для пользователя {user_id}",
            },
            headers={
                "Idempotence-Key": payment_id,
                "Authorization": f"Basic {settings.YOOMONEY_SECRET_KEY}",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status not in (200, 201):
                error = await resp.text()
                raise Exception(f"YouMoney API error {resp.status}: {error}")
            data = await resp.json()

    return data["id"], data["confirmation"]["confirmation_url"]


async def check_payment(payment_id: str) -> bool:
    """Проверить статус платежа."""
    if settings.YOOMONEY_SHOP_ID == "YOUR_SHOP_ID":
        return False

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{YOOMONEY_API_URL}/payments/{payment_id}",
            headers={
                "Authorization": f"Basic {settings.YOOMONEY_SECRET_KEY}",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
            return data.get("status") == "succeeded"
