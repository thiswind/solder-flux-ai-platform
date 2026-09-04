from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd


FIXED_PARTICLE_LABELS = ["<20µm", "20～38µm", "38～40µm", ">40µm"]
DELIVERY_BASE_COLUMNS = [
    "序号",
    "产品批号",
    "锡膏型号",
    "助焊膏",
    "助焊剂比例%",
    "合金含量（%）",
    "合金牌号",
    "锡粉批号",
    "Sn",
    "Pb",
    "As",
    "Ag",
    "Fe",
    "Cu",
    "Bi",
    "Sb",
    "Zn",
    "Al",
    "Cd",
    "Ni",
    "粒度分布_标准值_<20µm",
    "粒度分布_标准值_20～38µm",
    "粒度分布_标准值_38～40µm",
    "粒度分布_标准值_>40µm",
    "粒度分布_实测值_<20µm",
    "粒度分布_实测值_20～38µm",
    "粒度分布_实测值_38～40µm",
    "粒度分布_实测值_>40µm",
    "氧含量_标准值",
    "氧含量_实测值",
    "球型度_标准值",
    "球型度_实测值",
    "锡粉规格",
    "锡粉氧含量",
    "Wetting_Image_Path",
    "Wetting_Class",
    "黏度初值",
    "Ti",
    "黏度仪设备编号",
    "检验员",
    "overall数据源",
]
DELIVERY_EXTRA_COLUMNS = [
    "生产批号",
    "specific数据源",
    "SolderBall_Image_Path",
    "Collapse_Image_Path",
    "Stability_Image_Path",
    "图片匹配规则",
    "图片匹配置信度",
    "粒度分布_标准值_JSON",
    "粒度分布_实测值_JSON",
    # 自动视觉分级标签（由 vision_grading.grade_delivery_images 填充，对齐训练表 train_filled）
    "润湿等级",
    "润湿等级_来源",
    "润湿等级_置信度",
    "锡珠等级",
    "锡珠等级_来源",
    "锡珠等级_置信度",
    "坍塌类别",
    "坍塌类别_来源",
    "坍塌类别_置信度",
]
DELIVERY_REQUIRED_IMAGE_COLUMNS = [
    "Wetting_Image_Path",
    "SolderBall_Image_Path",
    "Collapse_Image_Path",
    "Stability_Image_Path",
]
DELIVERY_DETAIL_SHEET_COLUMNS = [
    "序号",
    "产品批号",
    "锡膏型号",
    "助焊膏",
    "助焊剂比例%",
    "合金含量（%）",
    "合金牌号",
    "锡粉批号",
    "Sn",
    "Pb",
    "As",
    "Ag",
    "Fe",
    "Cu",
    "Bi",
    "Sb",
    "Zn",
    "Al",
    "Cd",
    "Ni",
    "氧含量_标准值",
    "氧含量_实测值",
    "球型度_标准值",
    "球型度_实测值",
    "锡粉规格",
    "锡粉氧含量",
    "黏度初值",
    "Ti",
    "overall数据源",
    "specific数据源",
    "Wetting_Image_Path",
    "SolderBall_Image_Path",
    "Collapse_Image_Path",
    "Stability_Image_Path",
    "粒度分布_标准值_JSON",
    "粒度分布_实测值_JSON",
]
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", _normalize_text(value).upper())


def _normalize_particle_label(label: str) -> str:
    return (
        _normalize_text(label)
        .replace(" ", "")
        .replace("μ", "µ")
        .replace("um", "µm")
        .replace("~", "～")
        .replace("-", "～")
    )


