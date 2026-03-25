"""Auth-related schemas: login, register, tokens, and password reset payloads."""

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def username_alphanumeric_underscore(cls, v: str) -> str:
        if not _USERNAME_RE.fullmatch(v):
            raise ValueError(
                "username must be 3-32 characters and contain only letters, digits, or underscore"
            )
        return v


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_active: bool


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginJSON(BaseModel):
    """JSON body for POST /auth/login (Swagger still uses OAuth2 form for the same route)."""

    email: EmailStr
    password: str
