from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://lumina:lumina@localhost:5432/lumina"

    # Anthropic (for AI pipeline)
    anthropic_api_key: str = ""
    anthropic_model_fast: str = "claude-haiku-4-5"  # for summarization
    anthropic_model_smart: str = "claude-sonnet-5"  # for planning/generation

    # ManimStudio SDK
    manimstudio_api_key: str = ""
    manimstudio_base_url: str = "https://manimstudio.me"

    # App
    environment: str = "development"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
