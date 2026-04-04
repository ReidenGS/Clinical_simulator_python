import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from google.genai import Client as GoogleGenAI
from google.genai import types as genai_types
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / 'dist'

ALLOWED_ORIGINS = {
    'https://api.openai.com',
    'https://dashscope.aliyuncs.com',
    'https://dashscope-intl.aliyuncs.com',
}


class ProxyRequest(BaseModel):
    url: str
    body: dict | None = None


class GeminiTtsRequest(BaseModel):
    text: str
    voiceName: str | None = None
    model: str | None = None


def is_allowed_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
        origin = f'{parsed.scheme}://{parsed.host}'
        if parsed.port:
            origin = f'{origin}:{parsed.port}'
        return origin in ALLOWED_ORIGINS
    except Exception:
        return False


def get_api_key(provider: str) -> str | None:
    if provider == 'openai':
        return os.getenv('OPENAI_API_KEY')
    if provider == 'gemini':
        return os.getenv('GEMINI_API_KEY')
    if provider == 'qwen':
        return os.getenv('DASHSCOPE_API_KEY')
    return None


app = FastAPI(title='Clinical Simulator Python Backend')

allowed_origins = (
    [origin for origin in [os.getenv('RENDER_EXTERNAL_URL'), os.getenv('APP_URL')] if origin]
    if os.getenv('NODE_ENV') == 'production'
    else ['http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:5173', 'http://127.0.0.1:5173']
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health_check():
    return {'status': 'ok'}


@app.post('/api/proxy/openai')
async def proxy_openai(payload: ProxyRequest):
    if not payload.url:
        raise HTTPException(status_code=400, detail='Missing url')
    if not is_allowed_url(payload.url):
        raise HTTPException(status_code=403, detail='URL not in allowlist')

    api_key = get_api_key('openai')
    if not api_key:
        raise HTTPException(status_code=500, detail='OPENAI_API_KEY not configured on server')

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                payload.url,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload.body or {},
            )
        content_type = response.headers.get('content-type', '')
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=content_type or 'application/octet-stream',
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail='Failed to proxy OpenAI request')


@app.post('/api/proxy/qwen-tts')
async def proxy_qwen_tts(payload: ProxyRequest):
    if not payload.url:
        raise HTTPException(status_code=400, detail='Missing url')
    if not is_allowed_url(payload.url):
        raise HTTPException(status_code=403, detail='URL not in allowlist')

    api_key = get_api_key('qwen')
    if not api_key:
        raise HTTPException(status_code=500, detail='DASHSCOPE_API_KEY not configured on server')

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                payload.url,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload.body or {},
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get('content-type', 'application/json'),
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail='Failed to proxy request')


@app.post('/api/proxy/gemini-tts')
async def proxy_gemini_tts(payload: GeminiTtsRequest):
    if not payload.text:
        raise HTTPException(status_code=400, detail='Missing text')

    api_key = get_api_key('gemini')
    if not api_key:
        raise HTTPException(status_code=500, detail='GEMINI_API_KEY not configured on server')

    try:
        client = GoogleGenAI(api_key=api_key)
        response = client.models.generate_content(
            model=payload.model or 'gemini-2.5-flash-preview-tts',
            contents=payload.text,
            config=genai_types.GenerateContentConfig(
                response_modalities=['AUDIO'],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=payload.voiceName or 'Kore'
                        )
                    )
                ),
            ),
        )

        audio = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                inline_data = getattr(part, 'inline_data', None)
                if inline_data and getattr(inline_data, 'data', None):
                    audio = inline_data.data
                    break

        if not audio:
            raise HTTPException(status_code=500, detail='No audio data in Gemini response')

        return {'audio': audio}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Gemini TTS failed: {exc}')


if DIST_DIR.exists():
    assets_dir = DIST_DIR / 'assets'
    if assets_dir.exists():
        app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')


@app.get('/{full_path:path}')
async def spa_fallback(full_path: str):
    if DIST_DIR.exists() and full_path:
        requested = DIST_DIR / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
    index_file = DIST_DIR / 'index.html'
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail='Frontend build not found. Run npm run build first.')
