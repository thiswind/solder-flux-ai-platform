from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import DatasetRecord, IngestionRun, ReviewIssue, SourceFileInventory, SystemArtifact
from app.schemas.pipeline import PipelineRunRequest
from app.services.legacy_etl import build_snapshot
from yunxi_data_platform.config import PlatformPaths
from yunxi_data_platform.delivery_export import build_delivery_filtered_sheet
from yunxi_data_platform.storage import export_excel_tables


def _sanitize_payload(value: Any) -> Any:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


class PipelineService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _dataset_business_key(self, dataset_name: str, row: dict[str, Any]) -> Optional[str]:
        for field in ("产品批号", "生产批号", "entity_key", "relative_path", "file_hash", "batch_master_id"):
            value = row.get(field)
            if value is not None and str(value).strip():
                return str(value)
        return f"{dataset_name}:{row.get('row_index', '')}" if row else None

    def _replace_source_inventory(self, rows: list[dict[str, Any]]) -> None:
        self.db.query(SourceFileInventory).delete()
        if rows:
            self.db.bulk_insert_mappings(SourceFileInventory, rows)

    def _replace_artifact(self, artifact_name: str, artifact_type: str, artifact_path: str) -> None:
        existing = self.db.scalar(select(SystemArtifact).where(SystemArtifact.artifact_name == artifact_name))
        if existing is None:
            existing = SystemArtifact(
                artifact_name=artifact_name,
                artifact_type=artifact_type,
                artifact_path=artifact_path,
            )
            self.db.add(existing)
        else:
            existing.artifact_type = artifact_type
            existing.artifact_path = artifact_path

    def _export_delivery_excel(self, run_id: int, delivery_df: pd.DataFrame) -> Optional[Path]:
        if delivery_df.empty:
            return None
        paths = PlatformPaths.from_root(self.settings.project_root)
        paths.ensure_directories()
        export_path = paths.export_dir / f"yunxi_delivery_run_{run_id}.xlsx"
        filtered_df = build_delivery_filtered_sheet(delivery_df)
        export_excel_tables(
            export_path,
            {
                "filtered": filtered_df,
                "raw": delivery_df,
            },
        )
        return export_path

    def create_run(self, params: PipelineRunRequest) -> IngestionRun:
        run = IngestionRun(
            trigger_source=params.trigger_source,
            include_images=params.include_images,
            status="running",
            current_step="初始化...",
            progress_percent=0
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def execute_run(self, run_id: int, params: PipelineRunRequest):
        # 注意：不要在函数开头就 self.db.get(run) —— 那样会立刻开启一个事务并
        # 把连接占用整整一次 ETL（可能几十分钟），期间连接池被长期占据，容易引发
        # QueuePool 连接池耗尽（TimeoutError）。
        # 正确做法：先跑完纯计算的 build_snapshot（不碰数据库），最后写库阶段再获取
        # run 并开启事务，写完后随 session 关闭归还连接。
        run = None
        import time
        last_db_update = [0.0]
        last_percent = [-1]
        last_step = [""]

        def progress_callback(step: str, percent: int):
            now = time.time()
            # 避免高频刷库：相同步骤和相同百分比，或间隔过短的更新直接跳过
            if percent == last_percent[0] and step == last_step[0]:
                return
            if now - last_db_update[0] < 1.0:
                return
            last_db_update[0] = now
            last_percent[0] = percent
            last_step[0] = step
            # 用独立 session 更新进度，避免 commit 阻塞 ETL 主线程。
            # execute_run 自身的 session 只负责最终状态写入。
            try:
                with SessionLocal() as progress_db:
                    progress_db.execute(
                        update(IngestionRun)
                        .where(IngestionRun.id == run_id)
                        .values(current_step=step, progress_percent=percent)
                    )
                    progress_db.commit()
            except Exception as exc:
                print(
                    f"[progress_callback] failed to update progress for run {run_id}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

        try:
            # 执行 ETL
            snapshot = build_snapshot(
                self.settings.project_root, 
                include_images=params.include_images,
                include_auto_grade=params.include_auto_grade,
                progress_callback=progress_callback
            )

            source_rows = [
                {key: _sanitize_payload(value) for key, value in row.items()}
                for row in snapshot.source_inventory.to_dict("records")
            ]

            # 写库阶段：此时才获取 run 并开启事务。build_snapshot 已跑完，连接仅占用数秒。
            run = self.db.get(IngestionRun, run_id)
            if not run:
                return
            self._replace_source_inventory(source_rows)

            dataset_records: list[dict[str, Any]] = []
            review_issue_records: list[dict[str, Any]] = []

            for dataset_name, df in snapshot.tables.items():
                for row_index, row in enumerate(df.to_dict("records")):
                    payload = {key: _sanitize_payload(value) for key, value in row.items()}
                    dataset_records.append(
                        {
                            "run_id": run.id,
                            "dataset_name": dataset_name,
                            "row_index": row_index,
                            "business_key": self._dataset_business_key(dataset_name, payload),
                            "payload": payload,
                        }
                    )

                    if dataset_name == "review_queue":
                        review_issue_records.append(
                            {
                                "run_id": run.id,
                                "issue_type": str(payload.get("issue_type", "review_issue")),
                                "severity": payload.get("severity"),
                                "entity_type": payload.get("entity_type"),
                                "entity_key": str(payload.get("entity_key") or payload.get("产品批号") or payload.get("生产批号") or ""),
                                "message": str(payload.get("message", "")),
                                "source_file": payload.get("source_file") or payload.get("overall数据源") or payload.get("specific数据源"),
                                "source_sheet": payload.get("source_sheet"),
                                "payload": payload,
                            }
                        )

            self.db.bulk_insert_mappings(DatasetRecord, dataset_records)
            self.db.query(ReviewIssue).filter(ReviewIssue.run_id == run.id).delete()
            if review_issue_records:
                self.db.bulk_insert_mappings(ReviewIssue, review_issue_records)

            summary = snapshot.summary
            delivery_export_path = self._export_delivery_excel(
                run.id,
                snapshot.tables.get("delivery_dataset", pd.DataFrame()),
            )
            if delivery_export_path is not None:
                self._replace_artifact("latest_delivery_excel", "excel", str(delivery_export_path))
                summary = {
                    **summary,
                    "delivery_export": {
                        "raw_rows": int(len(snapshot.tables.get("delivery_dataset", pd.DataFrame()))),
                        "filtered_rows": int(len(build_delivery_filtered_sheet(snapshot.tables.get("delivery_dataset", pd.DataFrame())))),
                        "sheet_names": ["filtered", "raw"],
                    },
                    "artifacts": {
                        **summary.get("artifacts", {}),
                        "latest_delivery_excel": str(delivery_export_path),
                    },
                }
            # 记录本次跑批使用的源文件指纹，供「未上传新文件」拦截判断使用。
            # 仅在成功收尾阶段写入，失败/中断的 run 不会污染比对基准。
            try:
                from app.services.upload_service import compute_source_signature
                from pathlib import Path as _Path

                sig, sig_count = compute_source_signature(_Path(self.settings.project_root))
                summary["source_signature"] = sig
                summary["source_file_count"] = sig_count
            except Exception:
                pass

            run.summary = summary
            run.status = "success"
            run.message = "数据处理完成"
            run.completed_at = datetime.utcnow()

            self._replace_artifact("latest_run", "run", str(run.id))
            self.db.commit()
        except Exception as exc:
            print(f"ETL execution failed: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            try:
                run = self.db.get(IngestionRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.message = str(exc)
                    run.completed_at = datetime.utcnow()
                    self.db.commit()
            except Exception as inner_exc:
                print(f"failed to mark run {run_id} as failed: {inner_exc}", file=sys.stderr)

    def run_pipeline(self, params: PipelineRunRequest) -> IngestionRun:
        # 这个方法现在只保留用于同步调用（如测试），实际 Web 调用改用 execute_run
        run = self.create_run(params)
        self.execute_run(run.id, params)
        return run

    def get_latest_run(self, only_success: bool = False) -> Optional[IngestionRun]:
        query = select(IngestionRun)
        if only_success:
            query = query.where(IngestionRun.status == "success")
        return self.db.scalar(query.order_by(IngestionRun.id.desc()).limit(1))

    def get_artifact(self, artifact_name: str) -> Optional[SystemArtifact]:
        return self.db.scalar(select(SystemArtifact).where(SystemArtifact.artifact_name == artifact_name))

    def list_runs(self, limit: int = 20) -> list[IngestionRun]:
        return list(self.db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit)))

    def get_dataset_counts(self, run_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(DatasetRecord.dataset_name, func.count(DatasetRecord.id))
            .where(DatasetRecord.run_id == run_id)
            .group_by(DatasetRecord.dataset_name)
            .order_by(DatasetRecord.dataset_name)
        ).all()
        return [{"dataset_name": name, "row_count": count} for name, count in rows]

    def get_dataset_rows(
        self,
        dataset_name: str,
        run_id: int,
        page: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        conditions = [
            DatasetRecord.run_id == run_id,
            DatasetRecord.dataset_name == dataset_name,
        ]
        # 按产品批号模糊搜索（JSONB 字段提取文本后做 LIKE）
        if keyword:
            conditions.append(DatasetRecord.payload["产品批号"].astext.like(f"%{keyword}%"))

        total = self.db.scalar(
            select(func.count(DatasetRecord.id)).where(*conditions)
        ) or 0

        rows = self.db.scalars(
            select(DatasetRecord)
            .where(*conditions)
            .order_by(DatasetRecord.row_index)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return total, [row.payload for row in rows]

    def get_review_issues(self, run_id: int, limit: int = 200) -> list[ReviewIssue]:
        return list(
            self.db.scalars(
                select(ReviewIssue)
                .where(ReviewIssue.run_id == run_id)
                .order_by(ReviewIssue.created_at.desc())
                .limit(limit)
            )
        )

    def get_source_inventory_count(self) -> int:
        return self.db.scalar(select(func.count(SourceFileInventory.id))) or 0

    def list_source_inventory(self, limit: int = 300) -> list[SourceFileInventory]:
        return list(
            self.db.scalars(
                select(SourceFileInventory)
                .order_by(SourceFileInventory.updated_at.desc())
                .limit(limit)
            )
        )

    def build_dashboard_metrics(self, latest_run: Optional[IngestionRun]) -> dict[str, object]:
        # 已导入文件数为 0 时，强制全部指标归零（避免残留的旧 run 数据导致显示不一致）
        source_count = int(self.get_source_inventory_count())
        if source_count == 0:
            return {
                "metric_cards": {
                    "已导入文件数": 0,
                    "Excel数据行数": 0,
                    "图片齐全记录数": 0,
                    "待补图记录数": 0,
                },
                "excel_breakdown": {"有铅": {"overall": 0, "specific": 0}, "无铅": {"overall": 0, "specific": 0}},
                "image_breakdown": {"有铅": 0, "无铅": 0},
                "image_match_breakdown": {"有铅": 0, "无铅": 0},
            }

        # Excel 行数：从 dataset_records 表实时统计（不再依赖 ingestion_runs.summary 缓存 JSON，
        # 避免清空数据后 Dashboard 仍显示旧值）
        # 注意：dataset_name 与 legacy_etl.py build_snapshot 返回的 tables key 保持一致
        excel_row_count = 0
        if latest_run is not None:
            for ds_name in ("overall_records", "specific_raw_records"):
                total, _ = self.get_dataset_rows(ds_name, latest_run.id, page=1, page_size=1)
                excel_row_count += total
        delivery_ready_count = self._build_delivery_ready_count(latest_run)
        return {
            "metric_cards": {
                "已导入文件数": int(self.get_source_inventory_count()),
                "Excel数据行数": excel_row_count,
                "图片齐全记录数": delivery_ready_count,
                "待补图记录数": max(0, excel_row_count - delivery_ready_count),
            },
            "excel_breakdown": self._build_excel_breakdown(),
            "image_breakdown": self._build_image_breakdown(latest_run),
            "image_match_breakdown": self._build_image_match_breakdown(latest_run),
        }

    def _infer_lead_group(self, source: SourceFileInventory) -> str:
        text = f"{source.relative_path} {source.file_name}"
        if "有铅" in text:
            return "有铅"
        if "无铅" in text:
            return "无铅"
        return "未知"

    def _build_excel_breakdown(self) -> dict[str, dict[str, int]]:
        breakdown = {
            "有铅": {"overall": 0, "specific": 0},
            "无铅": {"overall": 0, "specific": 0},
        }
        sources = self.list_source_inventory(limit=50000)
        for source in sources:
            lead_group = self._infer_lead_group(source)
            if lead_group not in breakdown:
                continue
            if "overall" in source.source_type and "excel" in source.source_type:
                breakdown[lead_group]["overall"] += 1
            elif "specific" in source.source_type and "excel" in source.source_type:
                breakdown[lead_group]["specific"] += 1
        return breakdown

    def _build_image_breakdown(self, latest_run: Optional[IngestionRun]) -> dict[str, int]:
        breakdown = {"有铅": 0, "无铅": 0}
        if latest_run is not None:
            image_rows = self.get_dataset_rows("image_inventory", latest_run.id, page=1, page_size=50000)[1]
            for row in image_rows:
                lead_group = str(row.get("top_level_dir") or "")
                if lead_group not in breakdown:
                    text = f"{row.get('absolute_path', '')} {row.get('relative_path', '')}"
                    if "有铅" in text:
                        lead_group = "有铅"
                    elif "无铅" in text:
                        lead_group = "无铅"
                if lead_group in breakdown:
                    breakdown[lead_group] += 1
            if sum(breakdown.values()) > 0:
                return breakdown

        sources = self.list_source_inventory(limit=50000)
        for source in sources:
            lead_group = self._infer_lead_group(source)
            if lead_group not in breakdown:
                continue
            if "image" in source.source_type:
                breakdown[lead_group] += 1
        return breakdown

    def _build_image_match_breakdown(self, latest_run: Optional[IngestionRun]) -> dict[str, int]:
        breakdown = {"有铅": 0, "无铅": 0}
        if latest_run is None:
            return breakdown

        image_link_rows = self.get_dataset_rows("batch_image_link", latest_run.id, page=1, page_size=50000)[1]
        for row in image_link_rows:
            lead_group = str(row.get("image_lead_group") or "")
            if lead_group in breakdown:
                breakdown[lead_group] += 1
        return breakdown

    def _build_delivery_ready_count(self, latest_run: Optional[IngestionRun]) -> int:
        if latest_run is None:
            return 0

        delivery_rows = self.get_dataset_rows("delivery_dataset", latest_run.id, page=1, page_size=50000)[1]
        required_image_fields = (
            "Wetting_Image_Path",
            "SolderBall_Image_Path",
            "Collapse_Image_Path",
            "Stability_Image_Path",
        )

        return sum(
            1
            for row in delivery_rows
            if all(str(row.get(field) or "").strip() for field in required_image_fields)
        )

    def delete_run(self, run_id: int) -> None:
        run = self.db.get(IngestionRun, run_id)
        if run is None:
            raise ValueError("处理记录不存在")

        artifact_path = str((run.summary or {}).get("artifacts", {}).get("latest_delivery_excel") or "")
        if artifact_path and Path(artifact_path).exists():
            try:
                os.remove(artifact_path)
            except OSError:
                pass

        self.db.query(DatasetRecord).filter(DatasetRecord.run_id == run_id).delete()
        self.db.query(ReviewIssue).filter(ReviewIssue.run_id == run_id).delete()
        self.db.delete(run)
        self.db.commit()

        latest_run = self.get_latest_run()
        latest_delivery_artifact = self.get_artifact("latest_delivery_excel")
        latest_run_artifact = self.get_artifact("latest_run")

        if latest_run_artifact is not None:
            if latest_run is None:
                self.db.delete(latest_run_artifact)
            else:
                latest_run_artifact.artifact_path = str(latest_run.id)

        latest_success = self.db.scalar(
            select(IngestionRun)
            .where(IngestionRun.status == "success")
            .order_by(IngestionRun.id.desc())
            .limit(1)
        )
        if latest_delivery_artifact is not None:
            latest_path = str((latest_success.summary or {}).get("artifacts", {}).get("latest_delivery_excel") or "") if latest_success else ""
            if not latest_path:
                self.db.delete(latest_delivery_artifact)
            else:
                latest_delivery_artifact.artifact_path = latest_path
        self.db.commit()

    def build_source_graph(self, run_id: int, keyword: str = "") -> dict[str, Any]:
        keyword_norm = keyword.strip().lower()
        
        # 如果指定了 run_id，直接使用；否则使用最新成功的任务
        if run_id is None:
            latest_run = self.get_latest_run(only_success=True)
            if latest_run is None:
                return {"output_file": None, "keyword": keyword, "nodes": [], "links": [], "rows": []}
            run_id = latest_run.id
        
        total, rows = self.get_dataset_rows("delivery_dataset", run_id, page=1, page_size=1000)
        _ = total

        artifact = self.get_artifact("latest_delivery_excel")
        output_label = Path(artifact.artifact_path).name if artifact else "最终汇总文件"

        nodes: list[dict[str, Any]] = [
            {"id": "delivery", "label": output_label, "group": "output", "size": 28},
        ]
        links: list[dict[str, Any]] = []
        source_nodes: dict[str, dict[str, Any]] = {}
        image_nodes: dict[str, dict[str, Any]] = {}
        result_rows: list[dict[str, Any]] = []

        for row in rows:
            overall_source = str(row.get("overall数据源") or "").strip()
            specific_source = str(row.get("specific数据源") or "").strip()
            product_batch = str(row.get("产品批号") or "").strip()
            production_batch = str(row.get("生产批号") or "").strip()
            wetting_img = str(row.get("Wetting_Image_Path") or "").strip()
            
            search_blob = " ".join([product_batch, production_batch, overall_source, specific_source]).lower()
            if keyword_norm and keyword_norm not in search_blob:
                continue

            result_rows.append(
                {
                    "批号": product_batch or production_batch,
                    "overall数据源": overall_source,
                    "specific数据源": specific_source,
                    "图片关联": wetting_img,
                }
            )

            # 添加源文件节点
            for group_name, source_value in (("overall", overall_source), ("specific", specific_source)):
                if not source_value:
                    continue
                node_id = f"{group_name}:{source_value}"
                if node_id not in source_nodes:
                    source_nodes[node_id] = {
                        "id": node_id,
                        "label": source_value,
                        "group": group_name,
                        "size": 16,
                    }
                    links.append({"source": node_id, "target": "delivery"})

            # 添加图片节点
            if wetting_img:
                img_name = Path(wetting_img).name
                node_id = f"image:{wetting_img}"
                if node_id not in image_nodes:
                    image_nodes[node_id] = {
                        "id": node_id,
                        "label": img_name,
                        "group": "image",
                        "full_path": wetting_img,
                        "batch": product_batch or production_batch
                    }
                    links.append({"source": node_id, "target": "delivery"})

        nodes.extend(source_nodes.values())
        nodes.extend(image_nodes.values())
        return {
            "output_file": artifact.artifact_path if artifact else None,
            "keyword": keyword,
            "nodes": nodes,
            "links": links,
            "rows": result_rows[:200],
        }
