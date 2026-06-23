import os

class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://tax_ai:tax_ai_password@postgres:5432/tax_ai")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")

settings = Settings()
