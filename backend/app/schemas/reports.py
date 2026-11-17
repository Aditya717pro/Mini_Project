from pydantic import BaseModel, Field

from app.models.enums import RequestStatus, UserRole

QUALITY_DIMENSIONS = ("completeness", "validity", "consistency", "uniqueness", "typeCorrectness")


class QualityIssueResponse(BaseModel):
    id: str
    dimension: str
    severity: str
    field: str
    description: str
    affectedRecords: int
    recommendation: str


class QualityReportResponse(BaseModel):
    datasetId: str
    overall: int
    grade: str
    dimensions: dict[str, float]
    issues: list[QualityIssueResponse]
    assessedAt: str
    rulesVersion: str
    sampleSize: int
    method: str


class ReadinessCategoryResponse(BaseModel):
    key: str
    label: str
    score: int
    weight: float
    note: str


class ReadinessReportResponse(BaseModel):
    datasetId: str
    task: str
    overall: int
    verdict: str
    categories: list[ReadinessCategoryResponse]
    limitations: list[str]
    recommendations: list[str]
    assessedAt: str
    method: str


class ReadinessRequest(BaseModel):
    task: str = Field(min_length=3, max_length=250)


class RepresentativenessReportResponse(BaseModel):
    datasetId: str
    ageBands: list[dict]
    pregnancyStages: list[dict]
    paediatricGroups: list[dict]
    geography: list[dict]
    missingAttributes: list[dict]
    coverageNotes: list[str]
    assessedAt: str


class AccessRequestInput(BaseModel):
    projectTitle: str = Field(min_length=3, max_length=250)
    purpose: str = Field(min_length=10, max_length=3000)


class AccessDecisionInput(BaseModel):
    status: str = Field(pattern="^(Approved|Rejected)$")
    note: str = Field(default="", max_length=1000)


class AccessRequestResponse(BaseModel):
    id: str
    datasetId: str
    datasetTitle: str
    requester: str
    role: UserRole
    organisation: str
    purpose: str
    projectTitle: str
    requestedAt: str
    status: RequestStatus
    decidedAt: str | None
    reviewer: str | None
    decisionNote: str | None
    direction: str
