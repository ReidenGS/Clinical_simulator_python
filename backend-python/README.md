# Clinical Simulator Python Backend

This backend is the staged business-logic migration target for the Clinical Simulator project.

## Current role
The current architecture is **frontend-led, backend-assisted**:
- React / TypeScript frontend keeps UI, browser APIs, camera/mic, and real-time interaction
- Python backend is taking over business logic in phases

## What is included
- FastAPI app skeleton
- `/api/health`
- `/api/ai/text`
- `/api/ai/json`
- `/api/interview/respond`
- `/api/interview/evaluate`
- `/api/cpr/runtime/ingest`
- `/api/cpr/runtime/action`
- `/api/cpr/decide`
- `/api/cpr/evaluate`
- `/api/tts/qwen`
- compatibility shim: `/api/cpr/ingest` (legacy transitional path)
- `.env.example`
- Vite dev proxy support from the frontend to `http://127.0.0.1:8000`

## Current migration state
### Interview
Interview main path is already backend-driven for:
- turn processing
- extraction parsing
- session-state updates
- decision generation
- evaluation and feedback

### CPR
CPR is currently in **phase-1 hybrid migration**:
- frontend keeps real-time pose/tracking/workflow responsiveness
- backend handles decision and evaluation endpoints
- frontend still has local fallback logic for resilience

See `MIGRATION_STATUS.md` for the detailed breakdown.

## Phase 2 additions now in place
The backend now includes a first engineering-hardening pass for LangChain orchestration:
- prompt version markers for interview and evaluation chains
- shared retry/backoff helper for chain invocation
- structured-output first strategy with parser-based fallback
- chain metadata/tags prepared for LangSmith tracing
- backend unit tests for service logic and fallback behavior

### Interview orchestration design
The Interview module uses LangChain only for the **LLM orchestration layer**:
- prompt construction
- model adapter selection
- structured output parsing
- fallback handling

Business logic remains in the service layer:
- coverage tracking
- phase transitions
- hint / red-flag / continue decisions
- evaluation aggregation

This keeps the LangChain footprint narrow and avoids coupling core clinical logic to framework internals.

## Environment variables
### Core server
- `HOST`
- `PORT`
- `ALLOWED_ORIGINS`

### LangChain resilience / tracing
- `LANGCHAIN_MAX_RETRIES` — number of retries for structured-output path before fallback
- `LANGCHAIN_RETRY_BACKOFF_SECONDS` — linear backoff multiplier between retries
- `LANGSMITH_TRACING` — enable LangSmith-compatible tracing via environment
- `LANGSMITH_PROJECT` — tracing project label

### Providers
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `OPENAI_TTS_MODEL`
- `GEMINI_TTS_MODEL`
- `QWEN_TTS_MODEL`

## Quick start

```bash
cd backend-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or from project root:

```bash
npm run dev:backend
```

Then separately run the frontend:

```bash
npm run dev
```

## Test command

```bash
cd backend-python
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## Validation status
Current backend test coverage in this branch includes:
- interview service state initialization
- coverage update behavior
- phase transition behavior
- deterministic evaluation scoring
- retry helper behavior
- interview chain fallback behavior
- evaluation chain fallback behavior

For a concise validation checklist, see `../CPR_PHASE_2B_VALIDATION_MATRIX.md`.

## Migration direction
Recommended order from here:
1. keep current interview backend path as primary
2. preserve CPR phase-1 hybrid model while validating endpoint behavior
3. clean up legacy TS fallback paths and document ownership boundaries
4. only then consider deeper CPR state-progression migration to Python

## Important note
This backend is no longer just a skeleton: it already participates in both Interview and CPR production logic paths.
