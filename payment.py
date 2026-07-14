from config import settings


async def create_payment(user_id: int, amount: int) -> tuple[str, str]:
    """Создать платёж. Заглушка — интеграция с платёжной системой TBD."""
    raise NotImplementedError("Платежи ещё не подключены")


async def check_payment(payment_id: str) -> bool:
    """Проверить статус платежа. Заглушка."""
    raise NotImplementedError("Платежи ещё не подключены")
