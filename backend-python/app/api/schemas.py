from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TextRequest(BaseModel):
    provider: Literal["OPENAI", "GEMINI"]
    model: str | None = None
    system_prompt: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float = 0.4
    api_key: str | None = None
    base_url: str | None = None


class JsonRequest(TextRequest):
    pass


class TtsRequest(BaseModel):
    provider: Literal["OPENAI", "GEMINI", "QWEN"]
    text: str
    model: str | None = None
    voice: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
