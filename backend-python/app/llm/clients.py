from __future__ import annotations

from app.core.config import get_settings


class LangChainModelFactory:
    def __init__(self) -> None:
        self.settings = get_settings()

    def build_chat_model(
        self,
        provider: str,
        temperature: float = 0.4,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        provider_upper = provider.upper()

        if provider_upper == 'OPENAI':
            from langchain_openai import ChatOpenAI

            key = api_key or self.settings.openai_api_key
            if not key:
                raise ValueError('Missing OpenAI API key')
            return ChatOpenAI(
                api_key=key,
                base_url=base_url or self.settings.openai_base_url,
                model=model or self.settings.openai_model,
                temperature=temperature,
            )

        if provider_upper == 'GEMINI':
            from langchain_google_genai import ChatGoogleGenerativeAI

            key = api_key or self.settings.gemini_api_key
            if not key:
                raise ValueError('Missing Gemini API key')
            return ChatGoogleGenerativeAI(
                google_api_key=key,
                model=model or self.settings.gemini_model,
                temperature=temperature,
            )

        raise ValueError(f'Unsupported provider: {provider}')
