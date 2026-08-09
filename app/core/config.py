"""
All environment configuration lives here. Nothing else in the app should
call os.environ / os.getenv directly — import `settings` instead.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "KrishiSathi"
    ENV: str = "local"

    # STUB: real credentials wired up when M1/M4/M5 stop being stubs.
    # LLM_PROVIDER switches app/services/llm_service.py once that file exists
    # (Gemini via Vertex AI per CLAUDE.md — no other provider is in scope).
    LLM_PROVIDER: str = "gemini"
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
