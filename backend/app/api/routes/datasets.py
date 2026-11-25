from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings, require_roles
from app.core.config import Settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.enums import AccessClassification, DatasetStatus, UserRole
from app.models.user import User
from app.schemas.dataset import (
    DatasetDecisionInput,
    DatasetDetailResponse,
    DatasetLineageResponse,
    DatasetMetadataInput,
    DatasetSummary,
    DatasetVersionCompareInput,
    DatasetVersionCompareResponse,
    DatasetVersionCreateInput,
    DatasetVersionHistoryResponse,
    DatasetVersionItemResponse,
    UploadResponse,
)
from app.services import dataset_version_service
from app.services.audit_service import log_audit
from app.services.dataset_service import (
    approve_dataset as approve_service,
)
from app.services.dataset_service import (
    current_version,
    get_dataset,
    has_approved_access,
    list_datasets,
    to_detail,
    to_summary,
)
from app.services.dataset_service import (
    reject_dataset as reject_service,
)
from app.services.generated_ingestion_service import ingest_generated_dataset
from app.services.storage_service import StorageService
from app.services.upload_service import create_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _visible(dataset: Dataset, user: User) -> bool:
    return (
        user.role == UserRole.ADMINISTRATOR
        or dataset.owner_id == user.id
        or dataset.status == DatasetStatus.AVAILABLE
    )


def _can_view_version_metadata(db: Session, dataset: Dataset, user: User) -> bool:
    return _visible(dataset, user) and has_approved_access(db, dataset, user)


