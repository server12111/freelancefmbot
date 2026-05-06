import os
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str

    DATABASE_URL: str = "sqlite+aiosqlite:///freelance_bot.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    CRYPTOBOT_TOKEN: str = ""
    CRYPTOBOT_API_URL: str = "https://pay.crypt.bot/api"

    TON_API_KEY: str = ""
    TON_CENTER_URL: str = "https://toncenter.com/api/v2"
    TON_WALLET_ADDRESS: str = ""
    TON_MNEMONIC: str = ""

    ADMIN_IDS: List[int] = []

    PLATFORM_FEE_PERCENT: float = 5.0
    ANTI_SPAM_MAX_MESSAGES: int = 10
    ANTI_SPAM_WINDOW_SECONDS: int = 10

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v

    class Config:
        env_file = ".env"


settings = Settings()
