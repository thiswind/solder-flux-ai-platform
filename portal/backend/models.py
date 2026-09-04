"""SQLAlchemy ORM 模型 — 统一门户用户库。"""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # 角色: Admin(全权 + 管理用户) / Users(日常操作)
    role: Mapped[str] = mapped_column(String(20), default="Users")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 邮箱(注册时必填, 已存在的旧用户允许为空)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
