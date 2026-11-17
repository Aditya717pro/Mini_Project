from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus, UserRole
from app.models.user import User
from app.schemas.dataset import (
    DatasetMetadataInput,
    UploadResponse,
)
from app.services.dataset_service import (
    to_summary,
)
from app.services.upload_service import create_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _visible(dataset: Dataset, user: User) -> bool:
    return (
        user.role == UserRole.ADMINISTRATOR
        or dataset.owner_id == user.id
        or dataset.status == DatasetStatus.AVAILABLE
    )


def _convert_mappings(suggestions: list[dict[str, Any]]) -> dict[str, str | None]:
    """Convert suggested mapping list to approved mapping dict."""
    mapping: dict[str, str | None] = {}
    for item in suggestions:
        source = str(item.get("source", ""))
        target = item.get("target")
        mapping[source] = target if target else None
    return mapping


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid metadata: {error}",
        ) from error

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    # Auto-approve suggested mappings from the ETL suggestion engine,
    # so the pipeline can run immediately when the user triggers it.
    # This eliminates the extra API call needed before starting ETL.
    mapping = _convert_mappings(job.suggested_mapping_json or [])
    job.approved_mapping_json = mapping
    db.commit()

    return UploadResponse(
        dataset=to_summary(dataset),
        jobId=job.id,
        message=(
"Upload accepted. Suggested column mappings have been pre-approved. "
"Run the ETL pipeline to process the dataset and generate "
"quality/readiness/representativeness reports."
),
    )