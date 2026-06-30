import os

class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://tax_ai:tax_ai_password@postgres:5432/tax_ai")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")

settings = Settings()

ANOMALY_RULE_CONFIG = {
    "default_tolerance_amount": 5.00,
    "owner_loan_materiality_threshold": 10000.00,
    "distribution_capital_tolerance": 5.00,
    "ownership_distribution_percent_tolerance": 0.01,
    "default_confidence_score": 0.75,
    "book_tax_difference_tolerance": 5.00,
    "retained_earnings_rollforward_tolerance": 5.00,
    "aaa_rollforward_tolerance": 5.00,
    "capital_rollforward_tolerance": 5.00
}

