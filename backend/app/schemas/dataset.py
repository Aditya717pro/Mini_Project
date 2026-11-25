from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccessClassification, DatasetStatus, FileFormat

DOMAIN_PATTERN = r"^[A-Za-z][A-Za-z &'-]{1,99}$"


class DatasetMetadataInput(BaseModel):
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


class DatasetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: str
    date: str
    note: str
    records: int
    checksum: str
    status: str


class DatasetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    domain: str
    access: AccessClassification
    status: DatasetStatus
    owner: str
    ownerOrganisation: str
    format: FileFormat
    records: int
    columns: int
    sizeMb: float
    createdAt: str
    updatedAt: str
    version: str
    qualityScore: int | None = None
    readinessScore: int | None = None
    representativenessScore: int | None = None
    tags: list[str] = Field(default_factory=list)
    ageRange: str = ""
    geography: list[str] = Field(default_factory=list)
    ethicsApproved: bool = False
    license: str = ""
    studyDesign: str = ""
    collectionPeriod: str = ""
    dataDictionaryAvailable: bool = False
    consentScope: str = ""
    checksum: str
    origin: str = "Original"
    sourceGeneratedDatasetId: str | None = None
    sourceRepositoryDatasetId: str | None = None
    generationJobId: str | None = None
    generationModel: str | None = None
    provenance: dict = Field(default_factory=dict)
    missingRate: float = 0.0
    duplicateRate: float = 0.0
    intendedTasks: list[str] = Field(default_factory=list)
    labelColumn: str | None = None
    versions: list[DatasetVersionResponse] = Field(default_factory=list)


class DatasetDetailResponse(DatasetSummary):
    profile: dict = Field(default_factory=dict)


class UploadResponse(BaseModel):
    dataset: DatasetSummary
    jobId: str
    message: str


class DatasetDecisionInput(BaseModel):
    reason: str = Field(default="", max_length=1000)


class DatasetVersionItemResponse(BaseModel):
    id: str
    versionNumber: int
    versionLabel: str
    kind: str
    recordCount: int
    columnCount: int
    createdAt: str
    creator: str
    checksumSha256: str
    isCurrent: bool
    rawFilePath: str
    processedFilePath: str | None = None
    parentVersionId: str | None = None
    transformationHistory: list[dict[str, Any]] = Field(default_factory=list)
    validationSummary: dict[str, Any] = Field(default_factory=dict)
    fileAvailable: bool = False
    datasetSchema: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=dict)
    missingSummary: dict[str, Any] = Field(default_factory=dict)
    distributionSummary: dict[str, Any] = Field(default_factory=dict)
    restoredFromVersionId: str | None = None
    note: str = ""


class DatasetVersionHistoryResponse(BaseModel):
    datasetId: str
    datasetName: str
    datasetType: str
    ownerId: str
    currentVersion: str
    totalVersions: int
    lastUpdatedAt: str
    versions: list[DatasetVersionItemResponse] = Field(default_factory=list)


class DatasetLineageEventResponse(BaseModel):
    type: str
    parentVersionId: str | None = None
    childVersionId: str | None = None
    timestamp: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetLineageResponse(BaseModel):
    datasetId: str
    versions: list[DatasetVersionItemResponse] = Field(default_factory=list)
    lineage: list[DatasetLineageEventResponse] = Field(default_factory=list)
    events: list[DatasetLineageEventResponse] = Field(default_factory=list)


class DatasetVersionCreateInput(BaseModel):
    note: str = Field(default="", max_length=1000)


class DatasetVersionCompareInput(BaseModel):
    versionAId: str
    versionBId: str


class DatasetVersionCompareResponse(BaseModel):
    datasetId: str
    datasetName: str
    a: dict[str, Any]
    b: dict[str, Any]
    comparison: dict[str, Any]
