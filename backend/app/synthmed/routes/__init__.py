from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.services.audit_service import log_audit
from app.synthmed.schemas import (
    SynthMedClinicalReferenceListResponse,
    SynthMedClinicalValidationRequest,
    SynthMedClinicalValidationResponse,
    SynthMedComparisonCreateRequest,
    SynthMedComparisonListItem,
    SynthMedComparisonResponse,
    SynthMedConditionValidationRequest,
    SynthMedConditionValidationResponse,
    SynthMedDatasetColumnsResponse,
    SynthMedDownloadsResponse,
    SynthMedEvaluationReportResponse,
    SynthMedExportRequest,
    SynthMedExportResponse,
    SynthMedGeneratedDatasetDetailResponse,
    SynthMedGeneratedDatasetResponse,
    SynthMedGeneratedPreviewResponse,
    SynthMedGenerationAnalysisResponse,
    SynthMedGenerationJobResponse,
    SynthMedGenerationStartRequest,
    SynthMedMedicalProfileResponse,
    SynthMedModelCapabilityListResponse,
    SynthMedSourceDatasetResponse,
    SynthMedSourceUploadResponse,
)
from app.synthmed.services import (
    clinical_reference_service,
    comparison_service,
    generation_service,
    medical_schema_service,
)
from app.synthmed.services.dataset_service import read_source_dataframe
from app.synthmed.services.source_service import (
    create_source_upload,
    downloads_payload,
    ensure_generated_access,
    ensure_source_access,
    get_generated,
    get_source,
    list_generated,
    list_sources,
    to_generated_response,
    to_source_response,
)
from app.synthmed.services.storage_service import SynthMedStorageService

router = APIRouter(prefix="/synthmed", tags=["synthmed"])


@router.get("/models", response_model=SynthMedModelCapabilityListResponse)
def get_generation_models(user: CurrentUser) -> SynthMedModelCapabilityListResponse:
    return SynthMedModelCapabilityListResponse.model_validate(generation_service.models_payload())


def _stream_file(path: Path, media_type: str, download_name: str) -> StreamingResponse:
    def chunks() -> Iterator[bytes]:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    quoted = quote(download_name, safe="")
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Content-Length": str(path.stat().st_size),
        },
    )


def _source_frame(source, settings: Settings):
    storage = SynthMedStorageService(settings)
    return read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)


