from __future__ import annotations

from typing import Any

import httpx
from google import genai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import OpenAI

from app.core.config import get_settings
from app.llm.clients import LangChainModelFactory


class AIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.factory = LangChainModelFactory()

    def generate_text(
        self,
        provider: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> str:
        chat_model = self.factory.build_chat_model(
            provider=provider,
            temperature=temperature,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

        chat_messages = []
        if system_prompt:
            chat_messages.append(SystemMessage(content=system_prompt))

        for message in messages:
            role = message['role']
            content = message['content']
            if role == 'system':
                chat_messages.append(SystemMessage(content=content))
            elif role == 'assistant':
                chat_messages.append(AIMessage(content=content))
            else:
                chat_messages.append(HumanMessage(content=content))

        response = chat_model.invoke(chat_messages)
        if isinstance(response.content, str):
            return response.content
        if isinstance(response.content, list):
            return ''.join(part.get('text', '') for part in response.content if isinstance(part, dict))
        return str(response.content)

    def generate_json(self, **kwargs: Any) -> str:
        augmented_prompt = (
            kwargs.get('system_prompt', '')
            + '\n\nReturn a valid JSON object only. Do not include markdown fences or extra commentary.'
        ).strip()
        return self.generate_text(
            provider=str(kwargs.get('provider', '')),
            system_prompt=augmented_prompt,
            messages=kwargs.get('messages', []),
            temperature=kwargs.get('temperature', 0.4),
            model=kwargs.get('model'),
            api_key=kwargs.get('api_key'),
            base_url=kwargs.get('base_url'),
        )

    async def qwen_tts(self, text: str, voice: str | None, model: str | None, api_key: str | None, base_url: str | None, extra: dict[str, Any]) -> dict[str, Any]:
        key = api_key or self.settings.qwen_api_key
        if not key:
            raise ValueError('Missing Qwen API key')
        root = (base_url or self.settings.qwen_base_url).rstrip('/')
        url = f'{root}/services/aigc/multimodal-generation/generation'
        headers = {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        }
        body = {
            'model': model or self.settings.qwen_tts_model,
            'input': {
                'text': text,
                'voice': voice or 'Cherry',
                **extra,
            },
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()

    def generate_gemini_tts_audio(self, text: str, voice_name: str | None = None, model: str | None = None, api_key: str | None = None) -> Any:
        key = api_key or self.settings.gemini_api_key
        if not key:
            raise ValueError('Missing Gemini API key')
        client = genai.Client(api_key=key)
        return client.models.generate_content(
            model=model or self.settings.gemini_tts_model,
            contents=text,
            config={
                'response_modalities': ['AUDIO'],
                'speech_config': {
                    'voice_config': {
                        'prebuilt_voice_config': {
                            'voice_name': voice_name or 'Kore',
                        }
                    }
                },
            },
        )

    def generate_openai_chat_completion(self, messages: list[dict[str, str]], model: str | None = None, api_key: str | None = None, base_url: str | None = None, temperature: float = 0.4):
        key = api_key or self.settings.openai_api_key
        if not key:
            raise ValueError('Missing OpenAI API key')
        client = OpenAI(api_key=key, base_url=base_url or self.settings.openai_base_url)
        return client.chat.completions.create(
            model=model or self.settings.openai_model,
            messages=messages,
            temperature=temperature,
        )
