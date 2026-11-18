from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_PATTERN = r"^\+?[1-9]\d{6,14}$"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    phone_number: str | None = None
    full_name: str
    role: UserRole
    organisation: str
    title: str
    is_active: bool


class RegisterRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    phone_number: str | None = Field(default=None, pattern=PHONE_PATTERN, max_length=32)
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    organisation: str = Field(default="Independent", max_length=200)
    title: str = Field(default="Researcher", max_length=120)
    role: UserRole = UserRole.CONTRIBUTOR


class LoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RoleUpdateRequest(BaseModel):
    role: UserRole


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone_number: str | None = Field(default=None, pattern=PHONE_PATTERN, max_length=32)
    organisation: str = Field(default="Independent", max_length=200)
    title: str = Field(default="Researcher", max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)


class VerifyOtpRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    otp: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=10, max_length=128)
