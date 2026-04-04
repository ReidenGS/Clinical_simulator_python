# Interview Frontend Audit

## Audit outcome
The main Interview UI flow now treats the Python backend as the authoritative path.

## What was changed
### `useInterviewSession.ts`
- backend `/api/interview/respond` remains the default path
- legacy frontend patient-response fallback is disabled by default
- legacy fallback is now dynamically imported only if explicitly re-enabled
- if backend orchestration is required but unavailable, the code now fails explicitly instead of silently behaving like the legacy architecture is normal

### `InterviewScreen.tsx`
- backend `/api/interview/evaluate` remains the default path
- legacy frontend evaluation is disabled by default
- legacy evaluation is dynamically imported only if explicitly re-enabled
- static import coupling to the legacy service file was removed from the main screen path

## Remaining legacy island
The following files still form a self-contained legacy island and are no longer part of the normal main-path imports:
- `src/modules/interview/services/interviewAiService.ts`
- `src/modules/interview/orchestration/DialogueOrchestrator.ts`
- `src/modules/interview/orchestration/DecisionEngine.ts`
- `src/modules/interview/evaluation/RubricEngine.ts`
- `src/modules/interview/evaluation/FeedbackGenerator.ts`
- `src/modules/interview/tracking/SessionStateTracker.ts`

## Recommendation
Next cleanup pass can either:
1. move these legacy files under `src/modules/interview/legacy/`
2. or remove them completely after backend endpoint confidence is considered sufficient
