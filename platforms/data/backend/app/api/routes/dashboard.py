from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.dashboard import DashboardOverviewResponse, RunSummaryResponse
from app.services.pipeline_service import PipelineService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(db: Session = Depends(get_db)) -> DashboardOverviewResponse:
    settings = get_settings()
    service = PipelineService(db)
    latest_run = service.get_latest_run()

    if latest_run is None:
        latest_run_response = None
        dataset_counts: list[dict] = []
        review_issue_count = 0
    else:
        latest_run_response = RunSummaryResponse(
            id=latest_run.id,
            status=latest_run.status,
            include_images=latest_run.include_images,
            current_step=latest_run.current_step,
            progress_percent=latest_run.progress_percent,
            started_at=latest_run.started_at.isoformat(),
            completed_at=latest_run.completed_at.isoformat() if latest_run.completed_at else None,
            message=latest_run.message,
            summary=latest_run.summary or {},
        )
        dataset_counts = service.get_dataset_counts(latest_run.id)
        review_issue_count = (latest_run.summary or {}).get("counts", {}).get("review_queue", 0)

    # 使用最新成功记录计算统计数据
    latest_success_run = service.get_latest_run(only_success=True)
    overview_metrics = service.build_dashboard_metrics(latest_success_run)

    # source_file_count 与 metric_cards 保持一致：无文件时归零（避免清空后前端按钮仍可点击）
    raw_source_count = service.get_source_inventory_count()
    source_file_count = overview_metrics["metric_cards"].get("已导入文件数", raw_source_count)

    return DashboardOverviewResponse(
        app_name=settings.app_name,
        latest_run=latest_run_response,
        dataset_counts=dataset_counts,
        review_issue_count=review_issue_count,
        source_file_count=source_file_count,
        metric_cards=overview_metrics["metric_cards"],
        excel_breakdown=overview_metrics["excel_breakdown"],
        image_breakdown=overview_metrics["image_breakdown"],
        image_match_breakdown=overview_metrics["image_match_breakdown"],
    )


@router.get("/runs", response_model=list[RunSummaryResponse])
def list_runs(db: Session = Depends(get_db)) -> list[RunSummaryResponse]:
    service = PipelineService(db)
    runs = service.list_runs()
    return [
        RunSummaryResponse(
            id=run.id,
            status=run.status,
            include_images=run.include_images,
            current_step=run.current_step,
            progress_percent=run.progress_percent,
            started_at=run.started_at.isoformat(),
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            message=run.message,
            summary=run.summary or {},
        )
        for run in runs
    ]
