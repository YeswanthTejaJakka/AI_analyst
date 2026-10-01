import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "QueryPilot"
    DEBUG: bool = False
    
    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    SAMPLE_DB_PATH: str = str(BASE_DIR / "sample_database" / "ecommerce.db")
    UPLOAD_DIR: str = str(BASE_DIR / "backend" / "temp_uploads")
    
    # Limits & Security
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50MB
    QUERY_TIMEOUT_SECONDS: int = 10
    MAX_RETURNED_ROWS: int = 1000
    SESSION_EXPIRE_MINUTES: int = 120
    
    # AI / LLM Configuration
    # Supported: 'auto', 'gemini', 'openai', 'heuristic'
    LLM_PROVIDER: str = "auto"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure temp directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
