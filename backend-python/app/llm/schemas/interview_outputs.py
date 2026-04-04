from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CoverageDimension = Literal['HPC', 'PMH', 'DH', 'FH', 'SH', 'ROS', 'ICE', 'COMM']
StudentApproach = Literal['open', 'closed', 'leading', 'empathetic']
ClinicalRelevance = Literal['high', 'medium', 'low', 'off_track']


class TopicCoveredOutput(BaseModel):
    dimension: CoverageDimension
    sub_item: str = Field(alias='subItem')
    confidence: float = 0.0
    evidence: str = ''


class InterviewExtractionOutput(BaseModel):
    topics_covered: list[TopicCoveredOutput] = Field(default_factory=list, alias='topicsCovered')
    student_approach: StudentApproach | None = Field(default=None, alias='studentApproach')
    clinical_relevance: ClinicalRelevance | None = Field(default=None, alias='clinicalRelevance')


class PatientTurnOutput(BaseModel):
    patient_response: str = Field(alias='patientResponse')
    extraction: InterviewExtractionOutput | None = None


class DimensionEvaluationOutput(BaseModel):
    raw_score: int = Field(default=50, alias='rawScore')
    feedback: str = 'Evaluation unavailable for this dimension.'
    evidence: list[str] = Field(default_factory=list)
