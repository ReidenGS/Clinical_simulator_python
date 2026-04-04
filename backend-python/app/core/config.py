from functools import lru_cache
from typing import List
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - compatibility for minimal test environments
    def load_dotenv() -> None:
        return None

try:
    from pydantic import BaseModel
except ModuleNotFoundError:  # pragma: no cover - compatibility for minimal test environments
    class BaseModel:
        def __init__(self, **kwargs):
            annotations = getattr(self.__class__, '__annotations__', {})
            for field in annotations:
                if field in kwargs:
                    setattr(self, field, kwargs[field])
                else:
                    setattr(self, field, getattr(self.__class__, field))


load_dotenv()


class Settings(BaseModel):
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    langchain_max_retries: int = int(os.getenv("LANGCHAIN_MAX_RETRIES", "2"))
    langchain_retry_backoff_seconds: float = float(os.getenv("LANGCHAIN_RETRY_BACKOFF_SECONDS", "0.5"))
    langsmith_enabled: bool = os.getenv("LANGSMITH_TRACING", "false").lower() in {"1", "true", "yes", "on"}
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "clinical-simulator")
    allowed_origins: List[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ]

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    openai_tts_model: str = os.getenv("OPENAI_TTS_MODEL", "tts-1")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_tts_model: str = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")

    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/api/v1")
    qwen_tts_model: str = os.getenv("QWEN_TTS_MODEL", "qwen3-tts-instruct-flash")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
