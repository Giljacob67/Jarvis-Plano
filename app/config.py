from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    jarvis_database_url: str = "sqlite:///./jarvis.db"
    timezone: str = "America/Sao_Paulo"
    app_base_url: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_max_tool_rounds: int = 3
    context_max_messages: int = 20
    context_max_memories: int = 10

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_user_id: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
