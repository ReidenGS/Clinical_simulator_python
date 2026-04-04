from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.schemas import JsonRequest, TextRequest, TtsRequest
from app.api.interview_schemas import InterviewRespondRequest
from app.api.interview_evaluate_schemas import InterviewEvaluateRequest
from app.api.cpr_schemas import CprDecisionRequest, CprEvaluateRequest, CprIngestRequest, CprRuntimeIngestRequest, CprRuntimeActionRequest
from app.services.ai_service import AIService
from app.services.interview_service import InterviewService
from app.services.interview_evaluate_service import InterviewEvaluateService
from app.services.cpr_service import CprService


router = APIRouter(prefix="/api")
service = AIService()
interview_service = InterviewService()
interview_evaluate_service = InterviewEvaluateService()
cpr_service = CprService()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ai/text")
def ai_text(payload: TextRequest) -> dict[str, str]:
    try:
        text = service.generate_text(
            provider=payload.provider,
            system_prompt=payload.system_prompt,
            messages=[m.model_dump() for m in payload.messages],
            temperature=payload.temperature,
            model=payload.model,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ai/json")
def ai_json(payload: JsonRequest) -> dict[str, str]:
    try:
        text = service.generate_json(**payload.model_dump())
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/interview/respond")
def interview_respond(payload: InterviewRespondRequest):
    try:
        result = interview_service.process_turn(
            case_data=payload.case_data.model_dump(by_alias=True),
            history=[m.model_dump() for m in payload.history],
            student_input=payload.student_input,
            state=payload.session_state.model_dump(by_alias=True) if payload.session_state else None,
            config=payload.config.model_dump(by_alias=True),
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/interview/evaluate")
def interview_evaluate(payload: InterviewEvaluateRequest):
    try:
        result = interview_evaluate_service.evaluate(
            session_state=payload.session_state.model_dump(by_alias=True),
            diagnosis=payload.diagnosis,
            case_data=payload.case_data.model_dump(by_alias=True),
            rubric_config=payload.rubric_config.model_dump(by_alias=True),
            config=payload.config.model_dump(by_alias=True),
            difficulty_cases=payload.difficulty_cases,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cpr/runtime/ingest")
def cpr_runtime_ingest(payload: CprRuntimeIngestRequest):
    try:
        result = cpr_service.ingest(
            observation=payload.observation.model_dump(by_alias=True, exclude_none=True),
            scenario=payload.scenario.model_dump(by_alias=True),
            state=payload.state.model_dump(by_alias=True) if payload.state else None,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cpr/runtime/action")
def cpr_runtime_action(payload: CprRuntimeActionRequest):
    try:
        result = cpr_service.apply_action(
            scenario=payload.scenario.model_dump(by_alias=True),
            state=payload.state.model_dump(by_alias=True),
            action=payload.action,
            phase=payload.phase,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Compatibility shim for older CPR Phase 2A clients. New callers should use
# `/api/cpr/runtime/ingest` for observations and `/api/cpr/runtime/action` for actions.
@router.post("/cpr/ingest")
def cpr_ingest(payload: CprIngestRequest):
    try:
        scenario = payload.scenario.model_dump(by_alias=True)
        state = payload.state.model_dump(by_alias=True) if payload.state else None

        if payload.action:
            if not state:
                raise HTTPException(status_code=400, detail='state is required for CPR action requests')
            result = cpr_service.apply_action(
                scenario=scenario,
                state=state,
                action=payload.action,
                phase=payload.phase,
            )
            return JSONResponse(content=result)

        if not payload.observation:
            raise HTTPException(status_code=400, detail='observation is required for CPR ingest requests')

        result = cpr_service.ingest(
            observation=payload.observation.model_dump(by_alias=True, exclude_none=True),
            scenario=scenario,
            state=state,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cpr/decide")
def cpr_decide(payload: CprDecisionRequest):
    try:
        result = cpr_service.decide(payload.session_state.model_dump(by_alias=True))
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cpr/evaluate")
def cpr_evaluate(payload: CprEvaluateRequest):
    try:
        result = cpr_service.evaluate(
            payload.session_state.model_dump(by_alias=True),
            payload.scenario.model_dump(by_alias=True),
            payload.rubric.model_dump(by_alias=True),
        )
        return JSONResponse(content=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tts/qwen")
async def tts_qwen(payload: TtsRequest):
    try:
        data = await service.qwen_tts(
            text=payload.text,
            voice=payload.voice,
            model=payload.model,
            api_key=payload.api_key,
            base_url=payload.base_url,
            extra=payload.extra,
        )
        return JSONResponse(content=data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
