import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str
    database_url: str
    admin_ids: list[int]
    prediction_close_minutes: int


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", ""),
    database_url=os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///bot.db",
).replace(
    "postgresql://",
    "postgresql+asyncpg://",
),
    admin_ids=[
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ],
    prediction_close_minutes=int(os.getenv("PREDICTION_CLOSE_MINUTES", "15")),
)