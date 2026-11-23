from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    business_name: str = "Maple Grove Dental"
    business_phone: str = "(416) 555-0142"

    kb_dir: Path = Path("data/kb")
    index_dir: Path = Path("data/index")
    db_path: Path = Path("data/handoffs.db")

    # LLM: auto picks Anthropic or OpenAI when a key is present, otherwise the mock.
    llm_provider: str = "auto"          # auto | anthropic | openai | mock
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_timeout: float = 30.0

    # Embeddings are off by default so the service runs with no external calls.
    embeddings_provider: str = "none"   # none | openai | voyage
    embeddings_base_url: str = ""
    embeddings_model: str = ""
    embeddings_api_key: str = ""

    top_k: int = 4
    scope_floor: float = 0.2            # below this the question is treated as off-topic
    confidence_threshold: float = 0.45  # below this an answer is handed to a human
    history_turns: int = 4
    session_ttl_seconds: int = 1800
    max_message_chars: int = 1000

    rate_limit_session_per_minute: int = 12
    rate_limit_ip_per_minute: int = 40
    trust_proxy: bool = False

    handoff_webhook_url: str = ""
    handoff_webhook_format: str = "json"   # json | slack
    handoff_cooldown_seconds: int = 1800

    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    graph_base_url: str = "https://graph.facebook.com/v21.0"

    admin_token: str = ""
    cors_origins: str = "*"

    def resolved_llm(self) -> tuple[str, str, str, str]:
        """Return (provider, base_url, model, api_key) after applying auto-detection."""
        provider = self.llm_provider.lower()
        if provider == "auto":
            if self.llm_api_key or self.anthropic_api_key:
                provider = "anthropic"
            elif self.openai_api_key:
                provider = "openai"
            else:
                provider = "mock"
        if provider == "anthropic":
            return (provider, self.llm_base_url or "https://api.anthropic.com",
                    self.llm_model or "claude-haiku-4-5",
                    self.llm_api_key or self.anthropic_api_key)
        if provider == "openai":
            return (provider, self.llm_base_url or "https://api.openai.com/v1",
                    self.llm_model or "gpt-4o-mini",
                    self.llm_api_key or self.openai_api_key)
        return "mock", "", "mock", ""
