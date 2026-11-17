from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.access import AccessRequest
from app.models.dataset import Dataset
from app.models.enums import RequestStatus, UserRole
from app.models.user import User
from app.schemas.reports import AccessDecisionInput, AccessRequestInput, AccessRequestResponse
from app.services.audit_service import log_audit
from app.services.dataset_service import get_dataset, iso

router = APIRouter(tags=["access"])


def _response(item: AccessRequest, viewer: User) -> AccessRequestResponse:
    incoming = item.dataset.owner_id == viewer.id or viewer.role == UserRole.ADMINISTRATOR
    return AccessRequestResponse(
        id=item.id,
        datasetId=item.dataset_id,
        datasetTitle=item.dataset.title,
        requester=item.requester.full_name,
        role=item.requester.role,
        organisation=item.requester.organisation,
        purpose=item.purpose,
        projectTitle=item.project_title,
        requestedAt=iso(item.created_at),
        status=item.status,
        decidedAt=iso(item.decided_at) if item.decided_at else None,
        reviewer=item.decider.full_name if item.decider else None,
        decisionNote=item.decision_notes,
        direction="Incoming" if incoming else "Outgoing",
    )


@router.post(
    "/datasets/{dataset_id}/access-requests",
    response_model=AccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_access_request(
    dataset_id: str,
    payload: AccessRequestInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> AccessRequestResponse:
    dataset = get_dataset(db, dataset_id)
    if dataset.owner_id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already own this dataset")
    existing = db.scalar(
        select(AccessRequest).where(
            AccessRequest.dataset_id == dataset.id,
            AccessRequest.requester_id == user.id,
            AccessRequest.status == RequestStatus.PENDING,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending request already exists")
    item = AccessRequest(
        dataset_id=dataset.id,
        requester_id=user.id,
        project_title=payload.projectTitle.strip(),
        purpose=payload.purpose.strip(),
    )
    db.add(item)
    db.flush()
    log_audit(
        db,
        action="access.requested",
        resource_type="access_request",
        resource_id=item.id,
        actor_id=user.id,
        details={"dataset_id": dataset.id, "project": item.project_title},
        request=request,
    )
    db.commit()
    db.refresh(item)
    return _response(item, user)


@router.get("/access-requests", response_model=list[AccessRequestResponse])
def list_access_requests(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> list[AccessRequestResponse]:
    if user.role == UserRole.ADMINISTRATOR:
        statement = select(AccessRequest)
    else:
        statement = select(AccessRequest).where(
            or_(AccessRequest.requester_id == user.id, AccessRequest.dataset.has(Dataset.owner_id == user.id))
        )
    items = db.scalars(
        statement.options(
            selectinload(AccessRequest.dataset),
            selectinload(AccessRequest.requester),
            selectinload(AccessRequest.decider),
        ).order_by(AccessRequest.created_at.desc())
    ).unique()
    return [_response(item, user) for item in items]


@router.post("/access-requests/{request_id}/withdraw", response_model=AccessRequestResponse)
def withdraw_access_request(
    request_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> AccessRequestResponse:
    item = db.scalar(
        select(AccessRequest)
        .options(
            selectinload(AccessRequest.dataset),
            selectinload(AccessRequest.requester),
            selectinload(AccessRequest.decider),
        )
        .where(AccessRequest.id == request_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    if item.requester_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester can withdraw this request",
        )
    if item.status != RequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending requests can be withdrawn")
    item.status = RequestStatus.WITHDRAWN
    item.decided_at = datetime.now(UTC)
    log_audit(
        db,
        action="access.withdrawn",
        resource_type="access_request",
        resource_id=item.id,
        actor_id=user.id,
        details={"dataset_id": item.dataset_id},
        request=request,
    )
    db.commit()
    db.refresh(item)
    return _response(item, user)


@router.patch("/access-requests/{request_id}", response_model=AccessRequestResponse)
def decide_access_request(
    request_id: str,
    payload: AccessDecisionInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> AccessRequestResponse:
    item = db.scalar(
        select(AccessRequest)
        .options(
            selectinload(AccessRequest.dataset),
            selectinload(AccessRequest.requester),
            selectinload(AccessRequest.decider),
        )
        .where(AccessRequest.id == request_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    if user.role != UserRole.ADMINISTRATOR and item.dataset.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the dataset owner or an administrator can decide",
        )
    if item.status != RequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Access request has already been decided")
    item.status = RequestStatus(payload.status)
    item.decision_notes = payload.note.strip() or None
    item.decided_by_id = user.id
    item.decided_at = datetime.now(UTC)
    log_audit(
        db,
        action=f"access.{payload.status.lower()}",
        resource_type="access_request",
        resource_id=item.id,
        actor_id=user.id,
        details={"dataset_id": item.dataset_id, "status": payload.status, "note": payload.note},
        request=request,
    )
    db.commit()
    db.refresh(item)
    return _response(item, user)
