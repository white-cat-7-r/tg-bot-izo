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
