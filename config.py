from pydantic_settings import BaseSettings
from pydantic import Field
import enum


class Plan(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    EXTENDED = "extended"
    UNLIMITED = "unlimited"


TOKEN_COST_PER_GENERATION = 5

PLAN_CONFIGS = {
    Plan.FREE: {"daily_tokens": 50, "price": 0},
    Plan.STANDARD: {"daily_tokens": 200, "price": 500},
    Plan.EXTENDED: {"daily_tokens": 500, "price": 900},
    Plan.UNLIMITED: {"daily_tokens": None, "price": 1300},
}


class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token")
    
    NANO_BANANA_API_KEY: str = Field(..., description="Nano Banana API Key")
    NANO_BANANA_API_URL: str = Field(default="https://api.nanobanana.ai/v1")
    
    YOOKASSA_SHOP_ID: str = Field(..., description="ЮKassa Shop ID")
    YOOKASSA_SECRET_KEY: str = Field(..., description="ЮKassa Secret Key")
    
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    
    PRICE_PER_PROCESSING: int = Field(default=100, description="Цена обработки в рублях (legacy)")
    WEBHOOK_URL: str = Field(default="", description="URL для webhook ЮKassa")
    
    TEST_USER_ID: int = Field(default=0, description="Telegram ID тестового аккаунта с безлимитом")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
