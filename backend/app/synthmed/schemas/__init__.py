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
    generationMode: str = "Unconditional"
    selectedModel: str = "CTGAN"
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


class SynthMedCondition(BaseModel):
    column: str
    operator: str = "eq"
    value: Any | None = None
    values: list[Any] | None = None
    min: float | None = None
    max: float | None = None
    numRows: int = Field(default=1, ge=1)


class SynthMedClinicalVariable(BaseModel):
    column: str
    measurement: str
    unit: str = ""
    context: str = ""
    referenceKey: str = ""
    ageColumn: str = ""
    sexColumn: str = ""
    pregnantColumn: str = ""
    ageYears: float | None = None
    sex: str = ""
    pregnant: bool | None = None
    enabled: bool = True


class SynthMedClinicalRule(BaseModel):
    disease: str
    column: str
    min: float | None = None
    max: float | None = None
    source: str = ""
    reviewed: bool = False


class SynthMedReferenceOverride(BaseModel):
    key: str
    active: bool = True
    lower: float | None = None
    upper: float | None = None
    plausibleLower: float | None = None
    plausibleUpper: float | None = None
    approvalStatus: Literal["Approved", "PendingReview", "Unavailable"] = "Approved"
    sourceOrganization: str = ""
    sourceUrl: str = ""
    citation: str = ""
    version: str = ""
    date: str = ""


class SynthMedMedicalProfileResponse(BaseModel):
    sourceDatasetId: str
    datasetName: str
    profile: dict[str, Any]
    message: str = ""


class SynthMedClinicalReferenceListResponse(BaseModel):
    references: list[dict[str, Any]]
    count: int
    message: str = ""


class SynthMedClinicalValidationRequest(BaseModel):
    sourceDatasetId: str
    generationProfile: Literal["Standard", "NormalRange", "ClinicalDistribution"] = "Standard"
    clinicalVariables: list[SynthMedClinicalVariable] = Field(default_factory=list)
    referenceOverrides: list[SynthMedReferenceOverride] = Field(default_factory=list)
    diseaseRules: list[SynthMedClinicalRule] = Field(default_factory=list)
    approvedOutputColumns: list[str] | None = None
    enforceStrictSchema: bool = False


class SynthMedClinicalValidationResponse(BaseModel):
    sourceDatasetId: str
    generatedDatasetId: str = ""
    generationProfile: str
    report: dict[str, Any]
    schemaValidation: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SynthMedEligibleColumn(BaseModel):
    name: str
    sdtype: str
    missingCount: int
    uniqueCount: int


class SynthMedIneligibleColumn(BaseModel):
    name: str
    reason: str


class SynthMedModelCapability(BaseModel):
    model: str
    sdvClass: str
    samplingApi: str
    conditionalSampling: bool
    multipleConditions: bool
    exactEquality: bool
    rangeOperators: bool
    primaryKeyConditions: bool
    missingValueConditions: bool
    samplingStrategy: str
    notes: list[str] = Field(default_factory=list)


class SynthMedConditionValidationRequest(BaseModel):
    sourceDatasetId: str
    model: str = "CTGAN"
    conditions: list[SynthMedCondition] = Field(default_factory=list)
    recordCount: int | None = Field(default=None, ge=1)
    selectedColumns: list[str] | None = None
    identifierColumns: list[str] = Field(default_factory=list)
    primaryKey: str | None = None
    categoricalColumns: list[str] = Field(default_factory=list)
    numericalColumns: list[str] = Field(default_factory=list)
    categoricalValues: dict[str, list[str]] = Field(default_factory=dict)
    numericRanges: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    preserveMissingness: bool = True
    generationProfile: Literal["Standard", "NormalRange", "ClinicalDistribution"] = "Standard"
    clinicalVariables: list[SynthMedClinicalVariable] = Field(default_factory=list)
    referenceOverrides: list[SynthMedReferenceOverride] = Field(default_factory=list)
    diseaseRules: list[SynthMedClinicalRule] = Field(default_factory=list)
    approvedOutputColumns: list[str] | None = None
    enforceStrictSchema: bool = False
    maxSamplingAttempts: int = Field(default=4, ge=1, le=20)


class SynthMedConditionValidationResponse(BaseModel):
    valid: bool
    model: str
    capabilities: SynthMedModelCapability
    eligibleColumns: list[SynthMedEligibleColumn] = Field(default_factory=list)
    ineligibleColumns: list[SynthMedIneligibleColumn] = Field(default_factory=list)
    normalizedConditions: list[dict[str, Any]] = Field(default_factory=list)
    samplingPlan: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SynthMedModelCapabilityListResponse(BaseModel):
    models: list[SynthMedModelCapability]
    sdvVersion: str
    message: str = ""


class SynthMedDatasetColumnsResponse(BaseModel):
    sourceDatasetId: str
    totalColumns: int
    eligibleColumns: list[SynthMedEligibleColumn] = Field(default_factory=list)
    ineligibleColumns: list[SynthMedIneligibleColumn] = Field(default_factory=list)
    numericalColumns: list[str] = Field(default_factory=list)
    categoricalColumns: list[str] = Field(default_factory=list)
    booleanColumns: list[str] = Field(default_factory=list)
    datetimeColumns: list[str] = Field(default_factory=list)
    potentialIdentifierColumns: list[str] = Field(default_factory=list)
    generationReady: bool
    guidance: str = ""


