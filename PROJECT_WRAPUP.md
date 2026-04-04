# Project Wrap-up / Consolidation Notes

## Current state
This repository is the active working line for the Clinical Simulator project.

It now contains:
- React / TypeScript frontend for user experience, camera, browser speech, and live interaction
- Python backend migration work under `backend-python/`
- production-style serving through root `app.py`
- Interview LangChain orchestration with Phase 2 hardening work in place

## Backend migration summary
### Interview
Interview is the most backend-mature module right now.

Implemented in Python backend:
- response generation
- extraction parsing
- session state progression
- decision generation
- evaluation and feedback report generation

LangChain scope is intentionally limited to the orchestration layer:
- provider model factory
- prompt modules
- structured output schemas
- response / evaluation chains
- retry + fallback handling

Business rules remain in the service layer.

### CPR
CPR remains intentionally hybrid.

Backend owns:
- runtime ingest/action endpoints
- decision logic
- evaluation logic

Frontend still owns:
- pose detection
- compression analysis
- local real-time responsiveness
- immediate session interaction loop

## Phase 2 hardening completed
Completed in this pass:
- prompt versioning markers added
- retry/backoff helper added
- structured-output-first with parser fallback added
- chain metadata/tags prepared for tracing
- backend unit tests added for service logic and fallback paths

Validation currently passes via backend unittest suite.

## Recommended next engineering step
- keep backend authoritative for Interview
- keep CPR hybrid until endpoint ownership is fully stable
- continue isolating or removing legacy frontend Interview fallback paths
- later add provider-backed integration tests in a fully provisioned Python environment

## Frontend boundary update
A frontend boundary pass has also been applied for Interview:
- legacy interview response/evaluation paths are disabled by default
- legacy modules are no longer statically imported from the main screen/hook path
- fallback code is now treated as explicit legacy behavior rather than normal architecture
