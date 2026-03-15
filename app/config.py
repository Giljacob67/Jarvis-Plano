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
    google_oauth_scopes: str = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/tasks"
    google_encryption_key: str = ""

    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    voice_responses_enabled: bool = False
    voice_response_voice: str = "alloy"
    max_audio_file_mb: int = 19
    temp_audio_dir: str = "/tmp/jarvis_audio"

    @property
    def effective_max_audio_mb(self) -> int:
        return min(self.max_audio_file_mb, 20)

    proactive_features_enabled: bool = True
    morning_briefing_enabled: bool = True
    morning_briefing_time: str = "08:00"
    evening_review_enabled: bool = True
    evening_review_time: str = "18:30"
    reminder_check_interval_minutes: int = 10
    default_timezone: str = "America/Sao_Paulo"
    approvals_enabled: bool = True
    max_pending_approvals: int = 20
    followup_default_days: int = 2
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    proactive_min_interval_minutes: int = 30

    google_gmail_enabled: bool = True
    google_gmail_scopes: str = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose"
    gmail_inbox_query_default: str = "in:inbox newer_than:7d"
    gmail_max_list_results: int = 10

    @property
    def all_google_scopes(self) -> str:
        scopes = self.google_oauth_scopes
        if self.google_gmail_enabled:
            scopes = f"{scopes} {self.google_gmail_scopes}"
        return scopes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
