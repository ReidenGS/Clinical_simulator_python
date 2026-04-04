# Migration Status

## Overall migration strategy
Current strategy is:
- keep the **React / TypeScript frontend** for UI, camera, microphone, browser speech, and real-time interaction
- move **core business logic** to the **Python backend** in staged steps
- keep temporary frontend fallback paths only where they reduce migration risk

---

## Interview migration status

### Moved to Python backend

#### Runtime orchestration
- `/api/interview/respond`
- patient response generation
- extraction parsing
- session state update
- decision generation

#### Evaluation
- `/api/interview/evaluate`
- rubric scoring
- feedback report generation
- competency level mapping
- next case suggestion

#### Shared AI gateway
- `/api/ai/text`
- `/api/ai/json`

### LangChain status for Interview
Phase 1 and early Phase 2 hardening are now in place.

#### Phase 1 complete
- LangChain model factory added
- interview prompt module added
- evaluation prompt module added
- structured output schemas added
- interview response chain added
- evaluation chain added
- service layer remains authoritative for business rules

#### Phase 2A complete
- prompt version markers added to interview and evaluation prompts
- retry/backoff helper added for chain invocation
- structured-output-first execution with parser fallback added
- chain tags / metadata prepared for LangSmith tracing
- service-layer lazy initialization added to reduce import-time coupling

#### Phase 2B complete
- backend tests added for retry helper
- backend tests added for interview fallback path
- backend tests added for evaluation fallback path
- deterministic service logic tests expanded and passing

### Current frontend role
- React UI components
- browser microphone / speech recognition
- browser audio playback
- local UI state and layout
- display-only helpers such as current progress / presentation logic

### Legacy / cleanup candidates (Interview)
These frontend interview implementations have now been consolidated under `src/modules/interview/legacy/` so the active module surface stays focused on the backend-driven path:
- `src/modules/interview/legacy/orchestration/DialogueOrchestrator.ts`
- `src/modules/interview/legacy/orchestration/DecisionEngine.ts`
- `src/modules/interview/legacy/evaluation/RubricEngine.ts`
- `src/modules/interview/legacy/evaluation/FeedbackGenerator.ts`
- `src/modules/interview/legacy/tracking/SessionStateTracker.ts`
- `src/modules/interview/legacy/services/interviewAiService.ts` (legacy fallback path still exists, disabled by default)

### Notes
- Frontend interview session flow now calls Python backend endpoints for the main path.
- Legacy fallback code remains for safety, but is now disabled by default in the main frontend flow and loaded lazily only if explicitly re-enabled.
- Current backend hardening focuses on resilience and testability rather than changing API contracts.

---

## CPR migration status

### Phase 1 complete: backend-assisted CPR
The CPR module is now in a staged hybrid architecture.

### Moved to Python backend
#### Runtime ingest / action path
- `/api/cpr/runtime/ingest`
- `/api/cpr/runtime/action`
- authoritative CPR runtime state progression
- phase transition handling
- ventilation confirmation handling
- cycle-break resume handling
- runtime-state continuation via `runtimeState` envelope

#### Decision path
- `/api/cpr/decide`
- decision logic
- coaching / instruction generation
- risk / readiness output used by CPR UI

#### Evaluation path
- `/api/cpr/evaluate`
- evaluation scoring
- feedback generation
- breakdown / strengths / gaps / next-step recommendations

### Still in frontend
These remain frontend-side intentionally for real-time responsiveness:
- pose detection
- compression analysis
- observation ingest
- real-time workflow/tracker progression
- local immediate state updates during live CPR

### CPR hook behavior currently in place
In `src/modules/cpr/hooks/useCprSession.ts`:

#### `ingestObservation()`
- frontend sends observation events to:
  - `POST /api/cpr/runtime/ingest`
- backend returns:
  - `sessionState`
  - `runtimeState`
  - `decision`
- frontend treats backend as primary authoritative path
- if backend fails:
  - local `WorkflowOrchestrator` remains fallback

#### explicit CPR actions
Frontend sends explicit control actions to:
- `POST /api/cpr/runtime/action`

This includes:
- phase advance
- ventilation confirmation
- cycle-break resume confirmation

#### `finalizeSession()`
- gets latest authoritative public state
- calls Python backend:
  - `POST /api/cpr/evaluate`
- if backend succeeds:
  - uses backend `evaluation`
  - uses backend `feedback`
- if backend fails:
  - falls back to local `orchestratorRef.current.evaluate(...)`

### Why this staged CPR architecture is good
- preserves live UI responsiveness
- avoids blocking on backend latency during active compression tracking
- allows decision/evaluation logic to migrate to Python first
- keeps real-time browser sensing where it belongs

### CPR cleanup / next-step candidates
Not for deletion yet, but for future review:
- `src/modules/cpr/orchestration/WorkflowOrchestrator.ts`
- `src/modules/cpr/orchestration/DecisionEngine.ts`
- `src/modules/cpr/evaluation/RubricEngine.ts`
- `src/modules/cpr/evaluation/FeedbackGenerator.ts`
- `src/modules/cpr/tracking/SessionStateTracker.ts`

These should remain for now because CPR is still intentionally hybrid.

---

## Safe cleanup candidates across project
- `server.ts.bak`
- `__pycache__/`
- duplicate / outdated requirements or setup notes after verification
- legacy fallback code once endpoint parity is fully confirmed

## Recommended next step
Continue the cleanup / consolidation pass before deeper migration:
1. remove or repoint any remaining imports that still assume legacy files live outside `src/modules/interview/legacy/`
2. keep `ProgressEngine` in the active frontend path for UI-only progress / gap display, and treat `InfoExtractor` as legacy-only (now moved under `src/modules/interview/legacy/tracking/`)
3. verify frontend type / API consistency after the interview legacy isolation
4. trim dead exports, comments, and fallback toggles once backend parity is fully confirmed
5. only then consider deeper CPR state-progression migration to Python
