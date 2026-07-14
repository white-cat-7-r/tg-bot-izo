import aiohttp
from config import settings


async def process_photo(photo_bytes: bytes, prompt: str) -> bytes:
    """Отправить фото в Nano Banana API и получить обработанное."""
    if settings.TEST_MODE:
        return photo_bytes

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