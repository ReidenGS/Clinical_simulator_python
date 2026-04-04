# Interview Frontend Boundary

## Current authoritative path
The Interview module should now be understood as:
- **frontend**: UI, microphone, transcript input, presentation, local display state
- **backend**: response generation, extraction parsing, coverage tracking, state progression, decision logic, evaluation

In other words, the frontend is no longer the source of truth for Interview orchestration.

## Frontend legacy fallback policy
Legacy frontend interview orchestration and evaluation code still exists, but it should be treated as:
- fallback only
- disabled by default
- isolated from the normal execution path
- a temporary safety net rather than a supported primary architecture

## Remaining legacy files
- `src/modules/interview/services/interviewAiService.ts`
- `src/modules/interview/orchestration/DialogueOrchestrator.ts`
- `src/modules/interview/orchestration/DecisionEngine.ts`
- `src/modules/interview/evaluation/RubricEngine.ts`
- `src/modules/interview/evaluation/FeedbackGenerator.ts`
- `src/modules/interview/tracking/SessionStateTracker.ts`

## Boundary rule
When modifying Interview behavior going forward:
1. prefer backend route changes first
2. keep frontend focused on UX and display
3. do not reintroduce frontend-led orchestration as the default path
4. only touch legacy fallback code if explicitly preserving emergency fallback behavior

## Recommended cleanup direction
- keep legacy fallback import paths lazy/dynamic
- avoid static imports from InterviewScreen / useInterviewSession for legacy code
- eventually move legacy interview fallback files into a clearly named `legacy/` subtree or remove them after endpoint confidence is high
