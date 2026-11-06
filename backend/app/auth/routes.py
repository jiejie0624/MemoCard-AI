import re
import os
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.auth.repository import DuplicateEmailError, PostgresAuthRepository
from backend.app.auth.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "memocard_session"
SESSION_LIFETIME = timedelta(days=7)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return _validated_timezone(value)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validated_timezone(value) if value is not None else None

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "ProfileUpdate":
        if self.display_name is None and self.timezone is None:
            raise ValueError("At least one profile field must be provided")
        return self


class PublicUser(BaseModel):
    id: UUID
    email: str
    display_name: str
    timezone: str
    created_at: datetime


def _validated_timezone(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Timezone cannot be blank")
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Use a valid IANA timezone") from error
    return normalized


def get_repository() -> PostgresAuthRepository:
    return PostgresAuthRepository()


Repository = Annotated[PostgresAuthRepository, Depends(get_repository)]


def _set_session_cookie(response: Response, token: str) -> None:
    # Cookies stay secure by default; local HTTP development can opt out explicitly.
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=_cookie_is_secure(),
        samesite="lax",
        path="/",
    )


def _cookie_is_secure() -> bool:
    return os.getenv("APP_ENV", "production").lower() != "development"


def _start_session(response: Response, repository: PostgresAuthRepository, user_id: UUID) -> None:
    token = create_session_token()
    repository.create_session(user_id, hash_session_token(token))
    _set_session_cookie(response, token)


def current_user(
    repository: Repository,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> PublicUser:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = repository.get_user_for_session(hash_session_token(token))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return PublicUser.model_validate(user)


@router.post("/register", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
def register(payload: Registration, response: Response, repository: Repository) -> PublicUser:
    try:
        user = repository.create_user(
            payload.email,
            hash_password(payload.password),
            payload.display_name,
            payload.timezone,
        )
    except DuplicateEmailError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from error
    _start_session(response, repository, user["id"])
    return PublicUser.model_validate(user)


@router.post("/login", response_model=PublicUser)
def login(payload: Credentials, response: Response, repository: Repository) -> PublicUser:
    user = repository.get_user_by_email(payload.email)
    stored_hash = user["password_hash"] if user is not None else None
    if not verify_password(payload.password, stored_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    _start_session(response, repository, user["id"])
    return PublicUser.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    repository: Repository,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    if token:
        repository.revoke_session(hash_session_token(token))
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=_cookie_is_secure(),
        samesite="lax",
    )
    return response


@router.get("/me", response_model=PublicUser)
def get_profile(user: Annotated[PublicUser, Depends(current_user)]) -> PublicUser:
    return user


@router.patch("/me", response_model=PublicUser)
def update_profile(
    payload: ProfileUpdate,
    user: Annotated[PublicUser, Depends(current_user)],
    repository: Repository,
) -> PublicUser:
    updated = repository.update_profile(user.id, payload.display_name, payload.timezone)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return PublicUser.model_validate(updated)
