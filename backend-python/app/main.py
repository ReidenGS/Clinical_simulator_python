import base64
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from google.genai import Client as GoogleGenAI
from google.genai import types as genai_types
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # clinical_simulator_dev root
DIST_DIR = BASE_DIR / "dist"

# Explicitly load the root .env so env vars are available before any import
load_dotenv(BASE_DIR / ".env")

from app.api.routes import router  # noqa: E402
from app.core.config import get_settings  # noqa: E402

settings = get_settings()
app = FastAPI(title="Clinical Simulator Python Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ── Proxy routes (from root app.py) ─────────────────────────────────────────

ALLOWED_ORIGINS = {
    "https://api.openai.com",
    "https://dashscope.aliyuncs.com",
    "https://dashscope-intl.aliyuncs.com",
}


class ProxyRequest(BaseModel):
    url: str
    body: dict | None = None
    apiKey: str | None = None  # client-provided key overrides server env


class GeminiTtsRequest(BaseModel):
    text: str
    voiceName: str | None = None
    model: str | None = None
    apiKey: str | None = None  # client-provided key overrides server env


def is_allowed_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
        origin = f"{parsed.scheme}://{parsed.host}"
        if parsed.port:
            origin = f"{origin}:{parsed.port}"
        return origin in ALLOWED_ORIGINS
    except Exception:
        return False


@app.post("/api/proxy/openai")
async def proxy_openai(payload: ProxyRequest):
    if not payload.url:
        raise HTTPException(status_code=400, detail="Missing url")
    if not is_allowed_url(payload.url):
        raise HTTPException(status_code=403, detail="URL not in allowlist")
    api_key = payload.apiKey or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                payload.url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload.body or {},
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Failed to proxy OpenAI request")


@app.post("/api/proxy/qwen-tts")
async def proxy_qwen_tts(payload: ProxyRequest):
    if not payload.url:
        raise HTTPException(status_code=400, detail="Missing url")
    if not is_allowed_url(payload.url):
        raise HTTPException(status_code=403, detail="URL not in allowlist")
    api_key = payload.apiKey or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                payload.url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload.body or {},
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Failed to proxy request")


@app.post("/api/proxy/gemini-tts")
async def proxy_gemini_tts(payload: GeminiTtsRequest):
    if not payload.text:
        raise HTTPException(status_code=400, detail="Missing text")
    api_key = payload.apiKey or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
    try:
        client = GoogleGenAI(api_key=api_key)
        response = client.models.generate_content(
            model=payload.model or "gemini-2.5-flash-preview-tts",
            contents=payload.text,
            config=genai_types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=payload.voiceName or "Kore"
                        )
                    )
                ),
            ),
        )
        audio = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and getattr(inline_data, "data", None):
                    audio = inline_data.data
                    break
        if not audio:
            raise HTTPException(status_code=500, detail="No audio data in Gemini response")
        # Ensure audio is a base64 string for JSON serialization
        if isinstance(audio, (bytes, bytearray)):
            audio = base64.b64encode(audio).decode("utf-8")
        return {"audio": audio}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gemini TTS failed: {exc}")


# ── Static frontend serving ──────────────────────────────────────────────────

if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if DIST_DIR.exists() and full_path:
        requested = DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build not found. Run npm run build first.")
