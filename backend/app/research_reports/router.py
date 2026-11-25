from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.research_reports import constants
from app.research_reports.service import create_report, get_report, list_reports, to_response
from app.research_reports.storage import ResearchReportStorageService
from app.schemas.research_reports import ResearchReportGenerateRequest as GenerateRequest
from app.schemas.research_reports import ResearchReportListResponse as ListResponse
from app.schemas.research_reports import ResearchReportResponse as ReportResponse
from app.schemas.research_reports import ResearchReportStatusResponse as StatusResponse
from app.services.audit_service import log_audit

router = APIRouter(prefix="/reports", tags=["research reports"])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def _create(
    db: Session,
    settings: Settings,
    user: CurrentUser,
    payload: GenerateRequest,
    report_type: str,
    request: Request,
) -> ReportResponse:
    row = create_report(
        db,
        settings=settings,
        user=user,
        report_type=report_type,
        refs=payload.model_dump(),
        request=request,
    )
    return ReportResponse(**to_response(row))


@router.post("/dataset-profile", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_dataset_profile_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.DATASET_PROFILE, request)


@router.post("/etl", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_etl_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.ETL, request)


@router.post("/synthmed/generation", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_generation_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.SYNTHETIC_GENERATION, request)


@router.post("/synthmed/comparison", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_comparison_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.COMPARISON, request)


@router.post("/synthmed/privacy", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_privacy_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.PRIVACY, request)


@router.post("/synthmed/utility", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_utility_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.UTILITY, request)


@router.post("/synthmed/experiment", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_experiment_report(
    payload: GenerateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> ReportResponse:
    return _create(db, settings, user, payload, constants.EXPERIMENT, request)


@router.get("", response_model=ListResponse)
def list_research_reports(
    db: DbSession,
    user: CurrentUser,
    reportType: str | None = Query(default=None),
) -> ListResponse:
    rows = list_reports(db, user=user, report_type=reportType)
    counts = {value: 0 for value in constants.REPORT_TYPES}
    for row in rows:
        counts[row.report_type] = counts.get(row.report_type, 0) + 1
    return ListResponse(items=[ReportResponse(**to_response(row)) for row in rows], total=len(rows), counts=counts)


@router.get("/{report_id}", response_model=ReportResponse)
def get_research_report(report_id: str, db: DbSession, user: CurrentUser) -> ReportResponse:
    return ReportResponse(**to_response(get_report(db, user=user, report_id=report_id)))


@router.get("/{report_id}/status", response_model=StatusResponse)
def get_research_report_status(report_id: str, db: DbSession, user: CurrentUser) -> StatusResponse:
    row = get_report(db, user=user, report_id=report_id)
    response = to_response(row)
    return StatusResponse(
        reportId=response["reportId"],
        status=response["status"],
        error=response["error"],
        createdAt=response["createdAt"],
        completedAt=response["completedAt"],
    )


@router.get("/{report_id}/download")
def download_research_report(
    report_id: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> Response:
    row = get_report(db, user=user, report_id=report_id)
    if row.status != "Completed" or not row.report_file_path or not row.file_checksum:
        raise HTTPException(status_code=409, detail="This report is not available for download.")
    _, content = ResearchReportStorageService(settings).verify(row.report_file_path, row.file_checksum)
    log_audit(
        db,
        action="research_report_download",
        resource_type="research_report",
        resource_id=row.id,
        actor_id=user.id,
        details={"reportId": row.report_id},
        request=request,
    )
    db.commit()
    filename = f"{row.report_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
