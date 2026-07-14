import urllib.parse
import aiohttp
from config import settings


async def generate_image(prompt: str) -> bytes:
    """Сгенерировать изображение через Pollinations.ai (бесплатно, без ключей).

    Args:
        prompt: Текстовое описание желаемого изображения.

    Returns:
        bytes: JPEG изображение.
    """
    if settings.TEST_MODE:
        return b"test_image"

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Pollinations API error {resp.status}: {error_text}")
            return await resp.read()
