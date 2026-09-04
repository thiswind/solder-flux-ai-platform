from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from .config import PlatformPaths
from .excel_transform import (
    build_chemical_composition_long,
    build_merged_dataset,
    build_particle_distribution_long,
    build_quality_metric_long,
    build_specific_batch_master,
)
from .image_inventory import build_batch_image_links, build_image_gap_report, collect_image_inventory
from .legacy_bridge import read_overall_data, read_specific_data
from .storage import (
    collect_source_files,
    ensure_database,
    export_excel_tables,
    finish_ingestion_run,
    record_artifact,
    replace_tables,
    start_ingestion_run,
    upsert_source_inventory,
    write_csv_bundle,
    write_json_summary,
)
from .validators import build_validation_issues


@dataclass
class PipelineArtifacts:
    run_id: int
    export_excel_path: Path
    export_csv_dir: Path
    review_excel_path: Path
    summary_json_path: Path


class YunxiDataPlatform:
    def __init__(self, root_dir: str | Path):
        self.paths = PlatformPaths.from_root(root_dir)

    def _build_batch_master(self, merged_df: pd.DataFrame) -> pd.DataFrame:
        if merged_df.empty:
            return pd.DataFrame()

        preferred_columns = [
            "产品批号",
            "生产批号",
            "锡膏型号",
            "助焊膏",
            "助焊剂比例%",
            "合金含量（%）",
            "合金牌号",
            "锡粉批号",
            "Sn",
            "Pb",
            "Ag",
            "Cu",
            "Bi",
            "Sb",
            "氧含量_实测值",
            "球型度_实测值",
            "overall数据源",
            "specific数据源",
        ]
        available_columns = [col for col in preferred_columns if col in merged_df.columns]
        batch_master = merged_df[available_columns].copy()
        batch_master.insert(0, "batch_master_id", range(1, len(batch_master) + 1))
        return batch_master

    def _build_summary(
        self,
        run_id: int,
        source_inventory_df: pd.DataFrame,
        overall_df: pd.DataFrame,
        specific_raw_df: pd.DataFrame,
        specific_unique_df: pd.DataFrame,
        merged_df: pd.DataFrame,
        filtered_df: pd.DataFrame,
        image_inventory_df: pd.DataFrame,
        image_link_df: pd.DataFrame,
        validation_df: pd.DataFrame,
        image_gap_df: pd.DataFrame,
    ) -> Dict[str, object]:
        return {
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "paths": {
                "root_dir": str(self.paths.root_dir),
                "database": str(self.paths.db_path),
                "export_dir": str(self.paths.export_dir),
                "review_dir": str(self.paths.review_dir),
            },
            "counts": {
                "source_files": int(len(source_inventory_df)),
                "overall_records": int(len(overall_df)),
                "specific_raw_records": int(len(specific_raw_df)),
                "specific_unique_records": int(len(specific_unique_df)),
                "merged_records": int(len(merged_df)),
                "filtered_records": int(len(filtered_df)),
                "image_inventory_records": int(len(image_inventory_df)),
                "image_link_records": int(len(image_link_df)),
                "validation_issues": int(len(validation_df)),
                "image_gap_records": int(len(image_gap_df)),
            },
        }

    def run(self, export_tag: Optional[str] = None, include_images: bool = True) -> PipelineArtifacts:
        self.paths.ensure_directories()
        export_suffix = export_tag or datetime.now().strftime("%Y%m%d_%H%M%S")
        export_excel_path = self.paths.export_dir / f"yunxi_platform_export_{export_suffix}.xlsx"
        export_csv_dir = self.paths.export_dir / f"yunxi_platform_export_{export_suffix}"
        review_excel_path = self.paths.review_dir / f"yunxi_review_queue_{export_suffix}.xlsx"
        summary_json_path = self.paths.output_dir / f"run_summary_{export_suffix}.json"

        conn = ensure_database(self.paths)
        run_id = start_ingestion_run(conn)

        try:
            source_inventory_df = collect_source_files(self.paths)
            upsert_source_inventory(conn, source_inventory_df)

            overall_df = read_overall_data(self.paths)
            specific_raw_df = read_specific_data(self.paths)
            merged_df, filtered_df, specific_unique_df = build_merged_dataset(overall_df, specific_raw_df)

            batch_master_df = self._build_batch_master(merged_df)
            specific_batch_master_df = build_specific_batch_master(specific_unique_df)
            chemical_detail_df = build_chemical_composition_long(specific_unique_df)
            particle_detail_df = build_particle_distribution_long(specific_unique_df)
            quality_metric_df = build_quality_metric_long(specific_unique_df)

            if include_images:
                image_inventory_df = collect_image_inventory(self.paths)
                image_link_df = build_batch_image_links(filtered_df if not filtered_df.empty else merged_df, image_inventory_df)
                image_gap_df = build_image_gap_report(filtered_df if not filtered_df.empty else merged_df, image_link_df)
            else:
                image_inventory_df = pd.DataFrame()
                image_link_df = pd.DataFrame()
                image_gap_df = pd.DataFrame()

            validation_df = build_validation_issues(overall_df, specific_raw_df, specific_unique_df, merged_df)
            review_queue_df = pd.concat([validation_df, image_gap_df], ignore_index=True, sort=False)

            tables: Dict[str, pd.DataFrame] = {
                "batch_master": batch_master_df,
                "overall_records": overall_df,
                "specific_raw_records": specific_raw_df,
                "specific_unique_records": specific_unique_df,
                "merged_records": merged_df,
                "filtered_records": filtered_df,
                "specific_batch_master": specific_batch_master_df,
                "chemical_composition_detail": chemical_detail_df,
                "particle_distribution_detail": particle_detail_df,
                "quality_metric_detail": quality_metric_df,
                "image_inventory": image_inventory_df,
                "batch_image_link": image_link_df,
                "validation_issue": validation_df,
                "review_queue": review_queue_df,
            }
            replace_tables(conn, tables)

            export_excel_tables(
                export_excel_path,
                {
                    "Summary": pd.DataFrame([self._build_summary(
                        run_id,
                        source_inventory_df,
                        overall_df,
                        specific_raw_df,
                        specific_unique_df,
                        merged_df,
                        filtered_df,
                        image_inventory_df,
                        image_link_df,
                        validation_df,
                        image_gap_df,
                    )["counts"]]),
                    "BatchMaster": batch_master_df,
                    "MergedData": merged_df,
                    "SpecificBatch": specific_batch_master_df,
                    "ChemicalDetail": chemical_detail_df,
                    "ParticleDetail": particle_detail_df,
                    "QualityDetail": quality_metric_df,
                    "ImageInventory": image_inventory_df,
                    "ImageLink": image_link_df,
                    "ReviewQueue": review_queue_df,
                },
            )
            write_csv_bundle(export_csv_dir, tables)

            export_excel_tables(
                review_excel_path,
                {
                    "ValidationIssues": validation_df,
                    "ImageGap": image_gap_df,
                    "ReviewQueue": review_queue_df,
                },
            )

            summary_payload = self._build_summary(
                run_id,
                source_inventory_df,
                overall_df,
                specific_raw_df,
                specific_unique_df,
                merged_df,
                filtered_df,
                image_inventory_df,
                image_link_df,
                validation_df,
                image_gap_df,
            )
            write_json_summary(summary_json_path, summary_payload)

            record_artifact(conn, "latest_export_excel", export_excel_path, "excel")
            record_artifact(conn, "latest_export_csv_dir", export_csv_dir, "directory")
            record_artifact(conn, "latest_review_excel", review_excel_path, "excel")
            record_artifact(conn, "latest_summary_json", summary_json_path, "json")

            finish_ingestion_run(conn, run_id, "success", "Pipeline completed successfully.")
            return PipelineArtifacts(
                run_id=run_id,
                export_excel_path=export_excel_path,
                export_csv_dir=export_csv_dir,
                review_excel_path=review_excel_path,
                summary_json_path=summary_json_path,
            )
        except Exception as exc:
            finish_ingestion_run(conn, run_id, "failed", str(exc))
            raise
        finally:
            conn.close()
