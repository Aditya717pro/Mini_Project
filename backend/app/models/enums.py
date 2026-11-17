from enum import StrEnum


class UserRole(StrEnum):
    ADMINISTRATOR = "Administrator"
    RESEARCHER = "Researcher"
    CONTRIBUTOR = "Contributor"


class DatasetStatus(StrEnum):
    PROCESSING = "Processing"
    PENDING_REVIEW = "Pending review"
    CHANGES_REQUESTED = "Changes requested"
    AVAILABLE = "Available"
    FAILED = "Failed"


class AccessClassification(StrEnum):
    OPEN = "Open"
    CONTROLLED = "Controlled"
    RESTRICTED = "Restricted"


class FileFormat(StrEnum):
    CSV = "CSV"
    XLSX = "XLSX"
    JSON = "JSON"


class JobStatus(StrEnum):
    QUEUED = "Queued"
    PROFILING = "Profiling"
    AWAITING_REVIEW = "Review required"
    APPROVED = "Approved"
    RUNNING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


class RequestStatus(StrEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"
