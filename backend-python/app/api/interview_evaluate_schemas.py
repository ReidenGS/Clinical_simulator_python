from typing import Any

from pydantic import BaseModel, Field

from app.api.interview_schemas import AIConfigPayload, PatientCasePayload, SessionStatePayload


class RubricDimensionPayload(BaseModel):
    id: str
    name: str
    weight: float
    description: str
    scoring_method: str = Field(alias='scoringMethod')


class RubricConfigPayload(BaseModel):
    dimensions: list[RubricDimensionPayload]
    competency_thresholds: dict[str, int] = Field(alias='competencyThresholds')


class InterviewEvaluateRequest(BaseModel):
    session_state: SessionStatePayload = Field(alias='sessionState')
    diagnosis: str
    case_data: PatientCasePayload = Field(alias='caseData')
    rubric_config: RubricConfigPayload = Field(alias='rubricConfig')
    config: AIConfigPayload
    difficulty_cases: dict[str, list[dict[str, Any]]] | None = Field(default=None, alias='difficultyCases')
