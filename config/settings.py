import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    openai_api_key: str | None
    openai_model: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./commercial.db"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    )