class SynthMedGenerationStartRequest(BaseModel):
    sourceDatasetId: str
    datasetName: str = ""
    model: str = "CTGAN"
    generationMode: Literal["Unconditional", "Conditional"] = "Unconditional"
    conditions: list[SynthMedCondition] = Field(default_factory=list)
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
    generationProfile: Literal["Standard", "NormalRange", "ClinicalDistribution"] = "Standard"
    clinicalVariables: list[SynthMedClinicalVariable] = Field(default_factory=list)
    referenceOverrides: list[SynthMedReferenceOverride] = Field(default_factory=list)
    diseaseRules: list[SynthMedClinicalRule] = Field(default_factory=list)
    approvedOutputColumns: list[str] | None = None
    enforceStrictSchema: bool = False
    maxSamplingAttempts: int = Field(default=4, ge=1, le=20)


class SynthMedGenerationJobResponse(BaseModel):
    id: str
    sourceDatasetId: str
    generatedDatasetId: str = ""
    status: str
    modelName: str
    generationMode: str = "Unconditional"
    selectedModel: str = "CTGAN"
    epochs: int
    batchSize: int
    seed: int | None = None
    requestedRecordCount: int
    generatedRecordCount: int = 0
    trainingDurationSeconds: float | None = None
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    conditionValidation: dict[str, Any] = Field(default_factory=dict)
    conditionSatisfaction: dict[str, Any] = Field(default_factory=dict)
    createdAt: str
    startedAt: str = ""
    completedAt: str = ""
    error: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    generationProfile: str = "Standard"
    clinicalValidation: dict[str, Any] = Field(default_factory=dict)
    schemaValidation: dict[str, Any] = Field(default_factory=dict)


class SynthMedGeneratedDatasetDetailResponse(SynthMedGeneratedDatasetResponse):
    generationJobId: str = ""
    trainingDurationSeconds: float | None = None
    availableFormats: list[str] = Field(default_factory=list)
    reportTypes: list[str] = Field(default_factory=list)
    trainingConfig: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    conditionSatisfaction: dict[str, Any] = Field(default_factory=dict)
    generationProfile: str = "Standard"
    clinicalValidation: dict[str, Any] = Field(default_factory=dict)
    schemaValidation: dict[str, Any] = Field(default_factory=dict)


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


class SynthMedComparisonCreateRequest(BaseModel):
    sourceDatasetId: str
    generatedDatasetId: str
    name: str = ""


class SynthMedComparisonColumnMetric(BaseModel):
    name: str
    sourceKind: str
    syntheticKind: str
    shared: bool = True
    similarity: float | None = None
    metric: str = ""
    sourceMissingPercentage: float = 0.0
    syntheticMissingPercentage: float = 0.0
    sourceUniqueCount: int = 0
    syntheticUniqueCount: int = 0
    sourceStats: dict[str, Any] = Field(default_factory=dict)
    syntheticStats: dict[str, Any] = Field(default_factory=dict)


class SynthMedComparisonSummary(BaseModel):
    sourceRows: int
    syntheticRows: int
    rowDifference: int
    sourceColumns: int
    syntheticColumns: int
    sharedColumns: int
    onlySourceColumns: list[str] = Field(default_factory=list)
    onlySyntheticColumns: list[str] = Field(default_factory=list)
    overallSimilarity: float | None = None
    numericSimilarity: float | None = None
    categoricalSimilarity: float | None = None
    missingnessDeltaPercentage: float = 0.0


class SynthMedComparisonChart(BaseModel):
    column: str
    kind: str
    title: str
    points: list[dict[str, Any]] = Field(default_factory=list)


class SynthMedComparisonClinical(BaseModel):
    generationProfile: str
    sourceMedicalProfile: dict[str, Any] = Field(default_factory=dict)
    syntheticMedicalProfile: dict[str, Any] = Field(default_factory=dict)
    sourceValidation: dict[str, Any] = Field(default_factory=dict)
    syntheticValidation: dict[str, Any] = Field(default_factory=dict)
    schemaValidation: dict[str, Any] = Field(default_factory=dict)
    rejectionSampling: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class SynthMedComparisonListItem(BaseModel):
    id: str
    name: str
    sourceDatasetId: str
    sourceDatasetName: str
    generatedDatasetId: str
    generatedDatasetName: str
    summary: SynthMedComparisonSummary
    createdAt: str
    createdBy: str
    reportAvailable: bool = False
    generatedMetadata: dict[str, Any] = Field(default_factory=dict)


class SynthMedComparisonResponse(SynthMedComparisonListItem):
    method: str
    columns: list[SynthMedComparisonColumnMetric] = Field(default_factory=list)
    charts: list[SynthMedComparisonChart] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generatedMetadata: dict[str, Any] = Field(default_factory=dict)
    clinical: SynthMedComparisonClinical | None = None
