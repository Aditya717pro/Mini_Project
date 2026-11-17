from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_app_settings, require_roles
from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    RoleUpdateRequest,
    TokenResponse,
    UserResponse,
)
from app.services.audit_service import log_audit

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name cannot be blank or whitespace only.",
        )

    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.CONTRIBUTOR,
        organisation=payload.organisation.strip() or "Independent",
        title=payload.title.strip() or "Researcher",
    )
    db.add(user)
    db.flush()
    log_audit(
        db,
        action="user.registered",
        resource_type="user",
        actor_id=user.id,
        details={"email": email, "role": user.role.value},
        request=request,
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from error
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> TokenResponse:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    token = create_access_token(user.id, user.role, settings)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> User:
    user.full_name = payload.full_name.strip()
    user.organisation = payload.organisation.strip() or "Independent"
    user.title = payload.title.strip() or "Researcher"
    log_audit(
        db,
        action="user.profile_updated",
        resource_type="user",
        resource_id=user.id,
        actor_id=user.id,
        details={"organisation": user.organisation, "title": user.title},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> None:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must differ from the current password",
        )
    user.hashed_password = hash_password(payload.new_password)
    log_audit(
        db,
        action="user.password_changed",
        resource_type="user",
        resource_id=user.id,
        actor_id=user.id,
        details={},
        request=request,
    )
    db.commit()


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_role(
    user_id: str,
    payload: RoleUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = user.role
    user.role = payload.role
    log_audit(
        db,
        action="user.role_changed",
        resource_type="user",
        resource_id=user.id,
        actor_id=admin.id,
        details={"from": previous.value, "to": payload.role.value},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user
