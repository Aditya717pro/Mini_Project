from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccessClassification, DatasetStatus, FileFormat

DOMAIN_PATTERN = r"^[A-Za-z][A-Za-z &'-]{1,99}$"


class DatasetMetadataInput(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    description: str = Field(default="", max_length=5000)
    domain: str = Field(pattern=DOMAIN_PATTERN)
    access: AccessClassification = AccessClassification.CONTROLLED
    tags: list[str] = Field(default_factory=list, max_length=30)
    age_range: str = Field(default="", max_length=100)
    geography: list[str] = Field(default_factory=list, max_length=50)
    study_design: str = Field(default="", max_length=120)
    license: str = Field(default="", max_length=100)
    ethics_approved: bool = False
    data_dictionary_available: bool = False
    intended_tasks: list[str] = Field(default_factory=list, max_length=20)
    label_column: str | None = Field(default=None, max_length=120)
    research_task: str = Field(default="", max_length=250)


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
