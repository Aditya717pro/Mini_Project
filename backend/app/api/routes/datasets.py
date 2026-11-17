from __future__ import annotations

from pathlib import Path
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
    DatasetMetadataInput,
    DatasetSummary,
    UploadResponse,
)
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
from app.services.storage_service import StorageService
from app.services.upload_service import create_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _visible(dataset: Dataset, user: User) -> bool:
    return (
        user.role == UserRole.ADMINISTRATOR
        or dataset.owner_id == user.id
        or dataset.status == DatasetStatus.AVAILABLE
    )


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
    path = Path(file_path)
    if not path.is_absolute():
        storage = StorageService(settings)
        kind = "processed" if version.processed_file_path else "raw"
        path = storage.resolve(file_path, kind=kind)

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found on disk")

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
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
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

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )
    try:
        dataset, job = create_upload(
            db,
            settings=settings,
            user=user,
            filename=file.filename or "upload",
            content=content,
            metadata=parsed_metadata,
            request=request,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return UploadResponse(
        dataset=to_summary(dataset),
        jobId=job.id,
        message=(
            "Upload accepted. The ETL job is queued; start profiling, review every mapping suggestion, "
            "then approve and run the pipeline."
        ),
    )
