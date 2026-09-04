from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

import pandas as pd

KNOWN_ELEMENTS = ["Sn", "Pb", "Ag", "Cu", "Bi", "Sb", "As", "Fe", "Zn", "Al", "Cd", "Ni", "Ti"]
MERGE_KEY_SPLIT_PATTERN = re.compile(r"[/,，、;；]+")


def split_batch_keys(key_str: object) -> List[str]:
    if pd.isna(key_str):
        return []
    return [part.strip() for part in MERGE_KEY_SPLIT_PATTERN.split(str(key_str)) if part.strip()]


def particle_label_sort_key(column_name: str) -> Tuple[object, ...]:
    label = column_name.split("_", 2)[-1]

    less_match = re.match(r"<(\d+)µm", label)
    if less_match:
        return (0, int(less_match.group(1)), int(less_match.group(1)))

    range_match = re.match(r"(\d+)～(\d+)µm", label)
    if range_match:
        return (1, int(range_match.group(1)), int(range_match.group(2)))

    greater_match = re.match(r">(\d+)µm", label)
    if greater_match:
        return (2, int(greater_match.group(1)), int(greater_match.group(1)))

    return (3, label)


def deduplicate_specific_data(specific_df: pd.DataFrame) -> pd.DataFrame:
    if specific_df.empty:
        return specific_df.copy()

    if "生产批号" not in specific_df.columns:
        return specific_df.copy()

    df = specific_df.copy()
    df["生产批号"] = df["生产批号"].astype(str).str.strip()
    df = df[df["生产批号"].ne("") & df["生产批号"].ne("nan")]
    return df.drop_duplicates(subset=["生产批号"], keep="first")


def _matched_presence_mask(df: pd.DataFrame) -> pd.Series:
    if "来源文件_specific" in df.columns:
        return df["来源文件_specific"].notna() & df["来源文件_specific"].astype(str).str.strip().ne("")
    if "生产批号" in df.columns:
        return df["生产批号"].notna() & df["生产批号"].astype(str).str.strip().ne("")
    return pd.Series(False, index=df.index)


