from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.entities import DatasetRecord, IngestionRun, ReviewIssue, SourceFileInventory, SystemArtifact
from app.schemas.pipeline import (
    ArtifactResponse,
    DatasetListResponse,
    DatasetRowsResponse,
    DatasetSummary,
    PipelineRunRequest,
    PipelineRunResponse,
    UploadedFileListResponse,
    UploadFilesResponse,
)
from app.services.pipeline_service import PipelineService
from app.services.upload_service import list_uploaded_files, save_upload_files
from shared.auth_client import require_admin

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    payload: PipelineRunRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> PipelineRunResponse:
    service = PipelineService(db)

    # 1. 创建运行记录（使用请求作用域的 session，正常提交后随请求关闭）
    run = service.create_run(payload)

    # 2. 将实际处理逻辑放入后台。
    # 注意：后台任务必须使用自己独立创建的 session，绝不能复用本请求的 db ——
    # 否则请求返回后 get_db 会关闭该 session，后台长时间运行会持有/泄漏连接，
    # 最终触发 QueuePool 连接池耗尽（TimeoutError）。
    background_tasks.add_task(_execute_run_in_background, run.id, payload)

    return PipelineRunResponse(
        run_id=run.id,
        status=run.status,
        message=run.message or "任务已加入后台队列",
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary or {},
    )


def _execute_run_in_background(run_id: int, params: PipelineRunRequest) -> None:
    """后台任务：独占一个 session，仅在最终写库阶段占用连接，避免长时间持有。

    pipeline_service.execute_run 内部会在跑完纯计算的 build_snapshot 之后，
    才在写库阶段获取 run 并开启事务，因此 37 分钟的图像分级计算期间不会占用任何
    数据库连接，连接池不会被长时间任务拖垮。
    """
    with SessionLocal() as db:
        service = PipelineService(db)
        service.execute_run(run_id, params)


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(run_id: Optional[int] = None, db: Session = Depends(get_db)) -> DatasetListResponse:
    service = PipelineService(db)
    latest_run = service.get_latest_run()
    target_run_id = run_id or (latest_run.id if latest_run else None)

    if target_run_id is None:
        return DatasetListResponse(run_id=None, datasets=[])

    datasets = service.get_dataset_counts(target_run_id)
    return DatasetListResponse(
        run_id=target_run_id,
        datasets=[DatasetSummary(**item) for item in datasets],
    )


@router.get("/datasets/{dataset_name}", response_model=DatasetRowsResponse)
def get_dataset_rows(
    dataset_name: str,
    run_id: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
) -> DatasetRowsResponse:
    service = PipelineService(db)
    # 数据展示表应始终展示最近一次“成功”运行的数据；只有用户显式传 run_id
    # 或没有任何成功 run 时才回退到任意最新 run，避免最新 run 失败时页面为空。
    latest_run = service.get_latest_run(only_success=True) or service.get_latest_run()
    target_run_id = run_id or (latest_run.id if latest_run else None)
    if target_run_id is None:
        raise HTTPException(status_code=404, detail="暂无可查询的数据集")

    total, rows = service.get_dataset_rows(dataset_name, target_run_id, page, page_size, keyword=keyword)
    return DatasetRowsResponse(
        run_id=target_run_id,
        dataset_name=dataset_name,
        total=total,
        page=page,
        page_size=page_size,
        rows=rows,
    )


@router.get("/review-issues")
def get_review_issues(run_id: Optional[int] = None, db: Session = Depends(get_db)) -> list[dict]:
    service = PipelineService(db)
    latest_run = service.get_latest_run()
    target_run_id = run_id or (latest_run.id if latest_run else None)
    if target_run_id is None:
        return []

    issues = service.get_review_issues(target_run_id)
    return [
        {
            "id": issue.id,
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "entity_type": issue.entity_type,
            "entity_key": issue.entity_key,
            "message": issue.message,
            "source_file": issue.source_file,
            "source_sheet": issue.source_sheet,
            "payload": issue.payload,
        }
        for issue in issues
    ]


