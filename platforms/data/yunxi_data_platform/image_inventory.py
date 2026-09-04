from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .config import PlatformPaths

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
BATCH_PATTERN = re.compile(r"\d{5,}[A-Z]?\d*", re.IGNORECASE)
TRAILING_SPEC_PATTERN = re.compile(r"\s+(4A|4B|5A|5B|-\d+)$", re.IGNORECASE)
LEAD_GROUPS = {"有铅", "无铅"}


def normalize_token(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[^0-9A-Za-z]+", "", str(value).upper())


def extract_batch_candidate(path: Path) -> str:
    """
    根据用户要求：图片的所在目录下最后一层目录的名称必定包含了生产批号或者产品批号。
    """
    last_dir = path.name
    matches = BATCH_PATTERN.findall(last_dir)
    if matches:
        return normalize_token(matches[-1])

    # 如果最后一层没找到，尝试向上找一层（兼容性）
    for part in reversed(path.parts):
        matches = BATCH_PATTERN.findall(part)
        if matches:
            return normalize_token(matches[-1])
    return ""


def classify_image(file_path: Path) -> str:
    stem_upper = file_path.stem.upper()
    if "0001" in stem_upper:
        return "Wetting"
    if "0002" in stem_upper:
        return "SolderBall"
    if "0003" in stem_upper:
        return "Collapse"
    return "Stability"


def _extract_model_name(model_dir_name: str, alloy_name: str) -> str:
    cleaned = model_dir_name.strip()
    alloy_clean = alloy_name.strip()
    if alloy_clean and alloy_clean in cleaned:
        cleaned = cleaned.split(alloy_clean, 1)[0].strip()
    cleaned = TRAILING_SPEC_PATTERN.sub("", cleaned).strip()
    return cleaned or model_dir_name.strip()


def _scan_batch_tree(
    start_dir: Path,
    model_name: str,
    lead_group_name: str,
    root_label: str,
    platform_root: Path,
    timeout: Optional[float] = None,
    start_time: float = 0.0,
    records: Optional[List[Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """从 model 下一层开始递归扫描，兼容不同深度的目录结构。

    实际数据可能是 3 层（有铅/型号/批号/图片）或 4 层（有铅/型号/规格/日期批号/图片）
    甚至更多层。本函数递归到叶子目录，用**图片文件的直接父目录名**提取批号候选。
    """
    if records is None:
        records = []
    if not start_dir.is_dir():
        return records

    # 先尝试在当前层找文件；如果找到文件则本层就是"批号层"
    has_files = False
    for entry in start_dir.iterdir():
        if timeout is not None and time.time() - start_time > timeout:
            break
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            has_files = True
            stat = entry.stat()
            records.append(
                {
                    "source_root_type": root_label,
                    "absolute_path": str(entry),
                    "relative_path": str(entry.relative_to(platform_root)),
                    "file_name": entry.name,
                    "file_size": stat.st_size,
                    "modified_time": pd.Timestamp(stat.st_mtime, unit="s").isoformat(),
                    "image_category": classify_image(entry),
                    "batch_candidate": extract_batch_candidate(start_dir),
                    "model_candidate": normalize_token(model_name),
                    "model_display_name": model_name,
                    "top_level_dir": lead_group_name,
                    "parent_dir_name": start_dir.name,
                    "directory_path": str(start_dir),
                }
            )
        elif entry.is_dir() and not has_files:
            # 当前层还没发现文件时，递归进入子目录
            _scan_batch_tree(
                entry, model_name, lead_group_name, root_label, platform_root,
                timeout=timeout, start_time=start_time, records=records,
            )
    return records


def _collect_local_images(
    root: Path, root_label: str, platform_root: Path, timeout: Optional[float] = None
) -> List[Dict[str, object]]:
    if not root.exists():
        return []

    records: List[Dict[str, object]] = []
    start = time.time()
    for lead_group_dir in root.iterdir():
        if timeout is not None and time.time() - start > timeout:
            print(
                f"[image_inventory] local scan timeout after {timeout:.1f}s at {root}",
                flush=True,
            )
            break
        if not lead_group_dir.is_dir() or lead_group_dir.name not in LEAD_GROUPS:
            continue
        for model_dir in lead_group_dir.iterdir():
            if timeout is not None and time.time() - start > timeout:
                print(
                    f"[image_inventory] local scan timeout after {timeout:.1f}s at {root}",
                    flush=True,
                )
                break
            if not model_dir.is_dir():
                continue
            # 从 model 下一层开始递归扫描（兼容 3 层 / 4 层 / 更深结构）
            _scan_batch_tree(
                model_dir, model_dir.name, lead_group_dir.name,
                root_label, platform_root, timeout=timeout, start_time=start,
                records=records,
            )
    return records


def collect_image_inventory(
    paths: PlatformPaths,
    progress_callback: Optional[callable] = None,
    external_timeout: float = 120.0,
    local_timeout: float = 60.0,
) -> pd.DataFrame:
    records: List[Dict[str, object]] = []
    report_every = 500

    # 扫描用户上传的图片目录（uploads/image），与 Excel 一样只从上传目录读取
    for idx, rec in enumerate(
        _collect_local_images(
            paths.image_upload_dir, "uploaded_image", paths.root_dir, timeout=local_timeout
        )
    ):
        records.append(rec)
        if progress_callback and (idx + 1) % report_every == 0:
            progress_callback(
                f"构建图片清单（上传图片已扫描 {idx + 1} 张）",
                min(89, 80 + (idx + 1) // report_every),
            )

    inventory_df = pd.DataFrame(records)
    if inventory_df.empty:
        return pd.DataFrame(
            columns=[
                "image_id",
                "source_root_type",
                "absolute_path",
                "relative_path",
                "file_name",
                "file_size",
                "modified_time",
                "image_category",
                "batch_candidate",
                "model_candidate",
                "model_display_name",
                "top_level_dir",
                "parent_dir_name",
                "directory_path",
            ]
        )

    inventory_df.insert(0, "image_id", range(1, len(inventory_df) + 1))
    return inventory_df


def _build_merged_match_records(row: pd.Series) -> List[Tuple[str, str, str]]:
    candidates: List[Tuple[str, str, str]] = []
    product_batch = normalize_token(row.get("产品批号"))
    production_batch = normalize_token(row.get("生产批号"))

    if product_batch:
        candidates.append(("产品批号", product_batch, "产品批号"))
    if production_batch:
        candidates.append(("生产批号", production_batch, "生产批号"))
    return candidates


def _extract_model_from_row(row: pd.Series) -> str:
    for column in ("锡膏型号", "助焊膏"):
        value = normalize_token(row.get(column))
        if value:
            return value
    return ""


def build_batch_image_links(merged_df: pd.DataFrame, image_inventory_df: pd.DataFrame) -> pd.DataFrame:
    if merged_df.empty or image_inventory_df.empty:
        return pd.DataFrame()

    images = image_inventory_df.copy()
    images["batch_candidate_norm"] = images["batch_candidate"].map(normalize_token)
    images["model_candidate_norm"] = images["model_candidate"].map(normalize_token)
    images = images[images["batch_candidate_norm"].ne("")]
    if images.empty:
        return pd.DataFrame()

    grouped_images = {
        batch: group.to_dict("records")
        for batch, group in images.groupby("batch_candidate_norm", dropna=False)
    }

    link_records: List[Dict[str, object]] = []
    seen_keys = set()

    for _, row in merged_df.iterrows():
        row_model = _extract_model_from_row(row)
        row_source = row.get("specific数据源") or row.get("overall数据源")
        row_lead_group = "有铅" if pd.notna(row.get("Pb")) and str(row.get("Pb")).strip() not in {"", "0", "0.0"} else "无铅"

        for batch_field, batch_value, batch_origin in _build_merged_match_records(row):
            for image_record in grouped_images.get(batch_value, []):
                image_model = image_record.get("model_candidate_norm", "")
                image_lead_group = image_record.get("top_level_dir")

                if row_model and image_model and (row_model in image_model or image_model in row_model):
                    match_rule = "batch_and_model_fuzzy"
                    match_confidence = "high"
                elif image_lead_group == row_lead_group:
                    match_rule = "batch_and_lead_group"
                    match_confidence = "medium"
                else:
                    match_rule = "batch_only"
                    match_confidence = "low"

                dedupe_key = (row.get("产品批号"), row.get("生产批号"), image_record["absolute_path"])
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)

                link_records.append(
                    {
                        "产品批号": row.get("产品批号"),
                        "生产批号": row.get("生产批号"),
                        "锡膏型号": row.get("锡膏型号"),
                        "助焊膏": row.get("助焊膏"),
                        "matched_batch_field": batch_field,
                        "matched_batch_value": batch_value,
                        "batch_origin": batch_origin,
                        "match_rule": match_rule,
                        "match_confidence": match_confidence,
                        "image_id": image_record.get("image_id"),
                        "image_category": image_record.get("image_category"),
                        "image_source_root_type": image_record.get("source_root_type"),
                        "image_model_candidate": image_record.get("model_candidate"),
                        "image_model_display_name": image_record.get("model_display_name"),
                        "image_batch_candidate": image_record.get("batch_candidate"),
                        "image_lead_group": image_record.get("top_level_dir"),
                        "image_relative_path": image_record.get("relative_path"),
                        "image_absolute_path": image_record.get("absolute_path"),
                        "record_source": row_source,
                    }
                )

    return pd.DataFrame(link_records)


def build_image_gap_report(merged_df: pd.DataFrame, image_link_df: pd.DataFrame) -> pd.DataFrame:
    if merged_df.empty:
        return pd.DataFrame()

    matched_keys = set()
    if not image_link_df.empty:
        for _, row in image_link_df.iterrows():
            matched_keys.add((normalize_token(row.get("产品批号")), normalize_token(row.get("生产批号"))))

    gap_records: List[Dict[str, object]] = []
    for _, row in merged_df.iterrows():
        row_key = (normalize_token(row.get("产品批号")), normalize_token(row.get("生产批号")))
        if row_key in matched_keys:
            continue
        gap_records.append(
            {
                "产品批号": row.get("产品批号"),
                "生产批号": row.get("生产批号"),
                "锡膏型号": row.get("锡膏型号"),
                "助焊膏": row.get("助焊膏"),
                "overall数据源": row.get("overall数据源"),
                "specific数据源": row.get("specific数据源"),
                "issue_type": "missing_image_match",
                "message": "当前批次未匹配到任何图片，建议核对 image 与外部图片盘是否缺图或命名不一致。",
            }
        )

    return pd.DataFrame(gap_records)