@router.get("/", response_model=list[DatasetSummary])
@router.get("", response_model=list[DatasetSummary], include_in_schema=False)
def get_datasets(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    search: str | None = None,
    domain: str | None = None,
    access: AccessClassification | None = None,
    dataset_status: Annotated[DatasetStatus | None, Query(alias="status")] = None,
    mine: bool = False,
    repository_only: bool = False,
) -> list[DatasetSummary]:
    datasets = list_datasets(
        db,
        user=user,
        search=search,
        domain=domain,
        access=access,
        dataset_status=dataset_status,
        mine=mine,
        repository_only=repository_only,
    )
    return [to_summary(d) for d in datasets if _visible(d, user)]


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset_detail(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> DatasetDetailResponse:
    dataset = get_dataset(db, dataset_id)
    if not _visible(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    return to_detail(dataset)


@router.get("/{dataset_id}/versions", response_model=DatasetVersionHistoryResponse)
def get_version_history(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetVersionHistoryResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view_version_metadata(db, dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    return DatasetVersionHistoryResponse.model_validate(dataset_version_service.get_history(db, settings, dataset))


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version_snapshot(
    dataset_id: str,
    payload: DatasetVersionCreateInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetVersionItemResponse:
    dataset = get_dataset(db, dataset_id)
    if not _visible(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    version = dataset_version_service.create_snapshot_version(
        db,
        settings=settings,
        dataset=dataset,
        user=user,
        note=payload.note,
        request=request,
    )
    db.commit()
    db.refresh(dataset)
    return DatasetVersionItemResponse.model_validate(
        dataset_version_service.get_version(db, settings, dataset, version.id)
    )


@router.post("/{dataset_id}/versions/compare", response_model=DatasetVersionCompareResponse)
def compare_dataset_versions(
    dataset_id: str,
    payload: DatasetVersionCompareInput,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetVersionCompareResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view_version_metadata(db, dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    result = dataset_version_service.compare_versions(
        db,
        settings,
        dataset,
        payload.versionAId,
        payload.versionBId,
    )
    return DatasetVersionCompareResponse.model_validate(result)


@router.get("/{dataset_id}/lineage", response_model=DatasetLineageResponse)
def get_dataset_lineage(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetLineageResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view_version_metadata(db, dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    return DatasetLineageResponse.model_validate(dataset_version_service.get_lineage(db, settings, dataset))


@router.get("/{dataset_id}/versions/{version_id}", response_model=DatasetVersionItemResponse)
def get_dataset_version(
    dataset_id: str,
    version_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetVersionItemResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view_version_metadata(db, dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    return DatasetVersionItemResponse.model_validate(
        dataset_version_service.get_version(db, settings, dataset, version_id)
    )


@router.get("/{dataset_id}/versions/{version_id}/lineage", response_model=DatasetLineageResponse)
def get_version_lineage(
    dataset_id: str,
    version_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetLineageResponse:
    dataset = get_dataset(db, dataset_id)
    if not _can_view_version_metadata(db, dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    return DatasetLineageResponse.model_validate(
        dataset_version_service.version_for_lineage(db, settings, dataset, version_id)
    )


@router.post(
    "/{dataset_id}/versions/{version_id}/restore",
    response_model=DatasetVersionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def restore_dataset_version(
    dataset_id: str,
    version_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatasetVersionItemResponse:
    dataset = get_dataset(db, dataset_id)
    if not _visible(dataset, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this dataset")
    restored = dataset_version_service.restore_version(
        db,
        settings=settings,
        dataset=dataset,
        version_id=version_id,
        user=user,
        request=request,
    )
    db.commit()
    db.refresh(dataset)
    return DatasetVersionItemResponse.model_validate(
        dataset_version_service.get_version(db, settings, dataset, restored.id)
    )


@router.get("/{dataset_id}/versions/{version_id}/download")
def download_dataset_version(
    dataset_id: str,
    version_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    dataset = get_dataset(db, dataset_id)
    if not has_approved_access(db, dataset, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to download this dataset. Please request access.",
        )
    version, path, filename, media_type = dataset_version_service.version_download_path(
        db, settings, dataset, version_id
    )
    log_audit(
        db,
        action="dataset.version_downloaded",
        resource_type="dataset_version",
        resource_id=version.id,
        actor_id=user.id,
        details={
            "dataset_id": dataset.id,
            "version_label": version.version_label,
            "checksum_sha256": version.checksum_sha256,
        },
        request=request,
    )
    db.commit()
    return FileResponse(path=path, media_type=media_type, filename=filename)


@router.post("/{dataset_id}/approve", response_model=DatasetSummary)
def approve_dataset_endpoint(
    dataset_id: str,
    payload: DatasetDecisionInput,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))],
) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id)
    approve_service(db, dataset, admin, payload.reason)
    log_audit(
        db,
        action="dataset.approved",
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=admin.id,
        details={"reason": payload.reason},
    )
    db.commit()
    db.refresh(dataset)
    return to_summary(dataset)


@router.post("/{dataset_id}/reject", response_model=DatasetSummary)
def reject_dataset_endpoint(
    dataset_id: str,
    payload: DatasetDecisionInput,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))],
) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id)
    reject_service(db, dataset, admin, payload.reason)
    log_audit(
        db,
        action="dataset.changes_requested",
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=admin.id,
        details={"reason": payload.reason},
    )
    db.commit()
    db.refresh(dataset)
    return to_summary(dataset)


@router.get("/{dataset_id}/download")
def download_dataset_endpoint(
    dataset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    dataset = get_dataset(db, dataset_id)
    if not has_approved_access(db, dataset, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to download this dataset. Please request access.",
        )
    version = current_version(dataset)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset has no versions")

    file_path = version.processed_file_path or version.raw_file_path
    kind = "processed" if version.processed_file_path else "raw"
    try:
        path = StorageService(settings).resolve(file_path, kind=kind)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found on disk") from error
    if (
        kind == "processed"
        and version.checksum_sha256
        and dataset_version_service.sha256_file(path) != version.checksum_sha256
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset checksum mismatch; download blocked.")

    log_audit(
        db,
        action="dataset.downloaded",
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details={"version": version.version_label},
    )
    db.commit()

    media_type = "text/csv" if dataset.format.value == "CSV" else "application/octet-stream"
    filename = f"{dataset.title.replace(' ', '_')}_{version.version_label}.{dataset.format.value.lower()}"
    return FileResponse(path=path, media_type=media_type, filename=filename)


@router.post("/", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
    metadata: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    generated_dataset_id: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    if user.role not in {UserRole.CONTRIBUTOR, UserRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only contributors can upload datasets")
    try:
        parsed_metadata = DatasetMetadataInput.model_validate_json(metadata)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid metadata: {error}",
        ) from error

    try:
        if generated_dataset_id:
            dataset, job = ingest_generated_dataset(
                db,
                settings=settings,
                user=user,
                generated_dataset_id=generated_dataset_id,
                metadata=parsed_metadata,
                request=request,
            )
            message = (
                "Generated dataset queued for the same governed ETL pipeline as direct uploads. "
                "Review every mapping suggestion, then approve and run the pipeline."
            )
        else:
            if file is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Select a file or provide a generated dataset ID",
                )
            content = await file.read()
            if not content:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The uploaded file is empty"
                )
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
                )
            dataset, job = create_upload(
                db,
                settings=settings,
                user=user,
                filename=file.filename or "upload",
                content=content,
                metadata=parsed_metadata,
                request=request,
            )
            message = (
                "Upload accepted. The ETL job is queued; start profiling, review every mapping suggestion, "
                "then approve and run the pipeline."
            )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return UploadResponse(dataset=to_summary(dataset), jobId=job.id, message=message)