def _to_json_ready(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _json_dumps(mapping: dict[str, Any]) -> str:
    clean_mapping = {key: _to_json_ready(value) for key, value in mapping.items() if _to_json_ready(value) is not None}
    if not clean_mapping:
        return ""
    return json.dumps(clean_mapping, ensure_ascii=False, sort_keys=True)


def _build_particle_map(row: pd.Series, prefix: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column, value in row.items():
        if not isinstance(column, str) or not column.startswith(prefix):
            continue
        if value is None or pd.isna(value):
            continue
        label = column.replace(prefix, "", 1)
        values[label] = value
    return values


def _get_particle_value(values: dict[str, Any], target_label: str) -> Any:
    normalized_target = _normalize_particle_label(target_label)
    for label, value in values.items():
        if _normalize_particle_label(label) == normalized_target:
            return value
    return None


def _row_match_key(row: pd.Series) -> tuple[str, str]:
    return (_normalize_key(row.get("产品批号")), _normalize_key(row.get("生产批号")))


def _build_image_lookup(image_link_df: pd.DataFrame) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    if image_link_df.empty:
        return {}

    sorted_links = image_link_df.copy()
    sorted_links["_confidence_rank"] = sorted_links["match_confidence"].map(CONFIDENCE_RANK).fillna(99)
    sorted_links = sorted_links.sort_values(
        by=["_confidence_rank", "image_category", "image_absolute_path"],
        ascending=[True, True, True],
        na_position="last",
    )

    lookup: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for _, row in sorted_links.iterrows():
        key = (_normalize_key(row.get("产品批号")), _normalize_key(row.get("生产批号")))
        if not any(key):
            continue
        category = _normalize_text(row.get("image_category"))
        if not category:
            continue
        bucket = lookup.setdefault(key, {})
        bucket.setdefault(category, row.to_dict())
    return lookup


def build_delivery_dataset(base_df: pd.DataFrame, image_link_df: pd.DataFrame) -> pd.DataFrame:
    if base_df.empty:
        return pd.DataFrame(columns=DELIVERY_BASE_COLUMNS + DELIVERY_EXTRA_COLUMNS)

    image_lookup = _build_image_lookup(image_link_df)
    records: list[dict[str, Any]] = []

    for row_index, (_, row) in enumerate(base_df.iterrows(), start=1):
        standard_particle_map = _build_particle_map(row, "粒度分布_标准值_")
        measured_particle_map = _build_particle_map(row, "粒度分布_实测值_")
        matched_images = image_lookup.get(_row_match_key(row), {})
        wetting_image = matched_images.get("Wetting", {})
        solder_ball_image = matched_images.get("SolderBall", {})
        collapse_image = matched_images.get("Collapse", {})
        stability_image = matched_images.get("Stability", {})

        record: dict[str, Any] = {
            "序号": row_index,
            "产品批号": row.get("产品批号"),
            "锡膏型号": row.get("锡膏型号"),
            "助焊膏": row.get("助焊膏"),
            "助焊剂比例%": row.get("助焊剂比例%"),
            "合金含量（%）": row.get("合金含量（%）"),
            "合金牌号": row.get("合金牌号"),
            "锡粉批号": row.get("锡粉批号"),
            "Sn": row.get("Sn"),
            "Pb": row.get("Pb"),
            "As": row.get("As"),
            "Ag": row.get("Ag"),
            "Fe": row.get("Fe"),
            "Cu": row.get("Cu"),
            "Bi": row.get("Bi"),
            "Sb": row.get("Sb"),
            "Zn": row.get("Zn"),
            "Al": row.get("Al"),
            "Cd": row.get("Cd"),
            "Ni": row.get("Ni"),
            "氧含量_标准值": row.get("氧含量_标准值"),
            "氧含量_实测值": row.get("氧含量_实测值"),
            "球型度_标准值": row.get("球型度_标准值"),
            "球型度_实测值": row.get("球型度_实测值"),
            "锡粉规格": row.get("锡粉规格"),
            "锡粉氧含量": row.get("锡粉氧含量"),
            "Wetting_Image_Path": wetting_image.get("image_relative_path") or wetting_image.get("image_absolute_path"),
            "Wetting_Class": wetting_image.get("image_category"),
            "黏度初值": row.get("黏度初值"),
            "Ti": row.get("Ti"),
            "黏度仪设备编号": row.get("黏度仪设备编号"),
            "检验员": row.get("检验员"),
            "overall数据源": row.get("overall数据源"),
            "生产批号": row.get("生产批号"),
            "specific数据源": row.get("specific数据源"),
            "SolderBall_Image_Path": solder_ball_image.get("image_relative_path") or solder_ball_image.get("image_absolute_path"),
            "Collapse_Image_Path": collapse_image.get("image_relative_path") or collapse_image.get("image_absolute_path"),
            "Stability_Image_Path": stability_image.get("image_relative_path") or stability_image.get("image_absolute_path"),
            "图片匹配规则": wetting_image.get("match_rule"),
            "图片匹配置信度": wetting_image.get("match_confidence"),
            "粒度分布_标准值_JSON": _json_dumps(standard_particle_map),
            "粒度分布_实测值_JSON": _json_dumps(measured_particle_map),
        }

        for label in FIXED_PARTICLE_LABELS:
            record[f"粒度分布_标准值_{label}"] = _get_particle_value(standard_particle_map, label)
            record[f"粒度分布_实测值_{label}"] = _get_particle_value(measured_particle_map, label)

        records.append(record)

    delivery_df = pd.DataFrame(records)
    # 确保导出列（含自动分级中文标签列）始终存在，缺失的填 None
    for col in DELIVERY_BASE_COLUMNS + DELIVERY_EXTRA_COLUMNS:
        if col not in delivery_df.columns:
            delivery_df[col] = None
    ordered_columns = [column for column in DELIVERY_BASE_COLUMNS + DELIVERY_EXTRA_COLUMNS if column in delivery_df.columns]
    remaining_columns = [column for column in delivery_df.columns if column not in ordered_columns]
    return delivery_df[ordered_columns + remaining_columns]


def build_delivery_detail_sheet(delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df.empty:
        return pd.DataFrame(columns=DELIVERY_DETAIL_SHEET_COLUMNS)

    detail_df = delivery_df.copy()
    for column in DELIVERY_DETAIL_SHEET_COLUMNS:
        if column not in detail_df.columns:
            detail_df[column] = None
    return detail_df[DELIVERY_DETAIL_SHEET_COLUMNS]


def build_delivery_filtered_sheet(delivery_df: pd.DataFrame) -> pd.DataFrame:
    if delivery_df.empty:
        return delivery_df.copy()

    filtered_df = delivery_df.copy()
    for column in DELIVERY_REQUIRED_IMAGE_COLUMNS:
        if column not in filtered_df.columns:
            filtered_df[column] = None

    complete_mask = pd.Series(True, index=filtered_df.index)
    for column in DELIVERY_REQUIRED_IMAGE_COLUMNS:
        complete_mask &= filtered_df[column].fillna("").astype(str).str.strip().ne("")

    return filtered_df.loc[complete_mask].reset_index(drop=True)
