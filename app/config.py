import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


class Settings:
    """Application configuration settings with dynamic LLM provider support."""

    APP_NAME: str = "Smart Hospital AI Assistant"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    DB_PATH: Path = Path(__file__).resolve().parent.parent / "hospital.db"

    # Security / Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "smart-hospital-secret-key-super-secure-2026-min32chars")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1")

    # Server settings
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8500"))
    RELOAD: bool = os.getenv("RELOAD", "false").lower() in ("true", "1")

    @property
    def ALLOWED_ORIGINS(self) -> list:
        raw = os.getenv("ALLOWED_ORIGINS", "")
        if raw.strip():
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return [
            f"http://localhost:{self.PORT}",
            f"http://127.0.0.1:{self.PORT}",
            "http://localhost:3000",
            "http://localhost:8500",
            "http://127.0.0.1:8500",
        ]

    # RAG Chunking & Retrieval Configuration
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "500"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
    RAG_SCORE_THRESHOLD: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.25"))

    # Indian Hospital Localization & Emergency Constants
    CURRENCY_SYMBOL: str = "₹"
    CURRENCY_CODE: str = "INR"
    EMERGENCY_AMBULANCE: str = "108"
    EMERGENCY_NATIONAL: str = "112"
    EMERGENCY_HELPLINE: str = "+91-1800-419-5555"
    HOSPITAL_LOCATION: str = "Road No. 12, Banjara Hills, Hyderabad, Telangana 500034, India"
    WORKING_HOURS_START: str = "09:00"
    WORKING_HOURS_END: str = "17:00"
    SLOT_DURATION_MINUTES: int = 30
    AVAILABLE_SLOT_TIMES: list = [
        "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"
    ]

    # Smartflo Telephony Configuration
    SMARTFLO_WS_TOKEN: str = os.getenv("SMARTFLO_WS_TOKEN", "smartflo-secure-telephony-token-2026")

    # Gemini Live Native Voice Configuration
    GEMINI_LIVE_MODEL: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash")
    GEMINI_VOICE_NAME: str = os.getenv("GEMINI_VOICE_NAME", "Aoede")
    DEFAULT_TEMPERATURE: float = 0.2

    @property
    def GEMINI_API_KEY(self) -> str:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

    def validate_security(self) -> None:
        """Validate security configuration at application startup."""
        if not self.DEMO_MODE and len(self.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY must be set to a secure string with at least 32 characters in production. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )

    def get_llm_config(self) -> dict:
        """
        Dynamically parse LLM provider, model name, API key, and API base URL
        from environment variables (.env) and format them for LiteLLM / ADK.
        """
        raw_provider = (
            os.getenv("LLM_PROVIDER")
            or os.getenv("PROVIDER")
            or os.getenv("LLM_VENDOR")
            or ""
        ).strip().strip('"\'')

        raw_model = (
            os.getenv("MODEL")
            or os.getenv("LLM_MODEL")
            or os.getenv("MODEL_NAME")
            or "google/gemini-2.5-flash-lite"
        ).strip().strip('"\'')

        raw_api_key = (
            os.getenv("API_KEY")
            or os.getenv("LLM_API_KEY")
            or ""
        ).strip().strip('"\'')

        api_base = (
            os.getenv("API_BASE")
            or os.getenv("LLM_API_BASE")
            or ""
        ).strip().strip('"\'')

        provider = raw_provider.lower().replace("-", "_")

        # Detect if raw_provider is actually an API key (e.g. sk-or-v1-..., gsk_..., AIzaSy...)
        if not raw_api_key and (
            raw_provider.startswith("sk-or-v1-")
            or raw_provider.startswith("gsk_")
            or raw_provider.startswith("AIzaSy")
            or raw_provider.startswith("sk-")
        ):
            raw_api_key = raw_provider
            provider = ""

        # Infer provider from API key prefix if provider is empty
        if not provider and raw_api_key:
            if raw_api_key.startswith("sk-or-v1-"):
                provider = "openrouter"
            elif raw_api_key.startswith("gsk_"):
                provider = "groq"
            elif raw_api_key.startswith("AIzaSy"):
                provider = "gemini"
            elif raw_api_key.startswith("sk-"):
                provider = "openai"

        # Infer provider from model name if provider is empty
        if not provider:
            lower_model = raw_model.lower()
            if lower_model.startswith("openrouter/"):
                provider = "openrouter"
            elif lower_model.startswith("gemini/") or lower_model.startswith("google/"):
                provider = "gemini"
            elif lower_model.startswith("groq/"):
                provider = "groq"
            elif lower_model.startswith("grok/") or lower_model.startswith("xai/"):
                provider = "xai"
            elif lower_model.startswith("openai/"):
                provider = "openai"
            elif lower_model.startswith("anthropic/"):
                provider = "anthropic"
            elif lower_model.startswith("deepseek/"):
                provider = "deepseek"
            elif "/" in raw_model:
                if os.getenv("OPENROUTER_API_KEY") or raw_api_key.startswith("sk-or-v1-"):
                    provider = "openrouter"
                elif os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY") or raw_api_key.startswith("gsk_"):
                    provider = "groq"
                elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or raw_api_key.startswith("AIzaSy"):
                    provider = "gemini"

        # Resolve provider-specific API Key if raw_api_key is not set
        if not raw_api_key:
            if provider == "openrouter":
                raw_api_key = os.getenv("OPENROUTER_API_KEY", "")
            elif provider in ("gemini", "google"):
                raw_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
            elif provider == "groq":
                raw_api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY") or ""
            elif provider in ("grok", "xai"):
                raw_api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or os.getenv("GROQ_API_KEY") or ""
            elif provider == "openai":
                raw_api_key = os.getenv("OPENAI_API_KEY", "")
            elif provider == "anthropic":
                raw_api_key = os.getenv("ANTHROPIC_API_KEY", "")
            elif provider == "deepseek":
                raw_api_key = os.getenv("DEEPSEEK_API_KEY", "")
            elif provider == "mistral":
                raw_api_key = os.getenv("MISTRAL_API_KEY", "")

            # Fallback to any available provider key if still empty
            if not raw_api_key:
                raw_api_key = (
                    os.getenv("GROK_API_KEY")
                    or os.getenv("GROQ_API_KEY")
                    or os.getenv("OPENROUTER_API_KEY")
                    or os.getenv("GEMINI_API_KEY")
                    or os.getenv("GOOGLE_API_KEY")
                    or os.getenv("OPENAI_API_KEY")
                    or ""
                )

        # Format model string for LiteLLM
        model_name = raw_model
        if provider == "openrouter":
            if not model_name.startswith("openrouter/"):
                model_name = f"openrouter/{model_name}"
        elif provider in ("gemini", "google"):
            if model_name.startswith("google/"):
                model_name = "gemini/" + model_name[len("google/"):]
            elif not model_name.startswith("gemini/"):
                model_name = f"gemini/{model_name}"
        elif provider == "groq":
            if not model_name.startswith("groq/"):
                model_name = f"groq/{model_name}"
        elif provider in ("grok", "xai"):
            if not (model_name.startswith("xai/") or model_name.startswith("grok/") or model_name.startswith("groq/")):
                model_name = f"xai/{model_name}"
        elif provider == "openai":
            if not model_name.startswith("openai/"):
                model_name = f"openai/{model_name}"
        elif provider == "anthropic":
            if not model_name.startswith("anthropic/"):
                model_name = f"anthropic/{model_name}"
        elif provider == "deepseek":
            if not model_name.startswith("deepseek/"):
                model_name = f"deepseek/{model_name}"
        elif provider:
            if not ("/" in model_name and model_name.startswith(f"{provider}/")):
                model_name = f"{provider}/{model_name}"

        return {
            "provider": provider,
            "model_name": model_name,
            "raw_model": raw_model,
            "api_key": raw_api_key,
            "api_base": api_base
        }

    @property
    def MODEL_NAME(self) -> str:
        return self.get_llm_config()["model_name"]

    @property
    def GROK_API_KEY(self) -> str:
        return self.get_llm_config()["api_key"]


settings = Settings()
