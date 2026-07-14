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

    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./bot.db")

    TEST_USER_ID: int = Field(default=0, description="Telegram ID тестового аккаунта")
    TEST_MODE: bool = Field(default=False, description="Тестовый режим")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
