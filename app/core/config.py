"""
All environment configuration lives here. Nothing else in the app should
call os.environ / os.getenv directly — import `settings` instead.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "KrishiSathi"
    ENV: str = "local"

    # LLM_PROVIDER switches app/services/llm_service.py's provider branch —
    # only "gemini" is implemented, no other provider is in scope per
    # CLAUDE.md. Within that, llm_service.py itself tiers between two
    # Gemini auth paths: GEMINI_API_KEY (Gemini Developer API — primary,
    # works from any dev machine with a free Google AI Studio key) and
    # GOOGLE_CLOUD_PROJECT (Vertex AI service-account auth — fallback,
    # the stated production path once real GCP access comes through).
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    GOOGLE_CLOUD_PROJECT: str = ""
    VERTEX_AI_LOCATION: str = "us-central1"

    # STUB: Firestore is the decided datastore (see CLAUDE.md tech stack
    # table) — no SQL engine is configured in this skeleton pass because
    # nothing yet persists data; all routes currently return in-memory
    # fake/randomized values.
    QDRANT_URL: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
