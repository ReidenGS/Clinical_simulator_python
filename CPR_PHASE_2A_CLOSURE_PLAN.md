# CPR Phase 2A Closure Plan

## Purpose
This document defines how to close out the current CPR Phase 2A implementation and turn it from a working hybrid migration into a cleaner, more maintainable architecture.

Current Phase 2A already works in principle:
- ingest path is backend-led
- action path is backend-led
- evaluation path is backend-led
- frontend local orchestrator remains as fallback

However, two structural cleanup problems remain:
1. runtime-only backend state is currently mixed directly into `sessionState`
2. ingest and action traffic are multiplexed through one endpoint shape

This plan explains how to cleanly separate those layers.

---

## Current problem summary

### Problem A — runtime fields are mixed into `sessionState`
Current backend CPR runtime stores internal state using fields like:
- `_cycleStartTimestamp`
- `_cycleCompressionCount`
- `_cycleRates`
- `_totalCompressionTimeMs`
- `_lastCompressionTimestamp`
- `_wasCompressing`
- `_interCompressionIntervals`
- `_lastCountedPeakTimestamp`
- `_compressionsSinceVentilation`
- `_ventilationBreathCount`

These are not true UI-facing session-state fields.
They are backend runtime machine state.

Right now they are round-tripped inside `sessionState` because the backend needs them on the next request.
That works, but it creates three issues:
- frontend type pollution
- unclear ownership boundary
- temptation for UI to depend on backend internals

### Problem B — ingest and action share one API shape
Current `POST /api/cpr/ingest` serves two different jobs:
- observation ingest / state progression
- explicit user actions such as phase advance / ventilation confirm / cycle-break resume

That works for bootstrapping, but long-term it blurs semantics:
- ingest is event-driven observation processing
- action is command-driven state transition intent

These should be represented separately.

---

## Closure goals

Phase 2A should be considered structurally closed when:
1. UI-facing `sessionState` contains only UI-facing state
2. backend runtime machine state is separated into its own container
3. observation ingest and explicit control actions have clearly separated API contracts
4. frontend CPR hook no longer relies on hidden `_<field>` state mixed into UI types
5. fallback stays available, but boundaries become explicit and easier to reduce later

---

## Part 1 — runtime field layering

## Recommendation
Split current backend response into:
- `sessionState` → UI/public authoritative CPR state
- `runtimeState` → backend/private continuation state
- `decision`
- `meta`

### Recommended response shape
```json
{
  "sessionState": { ...public CPR state... },
  "runtimeState": { ...backend continuation state... },
  "decision": { ... },
  "meta": { ... }
}
```

### What belongs in `sessionState`
Keep only fields that the frontend UI can reasonably render or consume as product state:
- `module`
- `status`
- `startedAt`
- `scenarioId`
- `currentPhase`
- `currentRate`
- `averageRate`
- `maxRate`
- `elapsedSeconds`
- `checklist`
- `visibleRatio`
- `straightArmRatio`
- `centeredRatio`
- `riskLevel`
- `observations` (if still needed for UI/fallback)
- `trainingMode`
- `currentCycle`
- `cycleHistory`
- `compressionFraction`
- `rateConsistency`
- `recoilRatio`
- `depthProxyAverage`
- `compressionCount`

### What belongs in `runtimeState`
Move all backend-machine continuation fields here:
- `cycleStartTimestamp`
- `cycleCompressionCount`
- `cycleRates`
- `totalCompressionTimeMs`
- `lastCompressionTimestamp`
- `wasCompressing`
- `interCompressionIntervals`
- `lastCountedPeakTimestamp`
- `compressionsSinceVentilation`
- `ventilationBreathCount`

### Why this is better
This gives a clean distinction:
- `sessionState` = what the product is
- `runtimeState` = what the backend machine needs to continue safely

The frontend may transport `runtimeState`, but should not treat it as display state.

---

## Part 2 — frontend typing cleanup

## Recommendation
Introduce a separate frontend type pair:

### Public UI state
Keep existing `CprSessionState` for UI-facing state.

### Backend envelope
Add a new type, for example:
```ts
export interface CprRuntimeState {
  cycleStartTimestamp?: number | null;
  cycleCompressionCount?: number;
  cycleRates?: number[];
  totalCompressionTimeMs?: number;
  lastCompressionTimestamp?: number | null;
  wasCompressing?: boolean;
  interCompressionIntervals?: number[];
  lastCountedPeakTimestamp?: number;
  compressionsSinceVentilation?: number;
  ventilationBreathCount?: number;
}

export interface CprBackendStateEnvelope {
  sessionState: CprSessionState;
  runtimeState: CprRuntimeState | null;
}
```

### Frontend hook state change
In `useCprSession.ts`, keep:
- `sessionStateRef` for public state if desired
or better:
- `backendStateRef` for full authoritative envelope
- derive UI state from `backendStateRef.current.sessionState`

This removes the current need to cast:
```ts
(result.sessionState as CprSessionState & { _ventilationBreathCount?: number })
```

That cast is a strong sign the type boundary is currently wrong.

---

## Part 3 — API shape cleanup

## Recommendation
Split the current mixed `/api/cpr/ingest` behavior into two endpoints.

### Endpoint A — observation ingest
```http
POST /api/cpr/runtime/ingest
```
Purpose:
- accept observation events
- update runtime + session state
- compute decision

