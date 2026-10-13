from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    society_ids: list[int] = []     # societies this admin will manage


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str | None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v