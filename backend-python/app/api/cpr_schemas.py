from typing import Any, Literal

from pydantic import BaseModel, Field


class TargetCompressionRate(BaseModel):
    min: int
    max: int


class CprScenarioPayload(BaseModel):
    id: str
    title: str
    difficulty: str
    emergency_type: str = Field(alias='emergencyType')
    background: str
    required_first_steps: list[str] = Field(alias='requiredFirstSteps')
    common_mistakes: list[str] = Field(alias='commonMistakes')
    escalation_conditions: list[str] = Field(alias='escalationConditions')
    target_compression_rate: TargetCompressionRate = Field(alias='targetCompressionRate')
    training_mode: str | None = Field(default=None, alias='trainingMode')


class CprChecklistItemPayload(BaseModel):
    id: str
    label: str
    completed: bool
    detail: str


class CprObservationPayload(BaseModel):
    timestamp: int
    compression_rate: float = Field(alias='compressionRate')
    wrist_y: float | None = Field(default=None, alias='wristY')
    shoulder_width: float | None = Field(default=None, alias='shoulderWidth')
    hands_visible: bool = Field(alias='handsVisible')
    arms_straight: bool = Field(alias='armsStraight')
    hands_centered: bool = Field(alias='handsCentered')
    recoil_complete: bool | None = Field(default=None, alias='recoilComplete')
    depth_proxy: float | None = Field(default=None, alias='depthProxy')
    tracking_confidence: float | None = Field(default=None, alias='trackingConfidence')
    peak_timestamps: list[int] | None = Field(default=None, alias='peakTimestamps')


class CprCycleStatsPayload(BaseModel):
    cycle_number: int = Field(alias='cycleNumber')
    average_rate: float = Field(alias='averageRate')
    rate_consistency: float = Field(alias='rateConsistency')
    compression_count: int = Field(alias='compressionCount')
    duration_seconds: float = Field(alias='durationSeconds')


class CprSessionStatePayload(BaseModel):
    module: Literal['CPR']
    status: str
    started_at: int = Field(alias='startedAt')
    scenario_id: str = Field(alias='scenarioId')
    current_phase: str = Field(alias='currentPhase')
    current_rate: float = Field(alias='currentRate')
    average_rate: float = Field(alias='averageRate')
    max_rate: float = Field(alias='maxRate')
    elapsed_seconds: float = Field(alias='elapsedSeconds')
    checklist: list[CprChecklistItemPayload]
    visible_ratio: float = Field(alias='visibleRatio')
    straight_arm_ratio: float = Field(alias='straightArmRatio')
    centered_ratio: float = Field(alias='centeredRatio')
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH'] = Field(alias='riskLevel')
    observations: list[dict[str, Any]] = Field(default_factory=list)
    training_mode: str | None = Field(default=None, alias='trainingMode')
    current_cycle: int | None = Field(default=None, alias='currentCycle')
    cycle_history: list[CprCycleStatsPayload] | None = Field(default=None, alias='cycleHistory')
    compression_fraction: float | None = Field(default=None, alias='compressionFraction')
    rate_consistency: float | None = Field(default=None, alias='rateConsistency')
    recoil_ratio: float | None = Field(default=None, alias='recoilRatio')
    depth_proxy_average: float | None = Field(default=None, alias='depthProxyAverage')
    compression_count: int | None = Field(default=None, alias='compressionCount')


class CprRuntimeStatePayload(BaseModel):
    cycle_start_timestamp: int | None = Field(default=None, alias='cycleStartTimestamp')
    cycle_compression_count: int | None = Field(default=None, alias='cycleCompressionCount')
    cycle_rates: list[float] | None = Field(default=None, alias='cycleRates')
    total_compression_time_ms: int | None = Field(default=None, alias='totalCompressionTimeMs')
    last_compression_timestamp: int | None = Field(default=None, alias='lastCompressionTimestamp')
    was_compressing: bool | None = Field(default=None, alias='wasCompressing')
    inter_compression_intervals: list[float] | None = Field(default=None, alias='interCompressionIntervals')
    last_counted_peak_timestamp: int | None = Field(default=None, alias='lastCountedPeakTimestamp')
    compressions_since_ventilation: int | None = Field(default=None, alias='compressionsSinceVentilation')
    ventilation_breath_count: int | None = Field(default=None, alias='ventilationBreathCount')


class CprStateEnvelopePayload(BaseModel):
    session_state: CprSessionStatePayload = Field(alias='sessionState')
    runtime_state: CprRuntimeStatePayload | None = Field(default=None, alias='runtimeState')


class CprRubricPayload(BaseModel):
    weights: dict
    thresholds: dict


class CprDecisionRequest(BaseModel):
    session_state: CprSessionStatePayload = Field(alias='sessionState')


class CprEvaluateRequest(BaseModel):
    session_state: CprSessionStatePayload = Field(alias='sessionState')
    scenario: CprScenarioPayload
    rubric: CprRubricPayload


class CprRuntimeIngestRequest(BaseModel):
    scenario: CprScenarioPayload
    observation: CprObservationPayload
    state: CprStateEnvelopePayload | None = None


class CprRuntimeActionRequest(BaseModel):
    scenario: CprScenarioPayload
    state: CprStateEnvelopePayload
    action: str
    phase: str | None = None


class CprIngestRequest(BaseModel):
    scenario: CprScenarioPayload
    observation: CprObservationPayload | None = None
    state: CprStateEnvelopePayload | None = None
    action: str | None = None
    phase: str | None = None
