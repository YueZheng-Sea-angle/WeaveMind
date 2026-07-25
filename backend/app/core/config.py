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
    # 角色卡构建默认沿用高质量模型（结构化档案生成，建议更强模型）
    DEFAULT_CARD_MODEL: str = "gpt-4o"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # 对话大脑专属 API（可独立配置，不填则沿用主 API）
    CHAT_API_KEY: str = ""
    CHAT_BASE_URL: str = ""

    # Embedding 专属 API（可独立配置，不填则沿用主 API）
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""


settings = Settings()
