from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "ReadAgent"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/readagent.db"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # 模型默认值（用户可在前端覆盖）
    DEFAULT_PROCESSING_MODEL: str = "gpt-4o-mini"
    DEFAULT_VERIFIER_MODEL: str = "gpt-4o"
    DEFAULT_CHAT_MODEL: str = "gpt-4o"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"


settings = Settings()
