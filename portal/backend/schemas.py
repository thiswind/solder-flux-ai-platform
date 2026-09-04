"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = Field(..., min_length=3, max_length=120)
    display_name: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = "Users"
    display_name: str | None = None
    email: str | None = None


class UserUpdate(BaseModel):
    password: str | None = None
    role: str | None = None
    display_name: str | None = None
    email: str | None = None
    disabled: bool | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    display_name: str | None
    email: str | None
    disabled: bool
    created_at: str | None
