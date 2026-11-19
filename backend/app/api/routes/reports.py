from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.etl.extract import extract_dataset
from app.models.dataset import Dataset
from app.models.enums import UserRole
from app.models.reports import QualityReport, ReadinessReport, RepresentativenessReport
from app.models.user import User
from app.schemas.reports import (
    QualityIssueResponse,
    QualityReportResponse,
    ReadinessCategoryResponse,
    ReadinessReportResponse,
    ReadinessRequest,
    RepresentativenessReportResponse,
)
from app.services.audit_service import log_audit
from app.services.dataset_service import current_version, get_dataset, iso, representativeness_score
from app.services.readiness_service import assess_readiness, persist_readiness_report
from app.services.storage_service import StorageService

router = APIRouter(prefix="/datasets", tags=["reports"])


def _can_view(dataset: Dataset, user: User) -> bool:
    return (
        user.role == UserRole.ADMINISTRATOR
        or dataset.owner_id == user.id
        or dataset.status.value == "Available"
    )


def _grade(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Poor"


def _quality_response(report: QualityReport) -> QualityReportResponse:
    return QualityReportResponse(
        datasetId=report.dataset_id,
        overall=report.overall_score,
        grade=_grade(report.overall_score),
        dimensions=report.dimensions_json,
        issues=[QualityIssueResponse(**issue) for issue in report.findings_json or []],
        assessedAt=iso(report.created_at),
        rulesVersion=report.formula_version,
        sampleSize=report.sample_size,
        method=report.method,
    )


def _readiness_response(report: ReadinessReport) -> ReadinessReportResponse:
    return ReadinessReportResponse(
        datasetId=report.dataset_id,
        task=report.research_task,
        overall=report.overall_score,
        verdict=report.verdict,
        categories=[ReadinessCategoryResponse(**category) for category in report.categories_json or []],
        limitations=report.limitations_json or [],
        recommendations=report.recommendations_json or [],
        assessedAt=iso(report.created_at),
        method=report.method,
    )


def _representativeness_response(report: RepresentativenessReport) -> RepresentativenessReportResponse:
    return RepresentativenessReportResponse(
        datasetId=report.dataset_id,
        ageBands=report.age_bands_json or [],
        pregnancyStages=report.pregnancy_stages_json or [],
        paediatricGroups=report.paediatric_groups_json or [],
        geography=report.geography_json or [],
        missingAttributes=report.missing_attributes_json or [],
        coverageNotes=report.coverage_notes_json or [],
        assessedAt=iso(report.created_at),
    )


@router.get("/{dataset_id}/quality", response_model=QualityReportResponse)
def get_quality_report(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> QualityReportResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    report = db.scalar(
        select(QualityReport)
        .where(QualityReport.dataset_id == dataset.id)
        .order_by(QualityReport.created_at.desc())
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No quality report is available")
    return _quality_response(report)


@router.get("/{dataset_id}/readiness", response_model=ReadinessReportResponse)
def get_readiness_report(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    task: str | None = None,
) -> ReadinessReportResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    statement = select(ReadinessReport).where(ReadinessReport.dataset_id == dataset.id)
    if task:
        statement = statement.where(ReadinessReport.research_task == task)
    report = db.scalar(statement.order_by(ReadinessReport.created_at.desc()))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No readiness report is available")
    return _readiness_response(report)


@router.post("/{dataset_id}/readiness", response_model=ReadinessReportResponse)
def create_readiness_report(
    dataset_id: str,
    payload: ReadinessRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    user: CurrentUser,
) -> ReadinessReportResponse:
    dataset = get_dataset(db, dataset_id)
    if user.role != UserRole.ADMINISTRATOR and dataset.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset contributor can run readiness assessment",
        )
    version = current_version(dataset)
    if version is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset has no version to assess")
    quality = db.scalar(
        select(QualityReport)
        .where(QualityReport.dataset_id == dataset.id)
        .order_by(QualityReport.created_at.desc())
    )
    if quality is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run ETL quality assessment before assessing readiness",
        )

    try:
        raw_path = StorageService(settings).resolve(version.raw_file_path, kind="raw")
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset raw file not found on disk",
        ) from error
    extracted = extract_dataset(raw_path, dataset.format)
    latest_rep = db.scalar(
        select(RepresentativenessReport)
        .where(RepresentativenessReport.dataset_id == dataset.id)
        .order_by(RepresentativenessReport.created_at.desc())
    )
    rep_score = representativeness_score(dataset) if latest_rep else 0
    assessment = assess_readiness(
        dataset=dataset,
        metadata=dataset.metadata_record,
        profile=extracted.profile,
        quality=type(
            "QualityView",
            (),
            {"overall": quality.overall_score},
        )(),
        research_task=payload.task.strip(),
        representativeness_score=rep_score or 0,
    )
    dataset.research_task = payload.task.strip()
    report = persist_readiness_report(
        db,
        dataset=dataset,
        version=version,
        quality_report_id=quality.id,
        assessment=assessment,
    )
    log_audit(
        db,
        action="readiness.assessed",
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details={"task": payload.task, "overall": assessment.overall, "verdict": assessment.verdict},
        request=request,
    )
    db.commit()
    db.refresh(report)
    return _readiness_response(report)


@router.get("/{dataset_id}/representativeness", response_model=RepresentativenessReportResponse)
def get_representativeness_report(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> RepresentativenessReportResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    report = db.scalar(
        select(RepresentativenessReport)
        .where(RepresentativenessReport.dataset_id == dataset.id)
        .order_by(RepresentativenessReport.created_at.desc())
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No representativeness report is available")
    return _representativeness_response(report)


@router.get("/{dataset_id}/reports")
def get_all_reports(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> dict:
    dataset = get_dataset(db, dataset_id)
    if not _can_view(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    quality = db.scalar(
        select(QualityReport).where(QualityReport.dataset_id == dataset.id).order_by(QualityReport.created_at.desc())
    )
    readiness = db.scalar(
        select(ReadinessReport)
        .where(ReadinessReport.dataset_id == dataset.id)
        .order_by(ReadinessReport.created_at.desc())
    )
    representativeness = db.scalar(
        select(RepresentativenessReport)
        .where(RepresentativenessReport.dataset_id == dataset.id)
        .order_by(RepresentativenessReport.created_at.desc())
    )
    return {
        "quality": _quality_response(quality).model_dump() if quality else None,
        "readiness": _readiness_response(readiness).model_dump() if readiness else None,
        "representativeness": _representativeness_response(representativeness).model_dump()
        if representativeness
        else None,
    }
