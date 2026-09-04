from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Callable

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from yunxi_data_platform.config import PlatformPaths
from yunxi_data_platform.delivery_export import build_delivery_dataset
from yunxi_data_platform.vision_grading import grade_delivery_images
from yunxi_data_platform.excel_transform import (
    build_chemical_composition_long,
    build_merged_dataset,
    build_particle_distribution_long,
    build_quality_metric_long,
    build_specific_batch_master,
)
from yunxi_data_platform.image_inventory import (
    build_batch_image_links,
    build_image_gap_report,
    collect_image_inventory,
)
from yunxi_data_platform.legacy_bridge import read_overall_data, read_specific_data
from yunxi_data_platform.storage import collect_source_files
from yunxi_data_platform.validators import build_validation_issues


@dataclass
class EtlSnapshot:
    source_inventory: pd.DataFrame
    tables: Dict[str, pd.DataFrame]
    summary: dict[str, object]


def _build_batch_master(merged_df: pd.DataFrame) -> pd.DataFrame:
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


def build_snapshot(
    project_root: Path, 
    include_images: bool = False,
    include_auto_grade: bool = True,
    progress_callback: Optional[Callable] = None
) -> EtlSnapshot:
    paths = PlatformPaths.from_root(project_root)
    paths.ensure_directories()

    if progress_callback:
        progress_callback("正在扫描源文件...", 10)
    source_inventory_df = collect_source_files(
        paths,
        include_images=include_images,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback("正在读取锡膏检测数据...", 20)
    overall_df = read_overall_data(paths)

    if progress_callback:
        progress_callback("正在读取锡膏配方数据...", 30)
    specific_raw_df = read_specific_data(paths)

    if progress_callback:
        progress_callback("正在合并匹配数据...", 40)
    merged_df, filtered_df, specific_unique_df = build_merged_dataset(overall_df, specific_raw_df)

    batch_master_df = _build_batch_master(merged_df)
    specific_batch_master_df = build_specific_batch_master(specific_unique_df)
    chemical_detail_df = build_chemical_composition_long(specific_unique_df)
    particle_detail_df = build_particle_distribution_long(specific_unique_df)
    quality_metric_df = build_quality_metric_long(specific_unique_df)

    if include_images:
        if progress_callback:
            progress_callback("正在构建图片清单（仅记录路径，不复制）...", 80)
        image_inventory_df = collect_image_inventory(paths, progress_callback=progress_callback)
        
        if progress_callback:
            progress_callback("正在关联批次图片...", 90)
        image_link_df = build_batch_image_links(filtered_df if not filtered_df.empty else merged_df, image_inventory_df)
        image_gap_df = build_image_gap_report(filtered_df if not filtered_df.empty else merged_df, image_link_df)
    else:
        image_inventory_df = pd.DataFrame()
        image_link_df = pd.DataFrame()
        image_gap_df = pd.DataFrame()

    if progress_callback:
        progress_callback("正在生成交付数据集...", 95)
    delivery_base_df = filtered_df if not filtered_df.empty else merged_df
    delivery_dataset_df = build_delivery_dataset(delivery_base_df, image_link_df)

    # 自动视觉分级：仅当包含图片且开启自动分级时执行（此时 delivery_dataset_df 已含图片路径列）
    if include_images and include_auto_grade:
        try:
            from app.services.vision_service import vision_service
            if progress_callback:
                progress_callback("正在自动分级图片（视觉模型）...", 92)
            delivery_dataset_df = grade_delivery_images(
                delivery_dataset_df,
                vision_service,
                progress_callback=progress_callback,
                project_root=str(project_root),
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[build_snapshot] 自动分级失败，已跳过：{e}")

    validation_df = build_validation_issues(overall_df, specific_raw_df, specific_unique_df, merged_df)
    review_queue_df = pd.concat([validation_df, image_gap_df], ignore_index=True, sort=False)

    if progress_callback:
        progress_callback("数据处理完成", 100)

    tables: Dict[str, pd.DataFrame] = {
        "delivery_dataset": delivery_dataset_df,
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

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "source_files": int(len(source_inventory_df)),
            "delivery_dataset": int(len(delivery_dataset_df)),
            "overall_records": int(len(overall_df)),
            "specific_raw_records": int(len(specific_raw_df)),
            "specific_unique_records": int(len(specific_unique_df)),
            "merged_records": int(len(merged_df)),
            "filtered_records": int(len(filtered_df)),
            "image_inventory_records": int(len(image_inventory_df)),
            "image_link_records": int(len(image_link_df)),
            "validation_issues": int(len(validation_df)),
            "review_queue": int(len(review_queue_df)),
        },
        "datasets": {name: int(len(df)) for name, df in tables.items()},
    }

    return EtlSnapshot(source_inventory=source_inventory_df, tables=tables, summary=summary)
