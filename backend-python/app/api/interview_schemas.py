from typing import Any, Literal

from pydantic import BaseModel, Field


CoverageDimension = Literal['HPC', 'PMH', 'DH', 'FH', 'SH', 'ROS', 'ICE', 'COMM']
InterviewPhase = Literal['OPENING', 'HISTORY_TAKING', 'GUIDED_INQUIRY', 'DIAGNOSIS_READY']


class MustAskItem(BaseModel):
    dimension: CoverageDimension
    sub_item: str = Field(alias='subItem')
    critical: bool
    hint: str | None = None


class HiddenDetails(BaseModel):
    duration: str
    triggers: str
    past_history: str = Field(alias='pastHistory')
    associated_symptoms: str = Field(alias='associatedSymptoms')
    lifestyle: str
    family_history: str | None = Field(default=None, alias='familyHistory')
    drug_history: str | None = Field(default=None, alias='drugHistory')
    review_of_systems: str | None = Field(default=None, alias='reviewOfSystems')


class PatientCasePayload(BaseModel):
    id: str
    name: str
    age: int
    gender: str
    difficulty: Literal['easy', 'medium', 'hard']
    initial_complaint: str = Field(alias='initialComplaint')
    hidden_details: HiddenDetails = Field(alias='hiddenDetails')
    correct_diagnosis: str = Field(alias='correctDiagnosis')
    must_ask_items: list[MustAskItem] = Field(alias='mustAskItems')
    personality: str | None = None
    speech_patterns: list[str] | None = Field(default=None, alias='speechPatterns')


class FrontendMessage(BaseModel):
    role: Literal['student', 'patient', 'coach']
    text: str


class TopicCovered(BaseModel):
    dimension: CoverageDimension
    sub_item: str = Field(alias='subItem')
    confidence: float
    evidence: str


class ExtractedInfo(BaseModel):
    topics_covered: list[TopicCovered] = Field(default_factory=list, alias='topicsCovered')
    student_approach: str | None = Field(default=None, alias='studentApproach')
    clinical_relevance: str | None = Field(default=None, alias='clinicalRelevance')


class DimensionCoverage(BaseModel):
    dimension: CoverageDimension
    covered_items: list[str] = Field(default_factory=list, alias='coveredItems')
    total_items: int = Field(alias='totalItems')
    percentage: int


class SessionEvent(BaseModel):
    type: str
    turn: int
    timestamp: int
    data: dict[str, Any] | None = None


class SessionStatePayload(BaseModel):
    phase: InterviewPhase
    turn_count: int = Field(alias='turnCount')
    turns_without_progress: int = Field(alias='turnsWithoutProgress')
    dimension_coverages: list[DimensionCoverage] = Field(alias='dimensionCoverages')
    overall_coverage: int = Field(alias='overallCoverage')
    events: list[SessionEvent] = Field(default_factory=list)
    extractions: list[ExtractedInfo] = Field(default_factory=list)
    rag_case_id: str | None = Field(default=None, alias='ragCaseId')
    rag_case_summary: str | None = Field(default=None, alias='ragCaseSummary')
    session_id: str | None = Field(default=None, alias='sessionId')


class AIConfigPayload(BaseModel):
    text_provider: Literal['OPENAI', 'GEMINI', 'QWEN'] = Field(alias='textProvider')
    text_api_key: str = Field(default='', alias='textApiKey')
    text_base_url: str | None = Field(default=None, alias='textBaseUrl')
    text_model: str | None = Field(default=None, alias='textModel')


class InterviewRespondRequest(BaseModel):
    case_data: PatientCasePayload = Field(alias='caseData')
    history: list[FrontendMessage]
    student_input: str = Field(alias='studentInput')
    session_state: SessionStatePayload | None = Field(default=None, alias='sessionState')
    config: AIConfigPayload
