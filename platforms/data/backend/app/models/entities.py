from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    include_images: Mapped[bool] = mapped_column(default=True, nullable=False)
    current_step: Mapped[Optional[str]] = mapped_column(String(255))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class SourceFileInventory(Base, TimestampMixin):
    __tablename__ = "source_file_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    absolute_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_time: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class DatasetRecord(Base, TimestampMixin):
    __tablename__ = "dataset_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    business_key: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    run: Mapped[IngestionRun] = relationship(backref="dataset_records")


class ReviewIssue(Base, TimestampMixin):
    __tablename__ = "review_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[Optional[str]] = mapped_column(String(32))
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_key: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(Text)
    source_sheet: Mapped[Optional[str]] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    run: Mapped[IngestionRun] = relationship(backref="review_issues")


class SystemArtifact(Base, TimestampMixin):
    __tablename__ = "system_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
