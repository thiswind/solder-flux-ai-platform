from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    include_images: bool = Field(default=False, description="是否包含图片盘点与关联")
    include_auto_grade: bool = Field(default=True, description="包含图片时是否执行视觉模型自动分级")
    trigger_source: str = Field(default="manual", description="任务触发来源")


class PipelineRunResponse(BaseModel):
    run_id: int
    status: str
    message: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    summary: dict[str, Any] = Field(default_factory=dict)


class DatasetSummary(BaseModel):
    dataset_name: str
    row_count: int


class DatasetListResponse(BaseModel):
    run_id: Optional[int] = None
    datasets: list[DatasetSummary] = Field(default_factory=list)


class DatasetRowsResponse(BaseModel):
    run_id: Optional[int] = None
    dataset_name: str
    total: int
    page: int
    page_size: int
    rows: list[dict[str, Any]] = Field(default_factory=list)


class UploadedFileRecord(BaseModel):
    dataset_type: str
    file_name: str
    absolute_path: str
    relative_path: str
    file_size: int
    modified_time: str


class SkippedFileRecord(BaseModel):
    filename: str
    reason: str


class DuplicateFileRecord(BaseModel):
    filename: str
    existing: str


class UploadFilesResponse(BaseModel):
    saved_files: list[UploadedFileRecord] = Field(default_factory=list)
    skipped: list[SkippedFileRecord] = Field(default_factory=list)
    duplicates: list[DuplicateFileRecord] = Field(default_factory=list)


class UploadedFileListResponse(BaseModel):
    rows: list[UploadedFileRecord] = Field(default_factory=list)


class ArtifactResponse(BaseModel):
    artifact_name: str
    artifact_type: str
    artifact_path: str
    exists: bool = True
