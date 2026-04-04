# CPR Phase 2A Migration Plan

## Goal
Move CPR **workflow / state progression** business logic from frontend TypeScript to Python backend, while keeping:
- frontend pose detection
- frontend compression analysis
- frontend observation generation
- frontend real-time UI responsiveness

This is the next staged step after the current hybrid architecture:
- frontend still senses and renders in real time
- backend already handles `/api/cpr/decide` and `/api/cpr/evaluate`

Phase 2A adds a new backend-owned path for **state transition / orchestration**.

---

## Current architecture summary

### Frontend currently owns
In `src/modules/cpr/hooks/useCprSession.ts` and related CPR files, frontend still owns:
- observation ingest entry point
- local `WorkflowOrchestrator`
- local `SessionStateTracker`
- phase switching logic
- 30:2 ventilation switching
- cycle-break progression
- local fallback decision/evaluation behavior

### Backend currently owns
In `backend-python/app/services/cpr_service.py`, backend already owns:
- decision generation
- evaluation scoring
- feedback generation

---

## What should migrate in Phase 2A

### Move to backend now
1. session state progression
2. phase transition logic
3. cycle-break logic
4. 30:2 ventilation switching logic
5. compression-count accumulation rules
6. backend-generated next state + decision in one response

### Keep in frontend for now
1. pose detection
2. landmark processing
3. compression peak detection
4. observation generation
5. UI rendering and voice/metronome controls
6. optional local fallback orchestrator during transition period

---

## Why this split is correct
The current frontend `SessionStateTracker.ts` mixes two kinds of work:

### A. Browser-side sensing work
Examples:
- observation timestamps
- peak timestamps
- compression-rate signal inputs
- visibility / alignment observations

This should stay in frontend because it depends on browser timing and camera pipeline.

### B. Business-rule state machine work
Examples:
- current phase changes
- when cycle break is due
- when 30 compressions triggers ventilation
- when completed cycles are appended
- when compression counters reset
- what state snapshot should be considered authoritative

This should move to backend because it is deterministic business logic and should be centralized.

---

## Recommended API design

### New endpoint
Add:
- `POST /api/cpr/ingest`

### Request payload
Backend should receive:
- `scenario`
- `sessionState` (nullable on first call)
- `observation`
- optional control flags if needed later

Suggested shape:

```json
{
  "scenario": { ... },
  "sessionState": { ... } | null,
  "observation": { ... }
}
```

### Response payload
Backend should return:

```json
{
  "sessionState": { ...next authoritative state... },
  "decision": { ... },
  "meta": {
    "usedFallback": false,
    "transitionEvents": ["cycle_break_started", "ventilation_started"]
  }
}
```

`meta.transitionEvents` is optional but useful for debugging and future UI polish.

---

## Recommended backend responsibilities for `/api/cpr/ingest`

The backend endpoint should do the equivalent of current frontend flow:

1. accept latest observation
2. build or continue session state
3. update running metrics
4. apply phase progression rules
5. apply cycle-break rules
6. apply 30:2 ventilation switching rules
7. compute decision using backend `decide()`
8. return next state + decision together

This means backend becomes the **authoritative CPR state machine**.

---

## Migration boundary details

### Logic to port from frontend `SessionStateTracker.ts`
These rules should move into Python:
- observation-window trimming
- current/average/max rate derivation from observation stream
- visible / straight-arm / centered ratios
- compression-fraction accumulation
- rate-consistency accumulation
- recoil ratio aggregation
- depth proxy average aggregation
- risk-level derivation
- cycle stats accumulation
- current cycle number handling
- compression count handling
- compressions-since-ventilation handling
- phase auto-advance rules

### Logic to port from frontend `WorkflowOrchestrator.ts`
These rules should move into Python:
- cycle break trigger
- transition to `CYCLE_BREAK`
- transition from `COMPRESSIONS` to `VENTILATION`
- ventilation breath reset behavior
- post-ventilation reset back to `COMPRESSIONS`
- local orchestration response shape

### Logic that can remain frontend-controlled temporarily
- explicit user action callbacks such as:
  - confirm ventilation
  - confirm phase advance
  - brief/setup UI transitions

But even these should eventually call backend-owned transition endpoints or control actions.

---

## Phase 2A scope limit
To keep this safe, Phase 2A should **not** fully migrate every explicit UI-triggered transition yet.

### Phase 2A should include
- observation-driven next-state calculation
- backend-owned workflow progression during active CPR
- backend-owned decision result paired with next state

