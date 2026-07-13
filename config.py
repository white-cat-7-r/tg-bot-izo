from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token")
    
    NANO_BANANA_API_KEY: str = Field(..., description="Nano Banana API Key")
    NANO_BANANA_API_URL: str = Field(default="https://api.nanobanana.ai/v1")
    
    YOOKASSA_SHOP_ID: str = Field(..., description="ЮKassa Shop ID")
    YOOKASSA_SECRET_KEY: str = Field(..., description="ЮKassa Secret Key")
    
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    
    PRICE_PER_PROCESSING: int = Field(default=100, description="Цена обработки в рублях")
    WEBHOOK_URL: str = Field(default="", description="URL для webhook ЮKassa")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