@router.get("/source-files")
def get_source_files(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """仅从数据库读，避免在空数据时还去扫盘。"""
    total = db.query(SourceFileInventory).count()
    rows = (
        db.query(SourceFileInventory)
        .order_by(SourceFileInventory.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": [
            {
                "id": row.id,
                "source_type": row.source_type,
                "relative_path": row.relative_path,
                "file_name": row.file_name,
                "file_size": row.file_size,
                "modified_time": row.modified_time,
                "file_hash": row.file_hash,
            }
            for row in rows
        ],
    }


@router.post("/upload-files", response_model=UploadFilesResponse)
async def upload_files(
    dataset_type: str = Query(..., pattern="^(overall|specific|image)$"),
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(default=None),
) -> UploadFilesResponse:
    import logging
    logger = logging.getLogger(__name__)
    settings = get_settings()
    logger.info(f"Upload request received: dataset_type={dataset_type}, files_count={len(files)}")
    logger.info(f"Project root: {settings.project_root}")
    try:
        result = await save_upload_files(Path(settings.project_root), dataset_type, files, relative_paths)
    except ValueError as exc:
        logger.error(f"ValueError during upload: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Unexpected error during upload: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}") from exc
    return UploadFilesResponse(
        saved_files=result["saved_files"],
        skipped=result.get("skipped", []),
        duplicates=result.get("duplicates", []),
    )


@router.get("/uploaded-files", response_model=UploadedFileListResponse)
def get_uploaded_files() -> UploadedFileListResponse:
    settings = get_settings()
    return UploadedFileListResponse(rows=list_uploaded_files(Path(settings.project_root)))


@router.get("/run-readiness")
def get_run_readiness(db: Session = Depends(get_db)) -> dict:
    """判断点击「开始数据匹配」前是否需要提醒用户：当前磁盘文件是否与上次成功匹配一致。

    返回：
      - has_files: 当前上传目录是否有文件
      - file_count: 当前源文件数量
      - source_changed: 当前磁盘文件指纹是否与最近一次成功 run 记录的指纹不同
                        （None 表示尚无成功 run 可比对，视为"有变化"放行）
      - last_run_at: 最近一次成功 run 的完成时间（ISO 字符串），无则 None
    """
    from app.services.upload_service import compute_source_signature
    from app.services.pipeline_service import PipelineService

    settings = get_settings()
    current_sig, current_count = compute_source_signature(Path(settings.project_root))

    service = PipelineService(db)
    last_run = service.get_latest_run(only_success=True)
    last_sig = None
    last_run_at = None
    if last_run is not None:
        summary = last_run.summary if isinstance(last_run.summary, dict) else {}
        last_sig = summary.get("source_signature")
        last_run_at = last_run.completed_at.isoformat() if last_run.completed_at else None

    source_changed = True
    if last_sig is not None:
        source_changed = current_sig != last_sig

    return {
        "has_files": current_count > 0,
        "file_count": current_count,
        "source_changed": source_changed,
        "last_run_at": last_run_at,
    }


@router.delete("/clear-uploads")
def clear_uploads(db: Session = Depends(get_db)) -> dict:
    """清空所有上传文件及由其产生的数据。

    清空范围：
      - 磁盘：uploads/overall、uploads/specific、uploads/image 下的所有文件，
              以及删完文件后残留的空目录（恢复为三个空桶的初始状态）
      - 数据库：source_file_inventory、dataset_records、review_issues、system_artifacts
    注意：保留 ingestion_runs（处理日志），作为执行历史的审计追溯，不在清空范围内。
    """
    import logging

    from yunxi_data_platform.config import PlatformPaths

    logger = logging.getLogger(__name__)
    settings = get_settings()
    project_root = Path(settings.project_root)

    deleted_files = 0
    failed_files = 0

    # 1. 清磁盘上传文件（overall / specific / image 三个目录，只删文件不删目录本身）
    paths = PlatformPaths.from_root(project_root)
    upload_dirs = {
        "overall": paths.overall_upload_dir,
        "specific": paths.specific_upload_dir,
        "image": paths.image_upload_dir,
    }
    for _dataset_type, upload_dir in upload_dirs.items():
        if not upload_dir.exists():
            continue
        for file_path in upload_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    deleted_files += 1
                except Exception as exc:
                    failed_files += 1
                    logger.warning("删除文件失败 %s: %s", file_path, exc)

    # 1b. 删完文件后，自底向上清理残留的空目录，让上传区恢复到干净的初始状态
    #     （只删空目录；非空目录 rmdir 会抛 OSError，直接跳过，绝不误删数据）
    for _dataset_type, upload_dir in upload_dirs.items():
        if not upload_dir.exists():
            continue
        for dir_path in sorted(upload_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if dir_path.is_dir():
                try:
                    dir_path.rmdir()
                except OSError:
                    pass

    # 2. 清数据库表（全量清理，含处理日志）
    db_records: dict[str, int] = {}
    db_records["source_file_inventory"] = db.query(SourceFileInventory).delete()
    db_records["dataset_records"] = db.query(DatasetRecord).delete()
    db_records["review_issues"] = db.query(ReviewIssue).delete()

    # 3. 清系统产物记录，并尝试删除磁盘上的交付文件
    artifacts = db.query(SystemArtifact).all()
    db_records["system_artifacts"] = len(artifacts)
    for artifact in artifacts:
        try:
            artifact_file = Path(artifact.artifact_path)
            if artifact_file.exists():
                artifact_file.unlink()
        except Exception as exc:
            logger.warning("删除产物文件失败 %s: %s", artifact.artifact_path, exc)
    db.query(SystemArtifact).delete()

    db.commit()

    logger.info(
        "清空上传文件完成: 磁盘删除 %d 个文件, 数据库删除 %s",
        deleted_files,
        db_records,
    )

    return {
        "success": failed_files == 0,
        "message": "已清空所有上传文件及关联数据",
        "deleted_files": deleted_files,
        "failed_files": failed_files,
        "deleted_db_records": db_records,
    }


@router.get("/source-graph")
def get_source_graph(
    keyword: str = Query(default=""),
    run_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> dict:
    service = PipelineService(db)
    # 优先展示最近一次“成功”运行的来源追溯数据；若没有任何成功 run
    # （全部失败/进行中），再回退到任意最新 run，避免最新 run 处于
    # running/failed 时其 delivery_dataset 尚未写入导致页面显示 No Data。
    latest_run = service.get_latest_run(only_success=True) or service.get_latest_run()
    target_run_id = run_id or (latest_run.id if latest_run else None)
    if target_run_id is None:
        return {"output_file": None, "keyword": keyword, "nodes": [], "links": [], "rows": []}
    return service.build_source_graph(target_run_id, keyword)


@router.delete("/runs/{run_id}", dependencies=[Depends(require_admin)])
def delete_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    service = PipelineService(db)
    try:
        service.delete_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除处理日志失败: {exc}") from exc
    return {"success": True, "message": "处理日志已删除"}


@router.delete("/runs", dependencies=[Depends(require_admin)])
def clear_runs(db: Session = Depends(get_db)) -> dict:
    """清空全部处理日志（ingestion_runs）。危险操作，仅 Admin。

    仅删除日志表，不影响上传文件、数据集与系统产物。
    """
    try:
        deleted = db.query(IngestionRun).delete()
        db.commit()
        return {"success": True, "message": f"已清空 {deleted} 条处理日志", "deleted": deleted}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清空处理日志失败: {exc}") from exc


@router.get("/runs/export")
def export_runs(db: Session = Depends(get_db)):
    """导出全部处理日志为 Excel(.xlsx)，可直接用 Excel 打开。"""
    import io
    from datetime import datetime
    from urllib.parse import quote

    from openpyxl import Workbook

    runs = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "处理日志"
    headers = [
        "序号", "任务ID", "开始时间", "结束时间", "状态", "触发来源",
        "结果文件地址", "原始文件数", "汇总数据数", "待关联数据量", "处理消息", "是否关联图片",
    ]
    ws.append(headers)
    for i, r in enumerate(runs, 1):
        summary = r.summary if isinstance(r.summary, dict) else {}
        counts = summary.get("counts", {}) or {}
        artifacts = summary.get("artifacts", {}) or {}
        ws.append([
            i,
            r.id,
            r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "",
            r.completed_at.strftime("%Y-%m-%d %H:%M:%S") if r.completed_at else "",
            r.status,
            r.trigger_source,
            artifacts.get("latest_delivery_excel", "") or "",
            counts.get("source_files", 0) or 0,
            counts.get("delivery_dataset", 0) or 0,
            counts.get("review_queue", 0) or 0,
            r.message or "",
            "是" if r.include_images else "否",
        ])
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 20
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"处理日志_{ts}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/artifacts/latest-delivery", response_model=ArtifactResponse)
def get_latest_delivery_artifact(db: Session = Depends(get_db)) -> ArtifactResponse:
    service = PipelineService(db)
    artifact = service.get_artifact("latest_delivery_excel")
    if artifact is None:
        raise HTTPException(status_code=404, detail="暂无最终交付文档")
    
    artifact_path = artifact.artifact_path
    return ArtifactResponse(
        artifact_name=artifact.artifact_name,
        artifact_type=artifact.artifact_type,
        artifact_path=artifact_path,
        exists=Path(artifact_path).exists(),
    )


@router.get("/artifacts/latest-delivery/download")
def download_latest_delivery_artifact(db: Session = Depends(get_db)) -> FileResponse:
    service = PipelineService(db)
    artifact = service.get_artifact("latest_delivery_excel")
    if artifact is None:
        raise HTTPException(status_code=404, detail="暂无最终交付文档")

    artifact_path = Path(artifact.artifact_path)
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="最终交付文档不存在")

    return FileResponse(
        artifact_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=artifact_path.name,
    )
