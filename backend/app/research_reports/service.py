from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.research_report import ResearchReport
from app.models.user import User
from app.research_reports import constants
from app.research_reports.collectors import collect_data
from app.research_reports.pdf import render_report
from app.research_reports.sanitize import clean_text
from app.research_reports.storage import ResearchReportStorageService
from app.research_reports.templates import build_payload
from app.research_reports.validation import validate_sources
from app.services.audit_service import log_audit

TEMPLATE_VERSION = "1.0"
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _executor_for(settings: Settings) -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.synthmed_generation_worker_count,
                thread_name_prefix="research-reports",
            )
        return _executor


def shutdown_executor(*, wait: bool = True) -> None:
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=wait)


def _reference_values(refs: dict[str, str | None]) -> dict[str, str]:
    keys = (
        "datasetId",
        "datasetVersionId",
        "etlJobId",
        "generationJobId",
        "generatedDatasetId",
        "comparisonId",
        "privacyEvaluationId",
        "utilityEvaluationId",
        "experimentId",
    )
    return {key: clean_text(refs.get(key), default="") for key in keys}


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def to_response(row: ResearchReport) -> dict[str, Any]:
    return {
        "id": row.id,
        "reportId": row.report_id,
        "reportType": row.report_type,
        "title": row.title,
        "ownerId": row.owner_id,
        "datasetId": row.dataset_id,
        "datasetVersionId": row.dataset_version_id,
        "experimentId": row.experiment_id,
        "comparisonId": row.comparison_id,
        "privacyEvaluationId": row.privacy_evaluation_id,
        "utilityEvaluationId": row.utility_evaluation_id,
        "generationJobId": row.generation_job_id,
        "generatedDatasetId": row.generated_dataset_id,
        "fileChecksum": row.file_checksum,
        "fileSize": row.file_size,
        "templateVersion": row.template_version,
        "status": row.status,
        "error": clean_text(row.error_message, default="") if row.status == "Failed" else "",
        "createdAt": _iso(row.created_at),
        "completedAt": _iso(row.completed_at),
    }


