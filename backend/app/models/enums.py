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
    RUNNING = "Running"
    AWAITING_REVIEW = "Review required"
    COMPLETED = "Completed"
    FAILED = "Failed"


class RequestStatus(StrEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"