Request:
```json
{
  "scenario": { ... },
  "state": {
    "sessionState": { ... },
    "runtimeState": { ... }
  },
  "observation": { ... }
}
```

Response:
```json
{
  "state": {
    "sessionState": { ... },
    "runtimeState": { ... }
  },
  "decision": { ... },
  "meta": { ... }
}
```

### Endpoint B — control actions
```http
POST /api/cpr/runtime/action
```
Purpose:
- explicit user intent transitions
- phase advance
- ventilation confirmation
- cycle-break resume

Request:
```json
{
  "scenario": { ... },
  "state": {
    "sessionState": { ... },
    "runtimeState": { ... }
  },
  "action": "confirm_ventilation",
  "phase": null
}
```

Response:
```json
{
  "state": {
    "sessionState": { ... },
    "runtimeState": { ... }
  },
  "decision": { ... },
  "meta": { ... }
}
```

### Why this split matters
It improves correctness and maintainability:
- ingest = process sensor/event input
- action = process user intent

That makes logs, debugging, tests, and future backend design much clearer.

---

## Part 4 — schema redesign recommendation

## Backend schemas
Instead of extending `CprSessionStatePayload` with internal `_...` aliases, create:

### `CprRuntimeStatePayload`
Contains only backend runtime continuation fields.

### `CprStateEnvelopePayload`
```python
class CprStateEnvelopePayload(BaseModel):
    session_state: CprSessionStatePayload = Field(alias='sessionState')
    runtime_state: CprRuntimeStatePayload | None = Field(default=None, alias='runtimeState')
```

### Replace current mixed request models with:
- `CprRuntimeIngestRequest`
- `CprRuntimeActionRequest`

This is cleaner than continuing to overload `CprIngestRequest`.

---

## Part 5 — service-layer cleanup

## Recommendation
Refactor backend CPR service into clearer layers.

### Suggested internal structure
- `build_public_session_state(...)`
- `build_runtime_state(...)`
- `ingest_runtime(...)`
- `apply_runtime_action(...)`
- `decide(...)`
- `evaluate(...)`

### Even better long-term split
If desired later, move runtime logic out of `cpr_service.py` into:
- `cpr_runtime_service.py` → ingest + runtime transitions
- `cpr_decision_service.py` → decision generation
- `cpr_evaluation_service.py` → final scoring/feedback

That is not required immediately, but it is a good closure direction.

---

## Part 6 — frontend hook cleanup target

## Recommendation for `useCprSession.ts`
Move from this implicit model:
- send/receive raw `sessionState`
- stash internal backend fields inside it
- derive UI plus runtime from one object

to this explicit model:
- keep `backendEnvelopeRef`
- UI reads only `backendEnvelopeRef.current.sessionState`
- request payloads send the full envelope back to backend
- ventilation UI reads `backendEnvelopeRef.current.runtimeState?.ventilationBreathCount`

### Example conceptual shape
```ts
const backendStateRef = useRef<CprBackendStateEnvelope | null>(null);

const publicState = backendStateRef.current?.sessionState ?? null;
const runtimeState = backendStateRef.current?.runtimeState ?? null;
```

This would remove most of the current ambiguity.

---

## Part 7 — fallback strategy after closure

## Recommendation
Do not remove fallback yet, but tighten its role.

### Current fallback
Local `WorkflowOrchestrator` still acts as a broad rescue path.

### After closure
Fallback should be treated as:
- emergency continuity only
- not a parallel evolving primary implementation

### Suggested rule
When backend envelope split is complete:
- keep fallback only for network/backend failure
- avoid adding new product logic to fallback path
- treat backend behavior as source of truth for all future CPR rules

This will reduce dual-maintenance cost over time.

---

## Part 8 — staged closure sequence

### Stage 1 — type and schema cleanup
1. add frontend `CprRuntimeState` type
2. add frontend/backend state envelope types
3. add backend `CprRuntimeStatePayload`
4. stop embedding runtime fields directly into `CprSessionStatePayload`

### Stage 2 — endpoint cleanup
1. split `/api/cpr/ingest` into:
   - `/api/cpr/runtime/ingest`
   - `/api/cpr/runtime/action`
2. keep old endpoint temporarily as compatibility shim if desired

### Stage 3 — hook refactor
1. replace `sessionStateRef` with backend envelope ref
2. update UI to consume only public `sessionState`
3. update ventilation progress to consume `runtimeState`

### Stage 4 — fallback minimization
1. keep fallback only as network failure rescue
2. stop enriching fallback logic beyond parity needs
3. later decide if fallback can be reduced further

---

## Definition of closure success
This closure effort is successful when:
- no backend runtime field needs to be smuggled through `CprSessionState` using `_...`
- frontend CPR UI reads public state only
- runtime continuation fields live in a dedicated envelope
- ingest and action APIs are clearly separated
- backend remains the true owner of CPR runtime state machine
- future CPR work can proceed without deepening technical debt in Phase 2A

---

## Recommended next move
The best next implementation task after this plan is:

**Phase 2A closure implementation, part 1:**
- introduce `runtimeState` envelope
- update schemas and response shape
- refactor frontend hook to use envelope instead of mixed `sessionState`

That gives the highest cleanup value with the lowest conceptual risk.
