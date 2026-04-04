# CPR Backend Boundary

## Purpose
This document defines the intended long-term boundary for CPR logic in the Clinical Simulator project.

The goal is to avoid two opposite mistakes:
1. leaving too much deterministic business logic stranded in the frontend
2. forcing browser-native sensing/interaction work into the backend where it does not belong

This boundary is based on the current Phase 2A result and should guide all follow-up work.

---

## Core rule

### Move to backend
Anything that is:
- deterministic business logic
- state-machine progression
- rules-driven orchestration
- evaluation / scoring / feedback
- explicit workflow transition handling

### Keep in frontend
Anything that is:
- browser-native sensing
- real-time media/camera interaction
- frame-level pose/landmark processing
- immediate UI rendering/interaction
- browser-only control surfaces

---

## Already backend-owned or intended to remain backend-owned

### 1. CPR runtime state machine
These belong in backend and should continue to stay there:
- runtime ingest handling
- next-state calculation
- phase transitions
- runtime continuation state
- cycle progression
- cycle-break handling
- ventilation switching / confirmation rules
- compression count rules
- rhythm/form risk interpretation from already-produced observations

### 2. CPR explicit action handling
These belong in backend:
- phase advance actions
- ventilation confirm actions
- cycle-break resume actions
- any future explicit workflow control actions

### 3. Decision logic
These belong in backend:
- decision message generation
- rhythm status classification
- form status classification
- risk level interpretation
- can-evaluate logic

### 4. Evaluation logic
These belong in backend:
- rubric scoring
- score breakdown calculation
- strengths/gaps generation
- next-step recommendation generation
- cycle comparison analysis
- feedback summary generation

### 5. Runtime envelope / continuation state
These belong in backend-owned design even if transported through frontend:
- cycleStartTimestamp
- cycleCompressionCount
- cycleRates
- totalCompressionTimeMs
- lastCompressionTimestamp
- wasCompressing
- interCompressionIntervals
- lastCountedPeakTimestamp
- compressionsSinceVentilation
- ventilationBreathCount

Frontend may carry these, but should not become their owner.

---

## Explicitly NOT intended for backend migration

### 1. Pose detection
Keep in frontend:
- camera capture
- landmarks extraction
- pose-estimation model execution
- body-part visibility detection

Reason:
- browser/media pipeline concern
- tightly coupled to frame loop and client device capability

### 2. Compression analysis signal generation
Keep in frontend:
- wrist/shoulder movement analysis
- compression peak detection
- frame-window motion processing
- raw observation generation

Reason:
- high-frequency sensor-like processing
- strongly coupled to frame timing and local media state

### 3. Observation production
Keep in frontend:
- transforming local detection into `CprObservation`
- timestamping frame-derived events
- packaging peak timestamps / tracking confidence / depth proxy from local analysis

Reason:
- the frontend is the source of the raw physical signal

### 4. Browser-native interaction surfaces
Keep in frontend:
- camera/mic permissions
- video preview and overlays
- real-time UI updates
- audio/metronome playback controls
- interactive controls and presentation state

Reason:
- browser-only capabilities
- latency-sensitive UI responsibility

---

## Transitional pieces that still exist but should not grow

### 1. Local WorkflowOrchestrator fallback
Current status:
- still exists
- still useful as fallback

Rule:
- keep it for emergency continuity only
- do not keep expanding it as a co-equal primary implementation
- do not add new backend-owned business rules to it unless required for temporary parity

### 2. Legacy compatibility endpoint `/api/cpr/ingest`
Current status:
- compatibility shim only

Rule:
- do not add new primary CPR behavior here
- all new runtime path work should target:
  - `/api/cpr/runtime/ingest`
  - `/api/cpr/runtime/action`

---

## Recommended follow-up direction

## Continue pushing backend-side only for:
- runtime stabilization
- correctness validation
- compatibility shim retirement planning
- fallback minimization
- service-layer cleanup
- runtime rule clarity

## Do NOT spend time migrating to backend:
- browser sensing
- frame-level pose/compression analysis
- real-time visual rendering behavior
- media/device control

---

## Practical rule for future edits
Before migrating any CPR logic, ask:

### Question 1
Is this logic derived from already-produced observations and mostly rule-based?
- if yes → backend candidate

### Question 2
Does this logic depend on browser timing, frame-level camera data, or local media/device interaction?
- if yes → keep frontend

### Question 3
Is this only retained because of transitional fallback?
- if yes → do not enhance unless required for temporary safety/parity

---

## Current bottom-line boundary

### Backend owns
- CPR runtime rules
- CPR state machine
- CPR explicit workflow actions
- CPR decision/evaluation/feedback

### Frontend owns
- sensing
- detection
- observation generation
- browser interaction
- rendering

That is the intended long-term split.
