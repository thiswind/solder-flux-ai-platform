from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_name: str
    database_url: str
    db_ready: bool = False
    database_error: Optional[str] = None


class RunSummaryResponse(BaseModel):
    id: int
    status: str
    include_images: bool
    current_step: Optional[str] = None
    progress_percent: int = 0
    message: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    summary: dict[str, Any] = Field(default_factory=dict)


class DashboardOverviewResponse(BaseModel):
    app_name: str
    latest_run: Optional[RunSummaryResponse] = None
    dataset_counts: list[dict[str, Any]] = Field(default_factory=list)
    review_issue_count: int = 0
    source_file_count: int = 0
    metric_cards: dict[str, int] = Field(default_factory=dict)
    excel_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)
    image_breakdown: dict[str, int] = Field(default_factory=dict)
    image_match_breakdown: dict[str, int] = Field(default_factory=dict)
