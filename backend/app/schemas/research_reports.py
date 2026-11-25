from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchReportGenerateRequest(BaseModel):
    datasetId: str | None = Field(default=None, max_length=36)
    datasetVersionId: str | None = Field(default=None, max_length=36)
    etlJobId: str | None = Field(default=None, max_length=36)
    generationJobId: str | None = Field(default=None, max_length=36)
    generatedDatasetId: str | None = Field(default=None, max_length=36)
    comparisonId: str | None = Field(default=None, max_length=36)
    privacyEvaluationId: str | None = Field(default=None, max_length=36)
    utilityEvaluationId: str | None = Field(default=None, max_length=36)
    experimentId: str | None = Field(default=None, max_length=36)


class ResearchReportResponse(BaseModel):
    id: str
    reportId: str
    reportType: str
    title: str
    ownerId: str
    datasetId: str | None
    datasetVersionId: str | None
    experimentId: str | None
    comparisonId: str | None
    privacyEvaluationId: str | None
    utilityEvaluationId: str | None
    generationJobId: str | None
    generatedDatasetId: str | None
    fileChecksum: str | None
    fileSize: int | None
    templateVersion: str
    status: str
    error: str
    createdAt: str
    completedAt: str


class ResearchReportListResponse(BaseModel):
    items: list[ResearchReportResponse]
    total: int
    counts: dict[str, int]


class ResearchReportStatusResponse(BaseModel):
    reportId: str
    status: str
    error: str
    createdAt: str
    completedAt: str
