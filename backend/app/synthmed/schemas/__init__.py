from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SynthMedSourceDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    datasetName: str
    description: str = ""
    originalFilename: str
    fileFormat: str
    fileSizeBytes: int
    uploadDate: str
    uploadedBy: str
    uploadStatus: str
    checksumSha256: str
    rowCount: int = 0
    columnCount: int = 0


class SynthMedSourceUploadResponse(BaseModel):
    dataset: SynthMedSourceDatasetResponse
    message: str


class SynthMedGeneratedDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    sourceDatasetId: str = ""
    datasetName: str
    sourceDatasetName: str

    generationMethod: str
    recordCount: int
    columnCount: int
    generationDate: str
    fileFormat: str
    fileSizeBytes: int
    fileName: str = ""
    status: str


class SynthMedDownloadsResponse(BaseModel):
    sources: list[SynthMedSourceDatasetResponse] = Field(default_factory=list)
    generated: list[SynthMedGeneratedDatasetResponse] = Field(default_factory=list)


class SynthMedColumnAnalysis(BaseModel):
    name: str
    dtype: str
    kind: str
    missingCount: int
    missingPercentage: float
    uniqueCount: int
    constant: bool
    potentialIdentifier: bool
    quasiIdentifier: bool


class SynthMedGenerationAnalysisResponse(BaseModel):
    sourceDatasetId: str
    datasetName: str
    originalFilename: str
    totalRecords: int
    totalColumns: int
    columns: list[SynthMedColumnAnalysis]
    numericalColumns: list[str] = Field(default_factory=list)
    categoricalColumns: list[str] = Field(default_factory=list)
    datetimeColumns: list[str] = Field(default_factory=list)
    booleanColumns: list[str] = Field(default_factory=list)
    potentialIdentifierColumns: list[str] = Field(default_factory=list)
    quasiIdentifierColumns: list[str] = Field(default_factory=list)
    constantColumns: list[str] = Field(default_factory=list)
    duplicateRecords: int = 0
    generationReady: bool
    guidance: str = ""


class SynthMedGenerationStartRequest(BaseModel):
    sourceDatasetId: str
    datasetName: str = ""
    selectedColumns: list[str] | None = None
    categoricalColumns: list[str] = Field(default_factory=list)
    numericalColumns: list[str] = Field(default_factory=list)
    identifierColumns: list[str] = Field(default_factory=list)
    primaryKey: str | None = None
    seed: int | None = None
    epochs: int = Field(default=20, ge=1, le=10000)
    batchSize: int = Field(default=100, ge=20, le=10000, multiple_of=10)
    recordCount: int = Field(default=1000, ge=1, le=1000000)
    preserveMissingness: bool = True
    numericRanges: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    categoricalValues: dict[str, list[str]] = Field(default_factory=dict)


class SynthMedGenerationJobResponse(BaseModel):
    id: str
    sourceDatasetId: str
    generatedDatasetId: str = ""
    status: str
    modelName: str
    epochs: int
    batchSize: int
    seed: int | None = None
    requestedRecordCount: int
    generatedRecordCount: int = 0
    trainingDurationSeconds: float | None = None
    createdAt: str
    startedAt: str = ""
    completedAt: str = ""
    error: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class SynthMedGeneratedDatasetDetailResponse(SynthMedGeneratedDatasetResponse):
    generationJobId: str = ""
    trainingDurationSeconds: float | None = None
    availableFormats: list[str] = Field(default_factory=list)
    reportTypes: list[str] = Field(default_factory=list)
    trainingConfig: dict[str, Any] = Field(default_factory=dict)


class SynthMedGeneratedPreviewResponse(BaseModel):
    generatedDatasetId: str
    columns: list[str]
    rows: list[dict[str, Any]]
    totalRecords: int
    page: int
    pageSize: int


class SynthMedEvaluationReportResponse(BaseModel):
    id: str
    generatedDatasetId: str
    reportType: str
    method: str
    score: float | None = None
    report: dict[str, Any]
    createdAt: str


class SynthMedExportRequest(BaseModel):
    format: Literal["CSV", "XLSX", "JSON"] = "CSV"


class SynthMedExportResponse(BaseModel):
    generatedDatasetId: str
    format: str
    fileName: str