### Phase 2A can leave for later
- `confirmVentilation()` as a separate action
- `confirmPhaseAdvance()` as a separate action
- all pre-brief / setup UI state outside live CPR runtime

That gives a smaller and safer first step.

---

## Proposed implementation sequence

### Step 1 — Backend schema expansion
Update `backend-python/app/api/cpr_schemas.py` to support:
- full `CprObservationPayload`
  - add optional `wristY`
  - `shoulderWidth`
  - `recoilComplete`
  - `depthProxy`
  - `trackingConfidence`
  - `peakTimestamps`
- new `CprIngestRequest`
  - `scenario`
  - `sessionState | null`
  - `observation`

### Step 2 — Backend CPR state tracker service
Add a Python-side tracker/orchestrator layer, for example:
- `backend-python/app/services/cpr_tracker_service.py`

This module should:
- reconstruct or continue state from incoming `sessionState`
- apply one observation update
- return next state

### Step 3 — Backend route
Add route:
- `POST /api/cpr/ingest`

In `routes.py`, do:
- `result = cpr_service.ingest(...)`
- return `{ sessionState, decision, meta }`

### Step 4 — Backend service refactor
Refactor `CprService` so it has:
- `ingest(...)`
- `decide(...)`
- `evaluate(...)`

Where:
- `ingest()` handles state progression and internally calls `decide()`

### Step 5 — Frontend integration in `useCprSession.ts`
Change `ingestObservation()` from:
- local orchestrator first
- async backend decision second

to:
- call backend `/api/cpr/ingest` as primary path
- set returned `sessionState`
- set returned `decision`
- if backend fails, keep current local orchestrator as fallback

This preserves resilience while shifting authority to backend.

### Step 6 — Keep finalize path as-is initially
`finalizeSession()` can continue using backend `/api/cpr/evaluate` as it already does.
No need to destabilize that path in Phase 2A.

---

## Frontend behavior after Phase 2A

### Primary path
1. frontend generates observation
2. frontend calls `/api/cpr/ingest`
3. backend returns authoritative `sessionState + decision`
4. frontend renders returned state

### Fallback path
If backend ingest fails:
1. frontend local orchestrator computes fallback state + decision
2. UI continues working
3. console logs backend failure

This is the safest migration path because it does not sacrifice usability during backend iteration.

---

## Risks and mitigations

### Risk 1: request frequency is too high
Observation events may be too frequent for backend round-trips.

#### Mitigation
Phase 2A should keep current local observation generation but consider:
- throttling backend ingest calls
- only sending observations when a meaningful state delta occurs
- or batching a short observation window later if needed

For first implementation, keep it simple and measure.

### Risk 2: frontend/backend state drift
If local fallback and backend primary logic differ, states may diverge.

#### Mitigation
- treat backend as primary when available
- log transition differences during migration
- keep response payload explicit and deterministic

### Risk 3: missing fields in current backend schema
Current `CprObservationPayload` is too narrow for full tracker parity.

#### Mitigation
Expand schema first before migrating tracker logic.

### Risk 4: checklist behavior mismatch
`ChecklistEngine` behavior currently lives in frontend TS.

#### Mitigation
Either:
- port checklist rules into Python in Phase 2A, or
- temporarily keep checklist derived from incoming state until parity is complete

Recommended: port checklist logic now if it is compact.

---

## Files expected to change in Phase 2A

### Backend
- `backend-python/app/api/cpr_schemas.py`
- `backend-python/app/api/routes.py`
- `backend-python/app/services/cpr_service.py`
- `backend-python/app/services/__init__.py` (if needed)
- new file likely needed:
  - `backend-python/app/services/cpr_tracker_service.py`
  - or `cpr_runtime_service.py`

### Frontend
- `src/modules/cpr/hooks/useCprSession.ts`

### Optional frontend fallback references retained for now
- `src/modules/cpr/orchestration/WorkflowOrchestrator.ts`
- `src/modules/cpr/tracking/SessionStateTracker.ts`

---

## Definition of done for Phase 2A
Phase 2A is complete when:

1. active CPR observation handling primarily goes through backend `/api/cpr/ingest`
2. backend returns authoritative `sessionState + decision`
3. frontend still remains responsive
4. fallback local orchestrator still exists for safety
5. `/api/cpr/evaluate` continues to work unchanged
6. CPR business-state ownership is clearly more backend-centric than before

---

## Recommended next step after this plan
Start implementing Phase 2A in this order:
1. expand CPR schemas
2. create backend ingest/state-progress service
3. add `/api/cpr/ingest`
4. switch frontend `useCprSession.ts` primary path to backend ingest
5. keep local fallback until parity is verified