@router.post("/upload", response_model=SynthMedSourceUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_source_dataset(
    request: Request,
    file: Annotated[UploadFile, File()],
    dataset_name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    db: Annotated[Session, Depends(get_db)] = None,
    user: CurrentUser = None,
    settings: Annotated[Settings, Depends(get_app_settings)] = None,
) -> SynthMedSourceUploadResponse:
    if not (dataset_name or "").strip():
        # fall back to filename stem; keep dataset name required in practice but be tolerant
        dataset_name = ""
    dataset = create_source_upload(
        db,
        settings=settings,
        user=user,
        upload=file,
        dataset_name=dataset_name,
        description=description,
        request=request,
    )
    return SynthMedSourceUploadResponse(
        dataset=to_source_response(dataset),
        message=(
            "Source dataset uploaded and stored successfully. The original file was preserved without modification."
        ),
    )


@router.get("/sources", response_model=list[SynthMedSourceDatasetResponse])
def get_sources(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> list[SynthMedSourceDatasetResponse]:
    return [to_source_response(item) for item in list_sources(db, user=user)]


@router.get("/sources/{dataset_id}", response_model=SynthMedSourceDatasetResponse)
def get_source_dataset(
    dataset_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedSourceDatasetResponse:
    dataset = get_source(db, dataset_id)
    ensure_source_access(dataset, user)
    return to_source_response(dataset)


@router.get("/datasets/{dataset_id}/columns", response_model=SynthMedDatasetColumnsResponse)
def get_dataset_columns(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
    model: str = "CTGAN",
) -> SynthMedDatasetColumnsResponse:
    source = get_source(db, dataset_id)
    ensure_source_access(source, user)
    try:
        payload = generation_service.dataset_columns_payload(db, source, user, settings, model)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk.") from error
    return SynthMedDatasetColumnsResponse.model_validate(payload)


@router.get("/clinical/references", response_model=SynthMedClinicalReferenceListResponse)
def get_clinical_references(user: CurrentUser) -> SynthMedClinicalReferenceListResponse:
    references = clinical_reference_service.reference_catalog()
    return SynthMedClinicalReferenceListResponse(
        references=references,
        count=len(references),
        message=(
            "Documented research-use reference intervals with source provenance. "
            "Unavailable entries are never applied to generated records."
        ),
    )


@router.get("/sources/{dataset_id}/medical-profile", response_model=SynthMedMedicalProfileResponse)
def get_medical_profile(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedMedicalProfileResponse:
    source = get_source(db, dataset_id)
    ensure_source_access(source, user)
    try:
        frame = _source_frame(source, settings)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk.") from error
    profile = medical_schema_service.profile_medical_schema(frame)
    return SynthMedMedicalProfileResponse(
        sourceDatasetId=source.id,
        datasetName=source.dataset_name,
        profile=profile,
        message="Review detected units and contexts before enabling clinical constraints.",
    )


@router.post("/sources/{dataset_id}/clinical-validation", response_model=SynthMedClinicalValidationResponse)
def validate_source_clinical(
    dataset_id: str,
    payload: SynthMedClinicalValidationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedClinicalValidationResponse:
    source = get_source(db, dataset_id)
    ensure_source_access(source, user)
    try:
        frame = _source_frame(source, settings)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk.") from error
    profile = medical_schema_service.profile_medical_schema(frame)
    approved = payload.approvedOutputColumns or profile["approvedOutputColumns"]
    schema_validation = (
        medical_schema_service.validate_strict_output_schema(
            frame,
            approved_columns=approved,
            identifier_columns=profile["excludedIdentifierColumns"],
        )
        if payload.enforceStrictSchema
        else {}
    )
    report = clinical_reference_service.validate_clinical_records(
        frame,
        generation_profile=payload.generationProfile,
        clinical_variables=[item.model_dump() for item in payload.clinicalVariables],
        overrides=[item.model_dump() for item in payload.referenceOverrides],
        disease_rules=[item.model_dump() for item in payload.diseaseRules],
    )
    public_report = generation_service._public_clinical_report(report)
    return SynthMedClinicalValidationResponse(
        sourceDatasetId=source.id,
        generationProfile=payload.generationProfile,
        report=public_report,
        schemaValidation=schema_validation,
        warnings=list(public_report.get("warnings") or []),
    )


@router.get("/sources/{dataset_id}/download")
def download_source_dataset(
    dataset_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    dataset = get_source(db, dataset_id)
    ensure_source_access(dataset, user)
    storage = SynthMedStorageService(settings)
    try:
        path = storage.resolve_source(dataset.stored_path)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk.") from error

    log_audit(
        db,
        action="synthmed.source_downloaded",
        resource_type="synthmed_source_dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details={"filename": dataset.original_filename, "format": dataset.file_format},
        request=request,
    )
    db.commit()

    media = {
        "CSV": "text/csv",
        "JSON": "application/json",
        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(dataset.file_format, "application/octet-stream")
    return _stream_file(path, media, dataset.original_filename)


@router.get("/downloads", response_model=SynthMedDownloadsResponse)
def get_downloads(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> SynthMedDownloadsResponse:
    return downloads_payload(db, user=user)


@router.get("/generated", response_model=list[SynthMedGeneratedDatasetResponse])
def get_generated_datasets(
    db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> list[SynthMedGeneratedDatasetResponse]:
    return [to_generated_response(item) for item in list_generated(db, user=user)]


@router.get("/generated/{dataset_id}/download")
def download_generated_dataset(
    dataset_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
    file_format: str = "CSV",
):
    dataset = get_generated(db, dataset_id)
    ensure_generated_access(dataset, user)
    try:
        path, filename = generation_service.generated_download_path(db, dataset_id, file_format, settings)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generated file not found on disk."
        ) from error

    log_audit(
        db,
        action="synthmed.generated_downloaded",
        resource_type="synthmed_generated_dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details={"filename": filename, "format": file_format.upper()},
        request=request,
    )
    db.commit()

    media = {
        "CSV": "text/csv",
        "JSON": "application/json",
        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(file_format.upper(), "application/octet-stream")
    return _stream_file(path, media, filename)


@router.post("/generation/analyse/{source_dataset_id}", response_model=SynthMedGenerationAnalysisResponse)
def analyse_generation_source(
    source_dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedGenerationAnalysisResponse:
    source = get_source(db, source_dataset_id)
    ensure_source_access(source, user)
    try:
        return generation_service.analyse_source(db, source, settings)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found on disk.") from error


def _validate_conditions(
    payload: SynthMedConditionValidationRequest,
    request: Request,
    db: Session,
    user,
    settings: Settings,
) -> SynthMedConditionValidationResponse:
    source = get_source(db, payload.sourceDatasetId)
    ensure_source_access(source, user)
    config = payload.model_dump(exclude={"sourceDatasetId"})
    result = generation_service.validate_conditions_payload(source, config, settings)
    log_audit(
        db,
        action="synthmed.conditions_validated",
        resource_type="synthmed_source_dataset",
        resource_id=source.id,
        actor_id=user.id,
        details={
            "model": result["model"],
            "condition_count": len(config.get("conditions") or []),
            "valid": result["valid"],
        },
        request=request,
    )
    db.commit()
    return SynthMedConditionValidationResponse.model_validate(result)


@router.post("/generation/validate-conditions", response_model=SynthMedConditionValidationResponse)
def validate_generation_conditions(
    payload: SynthMedConditionValidationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedConditionValidationResponse:
    return _validate_conditions(payload, request, db, user, settings)


@router.post("/conditions/validate", response_model=SynthMedConditionValidationResponse)
def validate_conditions(
    payload: SynthMedConditionValidationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedConditionValidationResponse:
    return _validate_conditions(payload, request, db, user, settings)


@router.post("/generation/start", response_model=SynthMedGenerationJobResponse, status_code=status.HTTP_201_CREATED)
def start_generation(
    payload: SynthMedGenerationStartRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedGenerationJobResponse:
    source = get_source(db, payload.sourceDatasetId)
    ensure_source_access(source, user)
    config = payload.model_dump()
    job = generation_service.start_generation_job(
        db, source=source, config=config, user=user, settings=settings, request=request
    )
    return generation_service.job_response(job)


@router.get("/generation/jobs", response_model=list[SynthMedGenerationJobResponse])
def get_generation_jobs(db: Annotated[Session, Depends(get_db)], user: CurrentUser):
    return [generation_service.job_response(job) for job in generation_service.list_jobs(db, user)]


@router.get("/generation/jobs/{job_id}", response_model=SynthMedGenerationJobResponse)
def get_generation_job(
    job_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedGenerationJobResponse:
    return generation_service.job_response(generation_service.get_job(db, job_id, user))


@router.get("/generation/jobs/{job_id}/conditions", response_model=SynthMedEvaluationReportResponse)
def get_generation_job_conditions(
    job_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedEvaluationReportResponse:
    job = generation_service.get_job(db, job_id, user)
    if not job.generated_dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No condition result is available yet.")
    return SynthMedEvaluationReportResponse.model_validate(
        generation_service.condition_satisfaction_report(db, job.generated_dataset_id, user)
    )


@router.get("/generated/{generation_id}", response_model=SynthMedGeneratedDatasetDetailResponse)
def get_generated_detail(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedGeneratedDatasetDetailResponse:
    return generation_service.generated_detail(db, generation_id, user)


@router.get("/generated/{generation_id}/preview", response_model=SynthMedGeneratedPreviewResponse)
def get_generated_preview(
    generation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
) -> SynthMedGeneratedPreviewResponse:
    try:
        return generation_service.preview_generated(db, generation_id, user, settings, page, page_size)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated file not found on disk.",
        ) from error


@router.get("/generated/{generation_id}/conditions", response_model=SynthMedEvaluationReportResponse)
def get_generated_conditions(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedEvaluationReportResponse:
    return SynthMedEvaluationReportResponse.model_validate(
        generation_service.condition_satisfaction_report(db, generation_id, user)
    )


@router.get("/generated/{generation_id}/clinical", response_model=SynthMedEvaluationReportResponse)
def get_generated_clinical(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedEvaluationReportResponse:
    return SynthMedEvaluationReportResponse.model_validate(
        generation_service.evaluation_report(db, generation_id, "clinical", user)
    )


@router.get("/generated/{generation_id}/evaluation", response_model=dict[str, Any])
def get_generated_evaluation(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> dict[str, Any]:
    return generation_service.generated_evaluation_summary(db, generation_id, user)


@router.get("/generated/{generation_id}/quality", response_model=SynthMedEvaluationReportResponse)
def get_generated_quality(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedEvaluationReportResponse:
    return generation_service.evaluation_report(db, generation_id, "quality", user)


@router.get("/generated/{generation_id}/privacy", response_model=SynthMedEvaluationReportResponse)
def get_generated_privacy(
    generation_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedEvaluationReportResponse:
    return generation_service.evaluation_report(db, generation_id, "privacy", user)


@router.post("/generated/{generation_id}/export", response_model=SynthMedExportResponse)
def export_generated_dataset(
    generation_id: str,
    payload: SynthMedExportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedExportResponse:
    try:
        return generation_service.export_generated(
            db,
            generated_id=generation_id,
            user=user,
            file_format=payload.format,
            settings=settings,
            request=request,
        )
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated file not found on disk.",
        ) from error


@router.get("/generated/{generation_id}/reports/{report_type}/download")
def download_generated_report(
    generation_id: str,
    report_type: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    dataset = get_generated(db, generation_id)
    ensure_generated_access(dataset, user)
    report = generation_service.evaluation_report_row(db, generation_id, report_type)
    try:
        path = SynthMedStorageService(settings).resolve_report(report.file_path)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found on disk.") from error

    log_audit(
        db,
        action="synthmed.report_downloaded",
        resource_type="synthmed_evaluation_report",
        resource_id=report.id,
        actor_id=user.id,
        details={"generated_dataset_id": generation_id, "report_type": report_type},
        request=request,
    )
    db.commit()
    return _stream_file(path, "application/json", f"{report_type}_report.json")


@router.post("/comparisons", response_model=SynthMedComparisonResponse, status_code=status.HTTP_201_CREATED)
def create_comparison(
    payload: SynthMedComparisonCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SynthMedComparisonResponse:
    row = comparison_service.create_comparison(
        db,
        source_id=payload.sourceDatasetId,
        generated_id=payload.generatedDatasetId,
        name=payload.name,
        settings=settings,
        user=user,
        request=request,
    )
    return comparison_service.to_response(row)


@router.get("/comparisons", response_model=list[SynthMedComparisonListItem])
def get_comparisons(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> list[SynthMedComparisonListItem]:
    return [comparison_service.to_list_response(row) for row in comparison_service.list_comparisons(db, user)]


@router.get("/comparisons/{comparison_id}", response_model=SynthMedComparisonResponse)
def get_comparison(
    comparison_id: str, db: Annotated[Session, Depends(get_db)], user: CurrentUser
) -> SynthMedComparisonResponse:
    return comparison_service.to_response(comparison_service.get_comparison(db, comparison_id, user))


@router.get("/comparisons/{comparison_id}/report/download")
def download_comparison_report(
    comparison_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    row = comparison_service.get_comparison(db, comparison_id, user)
    path = comparison_service.comparison_report_path(row, settings)
    log_audit(
        db,
        action="synthmed.comparison_report_downloaded",
        resource_type="synthmed_comparison",
        resource_id=row.id,
        actor_id=user.id,
        details={"source_dataset_id": row.source_dataset_id, "generated_dataset_id": row.generated_dataset_id},
        request=request,
    )
    db.commit()
    return _stream_file(path, "application/json", "comparison_report.json")
