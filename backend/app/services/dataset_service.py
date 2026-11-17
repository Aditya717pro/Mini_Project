from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AccessClassification, DatasetStatus, RequestStatus
from app.models.reports import QualityReport, ReadinessReport, RepresentativenessReport
from app.models.user import User
from app.schemas.dataset import DatasetDetailResponse, DatasetSummary, DatasetVersionResponse


def iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def get_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.scalar(
        select(Dataset)
        .options(
            selectinload(Dataset.owner),
            selectinload(Dataset.metadata_record),
            selectinload(Dataset.versions),
            selectinload(Dataset.quality_reports),
            selectinload(Dataset.readiness_reports),
            selectinload(Dataset.representativeness_reports),
        )
        .where(Dataset.id == dataset_id)
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


def current_version(dataset: Dataset) -> DatasetVersion | None:
    if not dataset.versions:
        return None
    return next((version for version in dataset.versions if version.is_current), dataset.versions[-1])


def _latest_quality(dataset: Dataset) -> QualityReport | None:
    return max(dataset.quality_reports, key=lambda report: report.created_at, default=None)


def _latest_readiness(dataset: Dataset) -> ReadinessReport | None:
    return max(dataset.readiness_reports, key=lambda report: report.created_at, default=None)


def _latest_representativeness(dataset: Dataset) -> RepresentativenessReport | None:
    return max(dataset.representativeness_reports, key=lambda report: report.created_at, default=None)


def to_summary(dataset: Dataset) -> DatasetSummary:
    metadata = dataset.metadata_record
    version = current_version(dataset)
    quality = _latest_quality(dataset)
    readiness = _latest_readiness(dataset)
    versions = [
        DatasetVersionResponse(
            version=item.version_label,
            date=iso(item.created_at),
            note=(
                "Initial upload. Original file retained."
                if item.version_number == 1
                else "Processed version. Original and prior versions retained."
            ),
            records=item.record_count,
            checksum=item.checksum_sha256,
            status="Current" if item.is_current else "Superseded",
        )
        for item in sorted(dataset.versions, key=lambda value: value.version_number, reverse=True)
    ]
    return DatasetSummary(
        id=dataset.id,
        title=dataset.title,
        description=dataset.description,
        domain=dataset.domain,
        access=dataset.access_classification,
        status=dataset.status,
        owner=dataset.owner.full_name if dataset.owner else "Unknown",
        ownerOrganisation=dataset.owner.organisation if dataset.owner else "",
        format=dataset.format,
        records=dataset.record_count,
        columns=dataset.column_count,
        sizeMb=round(dataset.file_size_bytes / (1024 * 1024), 2),
        createdAt=iso(dataset.created_at),
        updatedAt=iso(dataset.updated_at),
        version=version.version_label if version else "v1.0",
        qualityScore=quality.overall_score if quality else None,
        readinessScore=readiness.overall_score if readiness else None,
        representativenessScore=representativeness_score(dataset),
        tags=metadata.keywords if metadata else [],
        ageRange=metadata.age_range if metadata else "",
        geography=metadata.geography if metadata else [],
        ethicsApproved=metadata.ethics_approved if metadata else False,
        license=metadata.license if metadata else "",
        studyDesign=metadata.study_design if metadata else "",
        collectionPeriod=metadata.collection_period if metadata else "",
        dataDictionaryAvailable=metadata.data_dictionary_available if metadata else False,
        consentScope=metadata.consent_scope if metadata else "",
        checksum=dataset.checksum_sha256,
        missingRate=dataset.missing_rate,
        duplicateRate=dataset.duplicate_rate,
        intendedTasks=metadata.intended_tasks if metadata else [],
        labelColumn=metadata.label_column if metadata else None,
        versions=versions,
    )


def representativeness_score(dataset: Dataset) -> int | None:
    report = _latest_representativeness(dataset)
    if report is None:
        return None
    available = 5 - len(report.missing_attributes_json or [])
    return max(0, min(100, round(100 * available / 5)))


def to_detail(dataset: Dataset) -> DatasetDetailResponse:
    summary = to_summary(dataset)
    version = current_version(dataset)
    return DatasetDetailResponse(**summary.model_dump(), profile=version.profile_json if version else {})


def list_datasets(
    db: Session,
    *,
    user: User,
    search: str | None = None,
    domain: str | None = None,
    access: AccessClassification | None = None,
    dataset_status: DatasetStatus | None = None,
    mine: bool = False,
    repository_only: bool = False,
) -> list[Dataset]:
    statement = (
        select(Dataset)
        .options(
            selectinload(Dataset.owner),
            selectinload(Dataset.metadata_record),
            selectinload(Dataset.versions),
            selectinload(Dataset.quality_reports),
            selectinload(Dataset.readiness_reports),
            selectinload(Dataset.representativeness_reports),
        )
        .order_by(Dataset.created_at.desc())
    )
    if mine:
        statement = statement.where(Dataset.owner_id == user.id)
    if repository_only:
        statement = statement.where(Dataset.status == DatasetStatus.AVAILABLE)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Dataset.title.ilike(term), Dataset.description.ilike(term), Dataset.domain.ilike(term))
        )
    if domain:
        statement = statement.where(Dataset.domain == domain)
    if access:
        statement = statement.where(Dataset.access_classification == access)
    if dataset_status:
        statement = statement.where(Dataset.status == dataset_status)
    return list(db.scalars(statement).unique())


def approve_dataset(db: Session, dataset: Dataset, admin: User, reason: str = "") -> Dataset:
    dataset.status = DatasetStatus.AVAILABLE
    dataset.approved_at = datetime.now(UTC)
    dataset.approved_by_id = admin.id
    dataset.rejection_reason = reason or None
    return dataset


def reject_dataset(db: Session, dataset: Dataset, admin: User, reason: str) -> Dataset:
    dataset.status = DatasetStatus.CHANGES_REQUESTED
    dataset.approved_at = None
    dataset.approved_by_id = None
    dataset.rejection_reason = reason
    return dataset


def dataset_report_context(dataset_id: str) -> dict[str, Any]:
    return {"dataset_id": dataset_id}


def has_approved_access(db: Session, dataset: Dataset, user: User) -> bool:
    from app.models.access import AccessRequest

    if user.role.value == "Administrator" or dataset.owner_id == user.id:
        return True
    if dataset.access_classification == AccessClassification.OPEN:
        return True
    request = db.scalar(
        select(AccessRequest).where(
            AccessRequest.dataset_id == dataset.id,
            AccessRequest.requester_id == user.id,
            AccessRequest.status == RequestStatus.APPROVED,
        )
    )
    return request is not None
