# Phase 2B Validation Matrix

## Completed validation in this pass

### Retry / fallback infrastructure
- [x] `invoke_with_retry()` succeeds after transient failures
- [x] `invoke_with_retry()` raises after retry exhaustion

### Interview chain resilience
- [x] Structured-output path is attempted first
- [x] Interview chain falls back to parser-based chain when structured output fails
- [x] Structured path retries according to configured retry count

### Evaluation chain resilience
- [x] Structured-output path is attempted first
- [x] Evaluation chain falls back to parser-based chain when structured output fails
- [x] Structured path retries according to configured retry count

### Service-layer deterministic logic
- [x] Interview initial state creation
- [x] Coverage update behavior
- [x] Phase transition behavior
- [x] Hint decision behavior
- [x] Deterministic evaluation scoring
- [x] Competency threshold mapping

## Test command
```bash
cd backend-python
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## Current result
- Passing tests: 11
- Focus: backend unit tests for Phase 2 resilience + service logic

## Remaining recommended validation
- Add provider-specific integration tests in a fully provisioned environment with `pydantic`, `python-dotenv`, and LangChain packages installed
- Add prompt snapshot / golden-file tests for versioned prompts
- Add one end-to-end backend API test for `/api/interview/respond` and `/api/interview/evaluate`
