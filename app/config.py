from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = "Magic Excel API"
    DEBUG: bool = False

    HF_TOKEN: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    DEFAULT_MODEL: str = "gemma4:e4b"
    OLLAMA_BASE_URL: Optional[str] = None
    FIRE_WORKS_API: Optional[str] = None
    FIREWORKS_MODEL: str = "accounts/fireworks/models/minimax-m2p7"

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SECRET_KEY: str

    # Supabase
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SECRET_KEY: Optional[str] = None

    class Config:
        env_file = str(Path(__file__).parent.parent / ".env")
        extra = "ignore"

settings = Settings()
