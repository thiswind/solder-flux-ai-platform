from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _issue(
    issue_type: str,
    severity: str,
    entity_type: str,
    entity_key: object,
    message: str,
    source_file: object = None,
    source_sheet: object = None,
) -> Dict[str, object]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "entity_type": entity_type,
        "entity_key": entity_key,
        "message": message,
        "source_file": source_file,
        "source_sheet": source_sheet,
    }


def build_validation_issues(
    overall_df: pd.DataFrame,
    specific_raw_df: pd.DataFrame,
    specific_unique_df: pd.DataFrame,
    merged_df: pd.DataFrame,
) -> pd.DataFrame:
    issues: List[Dict[str, object]] = []

    if not overall_df.empty and "merge_key" in overall_df.columns:
        missing_merge_key = overall_df[
            overall_df["merge_key"].isna() | overall_df["merge_key"].astype(str).str.strip().isin(["", "nan"])
        ]
        for _, row in missing_merge_key.iterrows():
            issues.append(
                _issue(
                    "overall_missing_merge_key",
                    "high",
                    "overall_record",
                    row.get("产品批号"),
                    "锡膏检测数据缺少用于关联锡膏配方数据的锡粉批号。",
                    row.get("来源文件"),
                    row.get("来源Sheet"),
                )
            )

    if not overall_df.empty and "产品批号" in overall_df.columns:
        valid_mask = overall_df["产品批号"].notna() & ~overall_df["产品批号"].astype(str).str.strip().isin(["", "nan"])
        overall_dups = overall_df[valid_mask & overall_df["产品批号"].duplicated(keep=False)]
        for _, row in overall_dups.iterrows():
            issues.append(
                _issue(
                    "overall_duplicate_batch",
                    "medium",
                    "overall_record",
                    row.get("产品批号"),
                    "锡膏检测数据存在重复产品批号，平台默认保留首条记录。",
                    row.get("来源文件"),
                    row.get("来源Sheet"),
                )
            )

    if not specific_raw_df.empty and "生产批号" in specific_raw_df.columns:
        duplicates = specific_raw_df[specific_raw_df["生产批号"].duplicated(keep=False)].copy()
        for _, row in duplicates.iterrows():
            issues.append(
                _issue(
                    "specific_duplicate_batch",
                    "medium",
                    "specific_record",
                    row.get("生产批号"),
                    "锡膏配方数据存在重复生产批号，平台默认保留首条记录。",
                    row.get("来源文件_specific"),
                    row.get("来源Sheet_specific"),
                )
            )

    if not merged_df.empty:
        if "specific数据源" in merged_df.columns:
            unmatched = merged_df[
                merged_df["specific数据源"].isna() | merged_df["specific数据源"].astype(str).str.strip().eq("")
            ]
            for _, row in unmatched.iterrows():
                issues.append(
                    _issue(
                        "overall_unmatched_specific",
                        "medium",
                        "overall_record",
                        row.get("产品批号"),
                        "锡膏检测数据未匹配到任何锡膏配方数据。",
                        row.get("来源文件"),
                        row.get("来源Sheet"),
                    )
                )

        if "specific数据源" in merged_df.columns and "Sn" in merged_df.columns:
            matched_with_missing_core = merged_df[
                merged_df["specific数据源"].astype(str).str.strip().ne("")
                & merged_df["Sn"].isna()
            ]
            for _, row in matched_with_missing_core.iterrows():
                issues.append(
                    _issue(
                        "matched_but_missing_core_metric",
                        "high",
                        "merged_record",
                        row.get("产品批号") or row.get("生产批号"),
                        "已经匹配到锡膏配方数据，但核心字段 Sn 为空，建议人工复核模板。",
                        row.get("来源文件_specific"),
                        row.get("来源Sheet_specific"),
                    )
                )

    if not specific_unique_df.empty:
        important_cols = [col for col in ["Sn", "氧含量_实测值", "球型度_实测值"] if col in specific_unique_df.columns]
        for col in important_cols:
            missing_rows = specific_unique_df[specific_unique_df[col].isna()]
            for _, row in missing_rows.iterrows():
                issues.append(
                    _issue(
                        "specific_missing_important_field",
                        "medium",
                        "specific_record",
                        row.get("生产批号"),
                        f"锡膏配方数据缺少关键字段：{col}",
                        row.get("来源文件_specific"),
                        row.get("来源Sheet_specific"),
                    )
                )

    review_df = pd.DataFrame(issues)
    if review_df.empty:
        return pd.DataFrame(columns=["issue_type", "severity", "entity_type", "entity_key", "message", "source_file", "source_sheet"])
    return review_df
