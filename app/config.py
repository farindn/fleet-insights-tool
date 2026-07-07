"""Application configuration.

All settings load from environment variables (or a local ``.env`` file — see
``.env.example``). The values here are the in-code fallbacks used when a
variable is not set. See USER_GUIDE.md → Installation & Setup → Configure the
Tool for the two values a user must supply (``SESSION_SECRET``, ``GENAI_API_KEY``).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load from .env (UTF-8); silently ignore any unrelated env vars.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Required secrets ────────────────────────────────────────────────
    # Signs the session JWT. The default is for LOCAL DEV ONLY — generate a
    # unique value in production (README / USER_GUIDE.md → Configure the Tool).
    SESSION_SECRET: str = "dev-secret-change-me-in-production-32x"
    # Geotab GenAI Gateway API key. If blank, AI insights are skipped and the
    # report falls back to static text (USER_GUIDE.md → AI-Generated Insights).
    GENAI_API_KEY: str = ""

    # ── AI Gateway ──────────────────────────────────────────────────────
    # Defaults target the Geotab GenAI Gateway with gemini-2.5-flash-lite,
    # matching .env.example and USER_GUIDE.md. Override via .env if required.
    GENAI_GATEWAY_URL: str = "https://genai-us.geotab.com/api/v2"
    GENAI_MODEL: str = "gemini-2.5-flash-lite"
    GENAI_MAX_TOKENS: int = 512        # per-slide insight token cap
    GENAI_RECS_MAX_TOKENS: int = 2048  # recommendations token cap (longer output)

    # ── Auth ────────────────────────────────────────────────────────────
    JWT_EXPIRE_HOURS: int = 4          # session token lifetime (USER_GUIDE.md → Logging In)

    # ── Job lifecycle ───────────────────────────────────────────────────
    JOB_TTL_HOURS: int = 2             # in-memory report jobs are purged after this

    # ── Safety score bands ──────────────────────────────────────────────
    # Risk-band thresholds (USER_GUIDE.md → Understanding the Calculations →
    # Safety Score): High <60, Medium 60–75. The 90 Mild/Low boundary is a
    # literal in report_builder.py.
    SAFETY_HIGH_RISK: float = 60.0
    SAFETY_MEDIUM_RISK: float = 75.0
    DORMANT_DAYS_THRESHOLD: int = 5    # <5 active days ⇒ "Dormant" at-risk flag

    # ── Idling defaults (legacy) ────────────────────────────────────────
    # NOTE: not currently referenced by the idling pipeline — the effective
    # per-fuel defaults come from FUEL_GROUP_MAP in
    # services/analytics/fleet.py. Retained for reference/back-compat only.
    DEFAULT_IDLE_BURN_RATE_ICE: float = 2.5   # L/h
    DEFAULT_IDLE_BURN_RATE_EV: float = 0.8    # kWh/h


settings = Settings()
