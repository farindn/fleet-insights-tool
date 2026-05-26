from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required
    SESSION_SECRET: str = "dev-secret-change-me-in-production-32x"
    GENAI_API_KEY: str = ""

    # AI Gateway
    GENAI_GATEWAY_URL: str = "https://api.openai.com/v1"
    GENAI_MODEL: str = "gpt-4o-mini"
    GENAI_MAX_TOKENS: int = 512
    GENAI_RECS_MAX_TOKENS: int = 2048

    # Auth
    JWT_EXPIRE_HOURS: int = 4

    # Job lifecycle
    JOB_TTL_HOURS: int = 2

    # Safety thresholds (mirror notebook defaults)
    SAFETY_HIGH_RISK: float = 60.0
    SAFETY_MEDIUM_RISK: float = 75.0
    DORMANT_DAYS_THRESHOLD: int = 5

    # Idling defaults (used if no fuel setting provided)
    DEFAULT_IDLE_BURN_RATE_ICE: float = 2.5   # L/h
    DEFAULT_IDLE_BURN_RATE_EV: float = 0.8    # kWh/h


settings = Settings()
