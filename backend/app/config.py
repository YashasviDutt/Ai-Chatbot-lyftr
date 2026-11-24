import os


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """All configuration comes from environment variables."""

    def __init__(self) -> None:
        self.api_keys = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]
        self.database_url = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
        self.allowed_origins = [
            o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ]
        self.enable_failure_simulation = _bool(os.getenv("ENABLE_FAILURE_SIMULATION", "false"))
        self.model = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
        self.default_system_prompt = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.")
        self.cache_type = os.getenv("CACHE_TYPE", "local")  # local (in-memory) | disk (if supported by LiteLLM version)
        self.request_timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.mock_llm = _bool(os.getenv("MOCK_LLM", "false"))  # tests only

    @property
    def db_path(self) -> str:
        return self.database_url.replace("sqlite:///", "", 1)

    @property
    def cache_dir(self) -> str:
        return os.getenv("CACHE_DIR") or os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "cache")


settings = Settings()