def build_merged_dataset(overall_df: pd.DataFrame, specific_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overall = overall_df.copy()
    specific_unique = deduplicate_specific_data(specific_df)

    if overall.empty or specific_unique.empty:
        merged = overall.copy()
        filtered = merged.copy()
        return merged, filtered, specific_unique

    overall["merge_key"] = overall["merge_key"].astype(str).str.strip()
    specific_unique["生产批号"] = specific_unique["生产批号"].astype(str).str.strip()
    specific_lookup = specific_unique.set_index("生产批号").to_dict("index")

    def lookup_data(key_str: object) -> Dict[str, object]:
        if not isinstance(key_str, str):
            return {}
        for key in split_batch_keys(key_str):
            if key in specific_lookup:
                return {"生产批号": key, **specific_lookup[key]}
        return {}

    # 性能优化：预计算每个 distinct merge_key 的匹配结果，避免对每一行重复做正则拆分 + 复制大字典。
    # 行数越多收益越大（run 38 约 1.5 万行时原逻辑会显著变慢）。
    distinct_keys = overall["merge_key"].dropna().unique().tolist()
    lookup_cache = {k: lookup_data(k) for k in distinct_keys}

    def get_match(key_str: object) -> Dict[str, object]:
        if pd.isna(key_str):
            return {}
        return lookup_cache.get(str(key_str), {})

    matched_series = overall["merge_key"].apply(get_match)
    matched_df = pd.DataFrame(matched_series.tolist(), index=overall.index)
    merged = pd.concat([overall, matched_df], axis=1)

    if "来源文件" in merged.columns and "来源Sheet" in merged.columns:
        merged["overall数据源"] = merged["来源文件"].fillna("") + " - " + merged["来源Sheet"].fillna("")
        merged["overall数据源"] = merged["overall数据源"].str.strip(" -")

    if "来源文件_specific" in merged.columns and "来源Sheet_specific" in merged.columns:
        merged["specific数据源"] = merged["来源文件_specific"].fillna("") + " - " + merged["来源Sheet_specific"].fillna("")
        merged["specific数据源"] = merged["specific数据源"].str.strip(" -")

    particle_standard_columns = sorted(
        [col for col in merged.columns if col.startswith("粒度分布_标准值_")],
        key=particle_label_sort_key,
    )
    particle_measured_columns = sorted(
        [col for col in merged.columns if col.startswith("粒度分布_实测值_")],
        key=particle_label_sort_key,
    )

    base_columns = [
        "序号",
        "产品批号",
        "生产批号",
        "锡膏型号",
        "助焊膏",
        "助焊剂比例%",
        "合金含量（%）",
        "合金牌号",
        "锡粉批号",
        "merge_key",
    ]
    element_columns = [col for col in KNOWN_ELEMENTS if col in merged.columns]
    metric_columns = [
        col
        for col in ["氧含量_标准值", "氧含量_实测值", "球型度_标准值", "球型度_实测值"]
        if col in merged.columns
    ]
    source_columns = [col for col in ["overall数据源", "specific数据源"] if col in merged.columns]
    ordered_columns = [
        col
        for col in base_columns + element_columns + particle_standard_columns + particle_measured_columns + metric_columns + source_columns
        if col in merged.columns
    ]
    other_columns = [col for col in merged.columns if col not in ordered_columns]
    merged = merged[ordered_columns + other_columns]

    matched_mask = _matched_presence_mask(merged)
    filtered = merged[matched_mask].copy()

    if "序号" in merged.columns:
        merged["序号"] = range(1, len(merged) + 1)
    if "序号" in filtered.columns:
        filtered["序号"] = range(1, len(filtered) + 1)

    return merged, filtered, specific_unique


def build_specific_batch_master(specific_df: pd.DataFrame) -> pd.DataFrame:
    if specific_df.empty:
        return pd.DataFrame()

    preferred_cols = [
        "生产批号",
        "来源文件_specific",
        "来源Sheet_specific",
        "Sn",
        "Pb",
        "Ag",
        "Cu",
        "Bi",
        "Sb",
        "氧含量_标准值",
        "氧含量_实测值",
        "球型度_标准值",
        "球型度_实测值",
    ]
    available_cols = [col for col in preferred_cols if col in specific_df.columns]
    batch_master = specific_df[available_cols].copy()
    batch_master.insert(0, "specific_batch_id", range(1, len(batch_master) + 1))
    return batch_master


def build_chemical_composition_long(specific_df: pd.DataFrame) -> pd.DataFrame:
    if specific_df.empty or "生产批号" not in specific_df.columns:
        return pd.DataFrame()

    available_elements = [element for element in KNOWN_ELEMENTS if element in specific_df.columns]
    records: List[Dict[str, object]] = []
    for _, row in specific_df.iterrows():
        batch_no = row.get("生产批号")
        if pd.isna(batch_no):
            continue
        for element in available_elements:
            value = row.get(element)
            if pd.isna(value):
                continue
            records.append(
                {
                    "生产批号": str(batch_no).strip(),
                    "元素": element,
                    "实测值": value,
                    "来源文件_specific": row.get("来源文件_specific"),
                    "来源Sheet_specific": row.get("来源Sheet_specific"),
                }
            )

    return pd.DataFrame(records)


def _iterate_particle_labels(columns: Iterable[str]) -> List[str]:
    labels = set()
    for column in columns:
        if column.startswith("粒度分布_标准值_"):
            labels.add(column.replace("粒度分布_标准值_", "", 1))
        elif column.startswith("粒度分布_实测值_"):
            labels.add(column.replace("粒度分布_实测值_", "", 1))
    return sorted(labels, key=lambda item: particle_label_sort_key(f"粒度分布_标准值_{item}"))


def build_particle_distribution_long(specific_df: pd.DataFrame) -> pd.DataFrame:
    if specific_df.empty or "生产批号" not in specific_df.columns:
        return pd.DataFrame()

    labels = _iterate_particle_labels(specific_df.columns)
    records: List[Dict[str, object]] = []
    for _, row in specific_df.iterrows():
        batch_no = row.get("生产批号")
        if pd.isna(batch_no):
            continue
        for order_index, label in enumerate(labels, start=1):
            standard_col = f"粒度分布_标准值_{label}"
            measured_col = f"粒度分布_实测值_{label}"
            standard_value = row.get(standard_col)
            measured_value = row.get(measured_col)
            if pd.isna(standard_value) and pd.isna(measured_value):
                continue
            records.append(
                {
                    "生产批号": str(batch_no).strip(),
                    "粒度区间": label,
                    "顺序": order_index,
                    "标准值": standard_value,
                    "实测值": measured_value,
                    "来源文件_specific": row.get("来源文件_specific"),
                    "来源Sheet_specific": row.get("来源Sheet_specific"),
                }
            )

    return pd.DataFrame(records)


def build_quality_metric_long(specific_df: pd.DataFrame) -> pd.DataFrame:
    if specific_df.empty or "生产批号" not in specific_df.columns:
        return pd.DataFrame()

    metric_groups = [
        ("氧含量", "氧含量_标准值", "氧含量_实测值"),
        ("球型度", "球型度_标准值", "球型度_实测值"),
    ]
    records: List[Dict[str, object]] = []
    for _, row in specific_df.iterrows():
        batch_no = row.get("生产批号")
        if pd.isna(batch_no):
            continue
        for metric_name, standard_col, measured_col in metric_groups:
            if standard_col not in specific_df.columns and measured_col not in specific_df.columns:
                continue
            standard_value = row.get(standard_col)
            measured_value = row.get(measured_col)
            if pd.isna(standard_value) and pd.isna(measured_value):
                continue
            records.append(
                {
                    "生产批号": str(batch_no).strip(),
                    "指标名": metric_name,
                    "标准值": standard_value,
                    "实测值": measured_value,
                    "来源文件_specific": row.get("来源文件_specific"),
                    "来源Sheet_specific": row.get("来源Sheet_specific"),
                }
            )

    return pd.DataFrame(records)
