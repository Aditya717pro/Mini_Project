from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus


class MappingSuggestionResponse(BaseModel):
    source: str
    target: str
    confidence: float
    status: str
    note: str


class EtlLogResponse(BaseModel):
    time: str
    level: str
    stage: str
    message: str


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
    progress: int
    stages: list[EtlStageResponse]
    logs: list[EtlLogResponse]
    startedAt: str
    finishedAt: str | None
    rowsIn: int
    rowsOut: int
    mappings: list[MappingSuggestionResponse]


class MappingDecisionInput(BaseModel):
    decision: str = Field(pattern="^(Approved|Unmapped)$")


class RunJobResponse(BaseModel):
    jobId: str
    status: str
    message: str
