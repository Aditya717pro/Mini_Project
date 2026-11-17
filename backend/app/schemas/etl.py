from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus


class MappingSuggestionResponse(BaseModel):
    source: str
    target: str
    confidence: float
    status: str
    note: str
    inferredType: str = ""
    proposedTarget: str = ""
    decision: str | None = None
    decidedBy: str | None = None
    decidedAt: str | None = None


class EtlLogResponse(BaseModel):
    time: str
    level: str
    stage: str
    message: str
    details: dict = Field(default_factory=dict)


class EtlStageResponse(BaseModel):
    key: str
    label: str
    state: str
    detail: str


class EtlJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    datasetId: str
    datasetTitle: str
    status: JobStatus
    currentStage: str
    progress: int
    stages: list[EtlStageResponse]
    logs: list[EtlLogResponse]
    startedAt: str
    finishedAt: str | None
    rowsIn: int
    rowsOut: int
    mappings: list[MappingSuggestionResponse]
    profile: dict = Field(default_factory=dict)
    errorMessage: str | None = None
    approvedAt: str | None = None
    approvedBy: str | None = None
    rejectionReason: str | None = None
    transformationSummary: dict = Field(default_factory=dict)


class MappingDecisionInput(BaseModel):
    source: str = Field(min_length=1, max_length=255)
    decision: str = Field(pattern="^(Approved|Rejected|Unmapped)$")
    target: str | None = Field(default=None, max_length=120)
    note: str = Field(default="", max_length=500)


class MappingApprovalInput(BaseModel):
    note: str = Field(default="", max_length=500)


class JobDecisionInput(BaseModel):
    reason: str = Field(default="", max_length=1000)


class RunJobResponse(BaseModel):
    jobId: str
    status: str
    message: str