def get_report(db: Session, *, user: Any, report_id: str) -> ResearchReport:
    row = db.scalar(select(ResearchReport).where(ResearchReport.report_id == report_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Research report not found.")
    if user.role != UserRole.ADMINISTRATOR and row.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not permitted to view this research report.")
    return row


def list_reports(db: Session, *, user: Any, report_type: str | None = None) -> list[ResearchReport]:
    from sqlalchemy import select

    statement = select(ResearchReport)
    if user.role != UserRole.ADMINISTRATOR:
        statement = statement.where(ResearchReport.owner_id == user.id)
    if report_type:
        statement = statement.where(ResearchReport.report_type == report_type)
    return list(db.scalars(statement.order_by(ResearchReport.created_at.desc())))


def create_report(
    db: Session,
    *,
    settings: Settings,
    user: Any,
    report_type: str,
    refs: dict[str, str | None],
    request: Request | None = None,
) -> ResearchReport:
    if report_type not in constants.REPORT_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported report type.")
    sources = validate_sources(db, user=user, report_type=report_type, refs=refs)
    source_refs = _reference_values(refs)
    resolved_refs = sources.reference_values()
    for key, value in resolved_refs.items():
        if value:
            source_refs[key] = value

    report_id = f"RR-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid4().hex[:12]}"
    row = ResearchReport(
        report_id=report_id,
        report_type=report_type,
        title=constants.REPORT_TITLES[report_type],
        owner_id=user.id,
        dataset_id=source_refs.get("datasetId") or None,
        dataset_version_id=source_refs.get("datasetVersionId") or None,
        experiment_id=source_refs.get("experimentId") or None,
        comparison_id=source_refs.get("comparisonId") or None,
        privacy_evaluation_id=source_refs.get("privacyEvaluationId") or None,
        utility_evaluation_id=source_refs.get("utilityEvaluationId") or None,
        generation_job_id=source_refs.get("generationJobId") or None,
        generated_dataset_id=source_refs.get("generatedDatasetId") or None,
        template_version=TEMPLATE_VERSION,
        report_data_snapshot_json={"sourceRefs": source_refs},
        status="Queued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_audit(
        db,
        action="research_report_create",
        resource_type="research_report",
        resource_id=row.id,
        actor_id=user.id,
        details={"reportId": row.report_id, "reportType": report_type},
        request=request,
    )
    db.commit()

    if settings.synthmed_generation_inline:
        generate_report(row.id, settings, db=db)
        db.refresh(row)
    else:
        _executor_for(settings).submit(generate_report, row.id, settings, SessionLocal)
    return row


def generate_report(
    report_id: str,
    settings: Settings,
    session_factory: sessionmaker | None = None,
    *,
    db: Session | None = None,
) -> None:
    owns_session = db is None
    session = db or (session_factory or SessionLocal)()
    try:
        row = session.get(ResearchReport, report_id)
        if row is None or row.status in {"Completed", "Generating"}:
            return
        refs = dict((row.report_data_snapshot_json or {}).get("sourceRefs") or {})
        user = session.get(User, row.owner_id)
        if user is None:
            raise RuntimeError("Report owner is unavailable")
        row.status = "Generating"
        row.error_message = None
        session.commit()

        sources = validate_sources(session, user=user, report_type=row.report_type, refs=refs)
        data = collect_data(session, settings, sources)
        data["report_id"] = row.report_id
        data["report_type"] = row.report_type
        data["title"] = row.title
        data["generated_at"] = datetime.now(UTC).isoformat()
        data["template_version"] = row.template_version
        dataset_ref = sources.dataset.id if sources.dataset else sources.synth_source.id if sources.synth_source else ""
        version_ref = (
            sources.dataset_version.id
            if sources.dataset_version
            else sources.synth_version.id if sources.synth_version else ""
        )
        data["references"] = [
            ("Dataset ID", dataset_ref),
            ("Dataset version ID", version_ref),
            ("Generation job ID", sources.generation_job.id if sources.generation_job else ""),
            ("Generated dataset ID", sources.generated_dataset.id if sources.generated_dataset else ""),
            ("Comparison ID", sources.comparison.id if sources.comparison else ""),
            ("Privacy evaluation ID", sources.privacy_evaluation.id if sources.privacy_evaluation else ""),
            ("Utility evaluation ID", sources.utility_evaluation.id if sources.utility_evaluation else ""),
            ("Experiment ID", sources.experiment.id if sources.experiment else ""),
        ]
        payload = build_payload(data)
        content = render_report(payload)

        storage = ResearchReportStorageService(settings)
        directory = storage.base / row.report_id
        attempt = 1 + len(list(directory.glob("report-attempt-*.pdf"))) if directory.exists() else 1
        _, relative = storage.save(row.report_id, content, filename=f"report-attempt-{attempt}.pdf")
        row.report_file_path = relative
        row.file_checksum = hashlib.sha256(content).hexdigest()
        row.file_size = len(content)
        row.report_data_snapshot_json = {
            "sourceRefs": refs,
            "payload": payload.to_dict(),
        }
        row.status = "Completed"
        row.completed_at = datetime.now(UTC)
        row.error_message = None
        log_audit(
            session,
            action="research_report_generate",
            resource_type="research_report",
            resource_id=row.id,
            actor_id=row.owner_id,
            details={"reportId": row.report_id, "status": "Completed"},
        )
        session.commit()
    except Exception as error:
        detail = getattr(error, "detail", str(error))
        message = clean_text(detail, default="Report generation failed", limit=500)
        row = session.get(ResearchReport, report_id)
        if row is not None:
            row.status = "Failed"
            row.error_message = message
            row.completed_at = datetime.now(UTC)
            session.commit()
    finally:
        if owns_session:
            session.close()
