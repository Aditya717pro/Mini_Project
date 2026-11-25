from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccessClassification
from app.schemas.dataset import DOMAIN_PATTERN, DatasetSummary


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
    repositoryRegistrationStatus: str = "Not registered"
    repositoryDatasetId: str | None = None
    repositoryDatasetTitle: str | None = None


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
    sourcePreservingMode: bool = False
    ageToleranceYears: int = Field(default=5, ge=0, le=120)
    numericTolerances: dict[str, float] = Field(default_factory=dict)
    numericTolerance: float | None = Field(default=None, ge=0)
    numericTolerancePercent: float | None = Field(default=None, ge=0)


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
    sourcePreservingMode: bool = False
    ageToleranceYears: int = Field(default=5, ge=0, le=120)
    numericTolerances: dict[str, float] = Field(default_factory=dict)
    numericTolerance: float | None = Field(default=None, ge=0)
    numericTolerancePercent: float | None = Field(default=None, ge=0)


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
    sourcePreservingMode: bool = False
    ageToleranceYears: int = 5
    validationStatus: str = ""
    sourcePreservation: dict[str, Any] = Field(default_factory=dict)


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
    sourcePreservingMode: bool = False
    ageToleranceYears: int = 5
    validationStatus: str = ""
    sourcePreservation: dict[str, Any] = Field(default_factory=dict)


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
    sourcePreservation: dict[str, Any] = Field(default_factory=dict)
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


class SynthMedUtilityTrainTestSplit(BaseModel):
    testSize: float = Field(default=0.2, ge=0.1, le=0.5)
    randomSeed: int = Field(default=42, ge=0)
    stratify: bool = True


class SynthMedUtilityEvaluationCreateRequest(BaseModel):
    sourceDatasetId: str
    generatedDatasetId: str
    evaluationName: str = ""
    evaluationType: Literal["TSTR", "TRTR", "BOTH"] = "BOTH"
    modelName: Literal[
        "LogisticRegression",
        "RandomForestClassifier",
        "DecisionTreeClassifier",
        "GradientBoostingClassifier",
        "LinearRegression",
        "Ridge",
        "RandomForestRegressor",
        "GradientBoostingRegressor",
    ]
    targetColumn: str
    featureColumns: list[str] = Field(default_factory=list)
    trainTestSplit: SynthMedUtilityTrainTestSplit = Field(default_factory=SynthMedUtilityTrainTestSplit)
    preprocessing: dict[str, Any] = Field(default_factory=dict)


class SynthMedUtilityEvaluationResponse(BaseModel):
    id: str
    sourceDatasetId: str
    generatedDatasetId: str
    status: str
    evaluationName: str
    evaluationType: str
    modelName: str
    targetColumn: str
    featureColumns: list[str] = Field(default_factory=list)
    trainTestSplit: dict[str, Any] = Field(default_factory=dict)
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    reportAvailable: bool = False
    reportCsvAvailable: bool = False
    reportPdfAvailable: bool = False
    error: str = ""
    createdAt: str = ""
    startedAt: str = ""
    completedAt: str = ""
    report: dict[str, Any] | None = None


class SynthMedVersionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    ownerId: str
    datasetKind: str
    logicalDatasetId: str = ""
    sourceDatasetId: str | None = None
    generatedDatasetId: str | None = None
    parentVersionId: str | None = None
    versionNumber: int
    versionLabel: str
    isActive: bool
    datasetName: str
    fileFormat: str
    storedPath: str
    checksumSha256: str
    fileSizeBytes: int
    recordCount: int
    columnCount: int
    datasetSchema: dict[str, Any] = Field(default_factory=dict)
    missingSummary: dict[str, Any] = Field(default_factory=dict)
    distributionSummary: dict[str, Any] = Field(default_factory=dict)
    transformHistory: list[dict[str, Any]] = Field(default_factory=list)
    validationSummary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    restoredFromVersionId: str | None = None
    createdAt: str = ""
    updatedAt: str = ""


class SynthMedLineageResponse(BaseModel):
    id: str
    eventType: str
    parentResourceType: str
    parentResourceId: str
    childResourceType: str
    childResourceId: str
    sourceDatasetId: str | None = None
    generatedDatasetId: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str = ""


class SynthMedDatasetLineageResponse(BaseModel):
    datasetId: str
    versions: list[SynthMedVersionResponse] = Field(default_factory=list)
    lineage: list[SynthMedLineageResponse] = Field(default_factory=list)


class SynthMedVersionCompareRequest(BaseModel):
    versionAId: str
    versionBId: str


class SynthMedExperimentCreateRequest(BaseModel):
    name: str
    description: str = ""
    status: str = "Draft"
    sourceDatasetId: str | None = None
    sourceVersionId: str | None = None
    generatedDatasetId: str | None = None
    generatedVersionId: str | None = None
    generationJobId: str | None = None
    configurationSnapshotId: str | None = None
    comparisonId: str | None = None
    utilityEvaluationId: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SynthMedConfigSnapshotResponse(BaseModel):
    id: str
    ownerId: str
    sourceDatasetId: str | None = None
    jobId: str | None = None
    modelName: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    configHash: str = ""
    isImmutable: bool = True
    createdAt: str = ""


class SynthMedExperimentResponse(BaseModel):
    id: str
    ownerId: str
    name: str
    description: str = ""
    status: str
    sourceDatasetId: str | None = None
    sourceVersionId: str | None = None
    generatedDatasetId: str | None = None
    generatedVersionId: str | None = None
    generationJobId: str | None = None
    configurationSnapshotId: str | None = None
    comparisonId: str | None = None
    utilityEvaluationId: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    configurationSnapshot: SynthMedConfigSnapshotResponse | None = None
    lineage: list[SynthMedLineageResponse] = Field(default_factory=list)
    privacyReport: dict[str, Any] = Field(default_factory=dict)
    utilityEvaluation: dict[str, Any] = Field(default_factory=dict)
    comparisonSummary: dict[str, Any] = Field(default_factory=dict)
    reportAvailability: dict[str, bool] = Field(default_factory=dict)
    createdAt: str = ""
    updatedAt: str = ""


class SynthMedGeneratedDatasetRegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=3, max_length=250)
    description: str = Field(default="", max_length=5000)
    domain: str = Field(pattern=DOMAIN_PATTERN)
    access: AccessClassification = AccessClassification.CONTROLLED
    tags: list[str] = Field(default_factory=list, max_length=30)
    age_range: str = Field(default="", alias="ageRange", max_length=100)
    geography: list[str] = Field(default_factory=list, max_length=50)
    study_design: str = Field(default="", alias="studyDesign", max_length=120)
    license: str = Field(default="", max_length=100)
    ethics_approved: bool = Field(default=False, alias="ethicsApproved")
    data_dictionary_available: bool = Field(default=False, alias="dataDictionaryAvailable")
    intended_tasks: list[str] = Field(default_factory=list, alias="intendedTasks", max_length=20)
    label_column: str | None = Field(default=None, alias="labelColumn", max_length=120)
    research_task: str = Field(default="", alias="researchTask", max_length=250)


class SynthMedGeneratedDatasetRegisterResponse(BaseModel):
    dataset: DatasetSummary
    message: str
