import hashlib
import io
import json
import os
import re
import time
import sqlite3
from urllib.parse import quote
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import asc, desc, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.models.experiment import DataUpload, Experiment, SolderPasteData
from backend.app.services.ai_service import PARTICLE_JSON_COL, ai_engine
from shared.auth_client import require_login, require_admin

router = APIRouter()

COMMON_PARTICLE_KEYS = {
    "particle_size_real_lt_20": ["<20µm", "<20μm", "<20um"],
    "particle_size_real_20_38": ["20～38µm", "20～38μm", "20-38um"],
    "particle_size_real_38_40": ["38～40µm", "38～40μm", "38-40um"],
    "particle_size_real_gt_40": [">40µm", ">40μm", ">40um"],
}


class PredictionRequest(BaseModel):
    features: Dict[str, Any]
    log: bool = True


class PredictionResponse(BaseModel):
    predictions: Dict[str, Any]
    score: float
    execution_time_ms: float


class HistoryItem(BaseModel):
    id: int
    experiment_name: Optional[str]
    composition_x: Dict[str, Any]
    properties_y: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class UploadItem(BaseModel):
    id: int
    filename: str
    description: Optional[str]
    row_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class SolderDataStats(BaseModel):
    total_count: int
    viscosity_dist: List[float]
    ti_dist: List[float]
    models: List[str]
    viscosity_summary: Dict[str, float]
    ti_summary: Dict[str, float]


class ModelInfoResponse(BaseModel):
    name: str
    status: str
    last_trained: Optional[str]
    accuracy: Dict[str, float]
    metrics: Dict[str, Any] = {}
    training_rows: int = 0
    feature_count: int = 0
    particle_feature_count: int = 0
    particle_feature_labels: List[str] = []


class AlloyPreset(BaseModel):
    alloy_grade: str
    pb: float
    ag: float
    fe: float
    cu: float
    bi: float
    sb: float
    oxygen_real: float
    lead_type: str = "lead_free"


class DataUpdate(BaseModel):
    viscosity_initial: Optional[float] = None
    ti_index: Optional[float] = None
    powder_spec: Optional[str] = None
    wetting_level: Optional[str] = None
    solderball_level: Optional[str] = None
    collapse_category: Optional[str] = None


class HistoryResponse(BaseModel):
    items: List[HistoryItem]
    total: int


_alloy_presets_cache: Optional[List[AlloyPreset]] = None


def calculate_file_hash(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


def calculate_content_hash(df: "pd.DataFrame") -> str:
    """解析后数据的规范化哈希，用于内容层级去重（L2）。

    与 L1 文件字节哈希不同，此处基于实际数据内容：可识别
    '字节不同但数据一致'的重复上传（如重新保存、改格式、个别单元格微调）。
    对列名排序、NaN 归一为 None，保证相同内容得到稳定哈希。
    """
    cols = sorted(str(c) for c in df.columns)
    sub = df[cols]
    records = sub.where(sub.notna(), None).to_dict(orient="records")
    blob = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def calculate_row_hash(payload: dict) -> str:
    """单行数据的规范化哈希，用于行层级去重（与 L2 内容哈希共用归一化约定）。

    基于 row_to_record 生成的 raw_payload（已对 NaN 归一为 None），
    对列名排序后做 sha256，保证内容相同的行得到稳定哈希。
    """
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# 目录清单识别：一份"文件/文件夹目录树扫描结果"若被当锡膏检测数据导入，
# 其每行字段各异（路径唯一）会被 row_hash 永远判不重，长期注水污染数据集。
# 守卫在解析后立即拦截：含目录清单特征列且缺少任何锡膏检测必需列即拒绝。
_LISTING_MARKER_COLS = {"类型", "完整路径", "父级路径", "名称", "层级", "扩展名", "大小(B)", "总大小(B)", "总数量"}
_MEASURE_MARKER_COLS = {
    "产品批号", "锡膏型号", "助焊膏", "助焊剂比例%", "合金含量（%）", "合金牌号",
    "锡粉批号", "Sn", "Pb", "As", "Ag", "Fe", "Cu", "Bi", "Sb", "Zn", "Al", "Cd", "Ni",
    "氧含量_实测值", "球型度_实测值", "锡粉规格", "锡粉氧含量", "黏度初值", "Ti",
}


def looks_like_directory_listing(df: pd.DataFrame) -> tuple[bool, str]:
    """判断解析后的 DataFrame 是否像「文件目录清单」而非锡膏检测数据。

    返回 (is_listing, reason)。当存在目录清单特征列且完全不含任何锡膏检测必需列时判为清单。
    若两类列都有（混合），不拦截，交由后续逻辑处理。
    """
    cols = {str(c).strip() for c in df.columns}
    has_listing = bool(cols & _LISTING_MARKER_COLS)
    has_measure = bool(cols & _MEASURE_MARKER_COLS)
    if has_listing and not has_measure:
        return True, "含目录清单特征列(类型/完整路径/层级等)但缺少锡膏检测必需列(产品批号/成分/黏度等)"
    return False, ""


def clean_text(value: Any) -> Optional[str]:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def clean_float(value: Any) -> Optional[float]:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "/"}:
        return None
    text = text.replace("余量", "")
    match = re.search(r"[-+]?\d*\.\d+|[-+]?\d+", text)
    return float(match.group()) if match else None


def clean_confidence(value: Any) -> Optional[float]:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    if not text:
        return None
    try:
        num = float(text)
        return num / 100 if num > 1 else num
    except ValueError:
        return None


def json_safe_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def parse_json_cell(value: Any) -> Optional[Dict[str, Any]]:
    text = clean_text(value)
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def normalize_label(value: Any) -> Optional[str]:
    text = clean_text(value)
    if text is None:
        return None
    numeric = clean_float(text)
    if numeric is not None and abs(numeric - round(numeric)) < 1e-9:
        return str(int(round(numeric)))
    return text


def sanitize_powder_spec(value: Any) -> str:
    return str(value or "N/A").strip()


def detect_lead_type(alloy_grade: Any = None, pb_value: Any = None) -> str:
    grade_text = clean_text(alloy_grade) or ""
    pb_text = clean_text(pb_value) or ""
    grade_upper = grade_text.upper()
    pb_upper = pb_text.upper()
    # In the current dataset, leaded alloys often mark Pb as "余量"
    # and the grade name itself contains Pb/63A/37 patterns.
    if "余量" in pb_text:
        return "leaded"
    if "PB" in grade_upper or "铅" in grade_text:
        return "leaded"
    if re.search(r"(^63A$|63/?37|37/?63|SN\d+(?:\.\d+)?PB|PBBI)", grade_upper):
        return "leaded"
    pb_numeric = clean_float(pb_value)
    if pb_numeric is not None and pb_numeric > 1:
        return "leaded"
    return "lead_free"


def sanitize_prob_list(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = clean_text(item.get("label"))
        prob = clean_float(item.get("prob"))
        if label is None or prob is None:
            continue
        cleaned.append({"label": label, "prob": float(prob)})
    return cleaned


def score_from_predictions(predictions: Dict[str, Any]) -> float:
    keys = [
        "powder_spec_top_probs",
        "wetting_level_top_probs",
        "collapse_category_top_probs",
        "solderball_level_top_probs",
    ]
    probs = []
    for key in keys:
        top = predictions.get(key) or []
        if top:
            probs.append(float(top[0].get("prob", 0) or 0))
    return round((sum(probs) / len(probs)) * 10, 1) if probs else 0.0


def pick_excel_sheet(excel_file: pd.ExcelFile) -> str:
    preferred = ["train_filled", "train", "modified", "filtered", "raw"]
    for name in preferred:
        if name in excel_file.sheet_names:
            return name
    return excel_file.sheet_names[0]


def load_excel_from_bytes(contents: bytes) -> tuple[pd.DataFrame, str]:
    excel = pd.ExcelFile(io.BytesIO(contents))
    sheet_name = pick_excel_sheet(excel)
    return pd.read_excel(io.BytesIO(contents), sheet_name=sheet_name), sheet_name


def processed_data_paths() -> List[str]:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return [
        os.path.join(project_root, "processed_data.xlsx"),
        os.path.join(project_root, "backend", "data", "processed_data.xlsx"),
    ]


def load_reference_dataframe() -> Optional[pd.DataFrame]:
    for path in processed_data_paths():
        if os.path.exists(path):
            excel = pd.ExcelFile(path)
            return pd.read_excel(path, sheet_name=pick_excel_sheet(excel))
    return None


def build_particle_json_from_legacy_fields(features: Dict[str, Any]) -> str:
    payload = {
        "<20µm": float(features.get("particle_size_real_lt_20", 0) or 0),
        "20～38µm": float(features.get("particle_size_real_20_38", 0) or 0),
        "38～40µm": float(features.get("particle_size_real_38_40", 0) or 0),
        ">40µm": float(features.get("particle_size_real_gt_40", 0) or 0),
    }
    return json.dumps(payload, ensure_ascii=False)


def extract_common_particle_values(value: Any) -> Dict[str, float]:
    data = value if isinstance(value, dict) else parse_json_cell(value) or {}
    normalized = {k: 0.0 for k in COMMON_PARTICLE_KEYS}
    for target_key, aliases in COMMON_PARTICLE_KEYS.items():
        found = 0.0
        for alias in aliases:
            for raw_key, raw_value in data.items():
                if str(raw_key).replace("μ", "µ").replace("u", "µ") == alias.replace("μ", "µ").replace("u", "µ"):
                    found = float(clean_float(raw_value) or 0.0)
                    break
            if found:
                break
        normalized[target_key] = round(found, 6)
    return normalized


def particle_score(values: Dict[str, float]) -> float:
    weights = {
        "particle_size_real_lt_20": 10.0,
        "particle_size_real_20_38": 29.0,
        "particle_size_real_38_40": 39.0,
        "particle_size_real_gt_40": 50.0,
    }
    return sum(float(values.get(key, 0) or 0) * weight for key, weight in weights.items())


def build_particle_profiles(records: List[Dict[str, float]]) -> List[Dict[str, Any]]:
    cleaned = []
    for row in records:
        values = {key: float(row.get(key, 0) or 0) for key in COMMON_PARTICLE_KEYS}
        if not any(values.values()):
            continue
        cleaned.append({"values": values, "score": particle_score(values)})
    if not cleaned:
        return []
    cleaned = sorted(cleaned, key=lambda item: item["score"])
    indexes = sorted({0, len(cleaned) // 4, len(cleaned) // 2, (len(cleaned) * 3) // 4, len(cleaned) - 1})
    profiles = []
    seen = set()
    for idx in indexes:
        values = cleaned[idx]["values"]
        signature = tuple(round(values[key], 4) for key in COMMON_PARTICLE_KEYS)
        if signature in seen:
            continue
        seen.add(signature)
        profiles.append({
            "label": f"P{len(profiles) + 1}",
            "score": round(float(cleaned[idx]["score"]), 6),
            "values": values,
        })
    return profiles


def safe_float_series(values: List[Any]) -> pd.Series:
    return pd.to_numeric(pd.Series(values), errors="coerce").dropna()


def range_payload(values: List[Any]) -> Dict[str, float]:
    series = safe_float_series(values)
    if series.empty:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "q10": 0.0, "q50": 0.0, "q90": 0.0}
    return {
        "min": round(float(series.min()), 6),
        "max": round(float(series.max()), 6),
        "mean": round(float(series.mean()), 6),
        "q10": round(float(series.quantile(0.1)), 6),
        "q50": round(float(series.quantile(0.5)), 6),
        "q90": round(float(series.quantile(0.9)), 6),
    }


def summary_payload(values: List[Any]) -> Dict[str, float]:
    series = safe_float_series(values)
    if series.empty:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0}
    return {
        "min": round(float(series.min()), 6),
        "max": round(float(series.max()), 6),
        "mean": round(float(series.mean()), 6),
        "median": round(float(series.median()), 6),
        "std": round(float(series.std(ddof=0)), 6),
    }


def parse_particle_label(raw_label: Any) -> Optional[Dict[str, Any]]:
    text = clean_text(raw_label)
    if not text:
        return None
    normalized = text.replace("μ", "µ").replace("um", "µm").replace("～", "~").replace(" ", "")
    if normalized.startswith("<"):
        upper = clean_float(normalized)
        if upper is None:
            return None
        return {"label": text, "kind": "lt", "start": None, "end": float(upper)}
    if normalized.startswith(">"):
        lower = clean_float(normalized)
        if lower is None:
            return None
        return {"label": text, "kind": "gt", "start": float(lower), "end": None}
    match = re.match(r"([-+]?\d*\.?\d+)[~\-]([-+]?\d*\.?\d+)", normalized)
    if not match:
        return None
    start = float(match.group(1))
    end = float(match.group(2))
    return {"label": text, "kind": "range", "start": min(start, end), "end": max(start, end)}


def particle_sort_key(item: Dict[str, Any]) -> tuple[float, float]:
    if item["start"] is None:
        return (-1e9, float(item["end"] or 0))
    if item["end"] is None:
        return (float(item["start"] or 0), 1e9)
    return (float(item["start"] or 0), float(item["end"] or 0))


def build_particle_templates_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    templates: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        particle_json = row.get("particle_json")
        if not particle_json:
            continue
        parsed_json = particle_json if isinstance(particle_json, dict) else parse_json_cell(particle_json)
        if not isinstance(parsed_json, dict) or not parsed_json:
            continue
        segments = []
        for key in parsed_json.keys():
            parsed = parse_particle_label(key)
            if parsed:
                segments.append(parsed)
        if not segments:
            continue
        segments = sorted(segments, key=particle_sort_key)
        signature = "|".join(
            f"{seg['kind']}:{'' if seg['start'] is None else round(seg['start'], 6)}:{'' if seg['end'] is None else round(seg['end'], 6)}"
            for seg in segments
        )
        lead_type = detect_lead_type(row.get("alloy_grade"), row.get("pb"))
        key = f"{lead_type}|{signature}"
        if key not in templates:
            templates[key] = {
                "id": f"{lead_type}_{len(templates) + 1}",
                "lead_type": lead_type,
                "segments": segments,
                "count": 0,
            }
        templates[key]["count"] += 1
    ordered = sorted(
        templates.values(),
        key=lambda item: (0 if item["lead_type"] == "lead_free" else 1, -item["count"], item["id"]),
    )
    for lead_type in ("lead_free", "leaded"):
        bucket = [item for item in ordered if item["lead_type"] == lead_type]
        for index, item in enumerate(bucket, start=1):
            prefix = "无铅模板" if lead_type == "lead_free" else "有铅模板"
            label = prefix + str(index)
            segment_text = " / ".join(seg["label"] for seg in item["segments"])
            item["label"] = f"{label} ({segment_text})"
    return ordered


def build_particle_templates_from_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = []
    json_series = df.get(PARTICLE_JSON_COL, pd.Series(dtype=str))
    alloy_grade_series = df.get("合金牌号", pd.Series(dtype=str))
    pb_series = pd.to_numeric(df.get("Pb", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    raw_pb_series = df.get("Pb", pd.Series(dtype=object))
    for particle_json, pb, raw_pb, alloy_grade in zip(
        json_series.tolist(),
        pb_series.tolist(),
        raw_pb_series.tolist(),
        alloy_grade_series.tolist(),
    ):
        rows.append({"particle_json": particle_json, "pb": raw_pb if clean_text(raw_pb) is not None else pb, "alloy_grade": alloy_grade})
    return build_particle_templates_from_rows(rows)


def build_upload_template_workbook() -> io.BytesIO:
    reference = load_reference_dataframe()
    if reference is not None and not reference.empty:
        template_df = reference.head(0).copy()
    else:
        template_df = pd.DataFrame(columns=[
            "序号", "产品批号", "锡膏型号", "助焊膏", "助焊剂比例%", "合金含量（%）", "合金牌号",
            "锡粉批号", "Sn", "Pb", "As", "Ag", "Fe", "Cu", "Bi", "Sb", "Zn", "Al", "Cd", "Ni",
            "氧含量_标准值", "氧含量_实测值", "球型度_标准值", "球型度_实测值", "锡粉规格", "Wetting_Image_Path",
            "黏度初值", "Ti", "overall数据源", "生产批号", "specific数据源", "SolderBall_Image_Path",
            "Collapse_Image_Path", "Stability_Image_Path", "粒度分布_标准值_JSON", "粒度分布_实测值_JSON",
            "Original_Wetting_Image_Path", "Wetting_more_details", "Original_SolderBall_Image_Path",
            "SolderBall_more_details", "Original_Collapse_Image_Path", "Collapse_more_details",
            "Original_Stability_Image_Path", "Stability_more_details", "润湿等级", "润湿等级_来源",
            "润湿等级_置信度", "锡珠等级", "锡珠等级_来源", "锡珠等级_置信度", "坍塌类别", "坍塌类别_来源", "坍塌类别_置信度",
        ])
    guide_df = pd.DataFrame([
        {"说明项": "Sheet 名称", "要求": "优先使用 train_filled；也兼容 train / modified / filtered / raw。"},
        {"说明项": "列结构", "要求": "请严格使用模板列名，保持大小写与中英文一致，不建议手动改列名。"},
        {"说明项": "粒度分布 JSON", "要求": "请保持合法 JSON 结构，例如 {\"<20µm\": 10, \"20～38µm\": 70, \">40µm\": 20}。"},
        {"说明项": "图片路径", "要求": "Wetting/SolderBall/Collapse 图片路径建议填写绝对路径。"},
        {"说明项": "分类标签", "要求": "润湿等级、锡珠等级、坍塌类别建议直接填写模型输出标签。"},
    ])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        template_df.to_excel(writer, sheet_name="train_filled", index=False)
        guide_df.to_excel(writer, sheet_name="模板说明", index=False)
    buffer.seek(0)
    return buffer


def row_to_record(row: pd.Series, upload_id: int) -> SolderPasteData:
    payload = {col: json_safe_value(row.get(col)) for col in row.index}
    return SolderPasteData(
        upload_id=upload_id,
        serial_number=int(clean_float(row.get("序号")) or 0) if clean_float(row.get("序号")) is not None else None,
        product_batch=clean_text(row.get("产品批号")),
        product_model=clean_text(row.get("锡膏型号")),
        flux_paste=clean_text(row.get("助焊膏")),
        flux_percent=clean_float(row.get("助焊剂比例%")),
        alloy_content=clean_float(row.get("合金含量（%）")),
        alloy_grade=clean_text(row.get("合金牌号")),
        powder_batch=clean_text(row.get("锡粉批号")),
        sn=clean_text(row.get("Sn")),
        pb=clean_float(row.get("Pb")),
        as_=clean_float(row.get("As")),
        ag=clean_float(row.get("Ag")),
        fe=clean_float(row.get("Fe")),
        cu=clean_float(row.get("Cu")),
        bi=clean_float(row.get("Bi")),
        sb=clean_float(row.get("Sb")),
        zn=clean_float(row.get("Zn")),
        al=clean_float(row.get("Al")),
        cd=clean_float(row.get("Cd")),
        ni=clean_float(row.get("Ni")),
        oxygen_std=clean_text(row.get("氧含量_标准值")),
        oxygen_real=clean_float(row.get("氧含量_实测值")),
        sphericity_std=clean_text(row.get("球型度_标准值")),
        sphericity_real=clean_text(row.get("球型度_实测值")),
        powder_spec=clean_text(row.get("锡粉规格")),
        powder_oxygen=clean_text(row.get("锡粉氧含量")),
        viscosity_initial=clean_float(row.get("黏度初值")),
        ti_index=clean_float(row.get("Ti")),
        viscosity_device_id=clean_text(row.get("黏度仪设备编号")),
        inspector=clean_text(row.get("检验员")),
        wetting_image_path=clean_text(row.get("Wetting_Image_Path")),
        solderball_image_path=clean_text(row.get("SolderBall_Image_Path")),
        collapse_image_path=clean_text(row.get("Collapse_Image_Path")),
        stability_image_path=clean_text(row.get("Stability_Image_Path")),
        particle_distribution_std_json=parse_json_cell(row.get("粒度分布_标准值_JSON")),
        particle_distribution_real_json=parse_json_cell(row.get(PARTICLE_JSON_COL)),
        original_wetting_image_path=clean_text(row.get("Original_Wetting_Image_Path")),
        wetting_more_details=clean_text(row.get("Wetting_more_details")),
        original_solderball_image_path=clean_text(row.get("Original_SolderBall_Image_Path")),
        solderball_more_details=clean_text(row.get("SolderBall_more_details")),
        original_collapse_image_path=clean_text(row.get("Original_Collapse_Image_Path")),
        collapse_more_details=clean_text(row.get("Collapse_more_details")),
        original_stability_image_path=clean_text(row.get("Original_Stability_Image_Path")),
        stability_more_details=clean_text(row.get("Stability_more_details")),
        wetting_level=normalize_label(row.get("润湿等级")),
        wetting_level_source=clean_text(row.get("润湿等级_来源")),
        wetting_level_confidence=clean_confidence(row.get("润湿等级_置信度")),
        solderball_level=normalize_label(row.get("锡珠等级")),
        solderball_level_source=clean_text(row.get("锡珠等级_来源")),
        solderball_level_confidence=clean_confidence(row.get("锡珠等级_置信度")),
        collapse_category=clean_text(row.get("坍塌类别")),
        collapse_category_source=clean_text(row.get("坍塌类别_来源")),
        collapse_category_confidence=clean_confidence(row.get("坍塌类别_置信度")),
        overall_source=clean_text(row.get("overall数据源")),
        production_batch=clean_text(row.get("生产批号")),
        specific_source=clean_text(row.get("specific数据源")),
        raw_payload=payload,
    )


def training_dataframe_from_db(rows: List[SolderPasteData]) -> pd.DataFrame:
    records = [row.raw_payload for row in rows if isinstance(row.raw_payload, dict)]
    return pd.DataFrame(records)


@router.post("/data/upload", dependencies=[Depends(require_admin)])
def upload_data(file: UploadFile = File(...), custom_filename: Optional[str] = Form(None), db: Session = Depends(get_db)):
    try:
        contents = file.file.read()
        file_hash = calculate_file_hash(contents)

        # L1 文件层级去重：字节完全一致的文件直接拦截（使用正规字段精确匹配）
        existing_file = db.query(DataUpload).filter(DataUpload.file_hash == file_hash).first()
        if existing_file:
            return {
                "message": f"文件内容完全相同，已存在上传记录 (ID: {existing_file.id})，无需重复导入。",
                "duplicate": True,
            }

        try:
            df, sheet_name = load_excel_from_bytes(contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"读取 Excel 失败: {exc}")

        # 守卫：拒绝把"文件目录清单"等非检测数据导入预测表
        is_listing, reason = looks_like_directory_listing(df)
        if is_listing:
            return {
                "message": f"上传被拒绝：{reason}。请上传锡膏检测数据 Excel（含产品批号/成分/黏度等列）。",
                "duplicate": False,
                "rejected": True,
            }

        # L2 内容层级去重：字节不同但解析后数据一致（重存/改格式/个别单元格微调）也拦截
        content_hash = calculate_content_hash(df)
        existing_content = db.query(DataUpload).filter(DataUpload.content_hash == content_hash).first()
        if existing_content:
            return {
                "message": f"数据内容已存在（与上传记录 ID: {existing_content.id} 内容一致），无需重复导入。",
                "duplicate": True,
            }

        filename = custom_filename or file.filename or "processed_data.xlsx"
        new_upload = DataUpload(
            filename=filename,
            description=f"Uploaded via Web | Sheet:{sheet_name} | Hash:{file_hash}",
            row_count=0,
            file_hash=file_hash,
            content_hash=content_hash,
        )
        db.add(new_upload)
        db.flush()

        # L3 行层级去重：与库内已有行及本次上传内部重复行做合并，相同行只保留一份。
        # 库内已存在行指纹（用于跨上传去重，对齐数据平台 drop_duplicates 行为）
        existing_row_hashes = {
            h for (h,) in db.query(SolderPasteData.row_hash)
            .filter(SolderPasteData.row_hash.isnot(None))
            .all()
        }
        seen_in_batch: set = set()
        records = []
        skipped_rows = 0
        for _, row in df.iterrows():
            payload = {col: json_safe_value(row.get(col)) for col in row.index}
            row_hash = calculate_row_hash(payload)
            if row_hash in seen_in_batch or row_hash in existing_row_hashes:
                skipped_rows += 1
                continue
            seen_in_batch.add(row_hash)
            rec = row_to_record(row, new_upload.id)
            rec.row_hash = row_hash
            records.append(rec)

        db.bulk_save_objects(records)
        new_upload.row_count = len(records)
        db.add(
            Experiment(
                experiment_name=datetime.now().strftime("%Y%m%d-%H%M%S") + "-Upload",
                composition_x={"filename": filename, "sheet_name": sheet_name, "file_hash": file_hash, "file_size": len(contents)},
                properties_y={"row_count": len(records), "upload_id": new_upload.id, "skipped_rows": skipped_rows, "status": "Success"},
            )
        )
        db.commit()
        if skipped_rows:
            return {"message": f"成功导入 {len(records)} 条记录，跳过重复行 {skipped_rows} 条（sheet: {sheet_name}）", "duplicate": False}
        return {"message": f"成功导入 {len(records)} 条记录（sheet: {sheet_name}）", "duplicate": False}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/data/template", dependencies=[Depends(require_admin)])
def download_upload_template():
    buffer = build_upload_template_workbook()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="solder_upload_template.xlsx"'},
    )


@router.post("/data/init")
def init_data():
    return {"message": "Please use /api/v1/data/upload to upload files."}


@router.get("/uploads", response_model=List[UploadItem])
def get_uploads(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(DataUpload).order_by(desc(DataUpload.created_at)).offset(skip).limit(limit).all()


@router.get("/uploads/{upload_id}/data")
def get_upload_data(upload_id: int, db: Session = Depends(get_db)):
    return db.query(SolderPasteData).filter(SolderPasteData.upload_id == upload_id).order_by(SolderPasteData.id).all()


@router.delete("/uploads/{id}", dependencies=[Depends(require_admin)])
def delete_upload(id: int, db: Session = Depends(get_db)):
    upload = db.query(DataUpload).filter(DataUpload.id == id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    db.query(SolderPasteData).filter(SolderPasteData.upload_id == id).delete()
    db.query(Experiment).filter(Experiment.properties_y["upload_id"].astext == str(id)).delete()
    db.delete(upload)
    db.commit()
    return {"message": "Upload deleted successfully"}


@router.delete("/data/clear-all", dependencies=[Depends(require_admin)])
def clear_all_data(db: Session = Depends(get_db)):
    """清空用户上传的数据（检测记录 + 上传记录），不影响操作记录(Experiment)。"""
    n_data = db.query(SolderPasteData).count()
    n_up = db.query(DataUpload).count()
    db.query(SolderPasteData).delete()
    db.query(DataUpload).delete()
    db.commit()
    return {
        "message": f"已清空上传数据：删除 {n_data} 条检测记录、{n_up} 条上传记录",
        "deleted_rows": n_data,
        "deleted_uploads": n_up,
    }


@router.put("/data/{id}", dependencies=[Depends(require_admin)])
def update_data_item(id: int, item: DataUpdate, db: Session = Depends(get_db)):
    db_item = db.query(SolderPasteData).filter(SolderPasteData.id == id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    update_data = item.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/data/stats", response_model=SolderDataStats)
def get_data_stats(db: Session = Depends(get_db)):
    total = db.query(SolderPasteData).count()
    viscosities = db.query(SolderPasteData.viscosity_initial).filter(SolderPasteData.viscosity_initial.isnot(None)).all()
    tis = db.query(SolderPasteData.ti_index).filter(SolderPasteData.ti_index.isnot(None)).all()
    models = db.query(SolderPasteData.product_model).distinct().all()
    return {
        "total_count": total,
        "viscosity_dist": [v[0] for v in viscosities][:1000],
        "ti_dist": [t[0] for t in tis][:1000],
        "models": [m[0] for m in models if m[0]],
        "viscosity_summary": summary_payload([v[0] for v in viscosities]),
        "ti_summary": summary_payload([t[0] for t in tis]),
    }


@router.get("/data/list")
def get_data_list(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(SolderPasteData).order_by(SolderPasteData.id).offset(skip).limit(limit).all()


@router.delete("/data/{id}", dependencies=[Depends(require_admin)])
def delete_data(id: int, db: Session = Depends(get_db)):
    item = db.query(SolderPasteData).filter(SolderPasteData.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"message": "Deleted successfully"}


@router.get("/model/info", response_model=ModelInfoResponse)
def get_model_info():
    return ai_engine.model_info


@router.get("/feature-ranges")
def get_feature_ranges(db: Session = Depends(get_db)):
    rows = db.query(SolderPasteData).all()
    if rows:
        particle_records = [extract_common_particle_values(row.particle_distribution_real_json) for row in rows]
        particle_templates = build_particle_templates_from_rows([
            {"particle_json": row.particle_distribution_real_json, "pb": row.pb, "alloy_grade": row.alloy_grade} for row in rows
        ])
        return {
            "source": "database",
            "count": len(rows),
            "features": {
                "flux_percent": range_payload([row.flux_percent for row in rows]),
                "alloy_content": range_payload([row.alloy_content for row in rows]),
                "oxygen_real": range_payload([row.oxygen_real for row in rows]),
                "particle_size_real_lt_20": range_payload([item["particle_size_real_lt_20"] for item in particle_records]),
                "particle_size_real_20_38": range_payload([item["particle_size_real_20_38"] for item in particle_records]),
                "particle_size_real_38_40": range_payload([item["particle_size_real_38_40"] for item in particle_records]),
                "particle_size_real_gt_40": range_payload([item["particle_size_real_gt_40"] for item in particle_records]),
            },
            "particle_profiles": build_particle_profiles(particle_records),
            "powder_specs": sorted({sanitize_powder_spec(row.powder_spec) for row in rows if row.powder_spec}),
            "wetting_classes": sorted({str(row.wetting_level) for row in rows if row.wetting_level}),
            "collapse_categories": sorted({str(row.collapse_category) for row in rows if row.collapse_category}),
            "solderball_levels": sorted({str(row.solderball_level) for row in rows if row.solderball_level}),
            "flux_pastes": sorted({str(row.flux_paste) for row in rows if row.flux_paste}),
            "particle_templates": particle_templates,
        }

    df = load_reference_dataframe()
    if df is None:
        return {"source": "empty", "count": 0, "features": {}, "particle_profiles": []}
    particle_records = [extract_common_particle_values(value) for value in df.get(PARTICLE_JSON_COL, pd.Series(dtype=str))]
    particle_templates = build_particle_templates_from_dataframe(df)
    return {
        "source": "processed_data",
        "count": int(len(df)),
        "features": {
            "flux_percent": range_payload(df.get("助焊剂比例%", pd.Series(dtype=float)).tolist()),
            "alloy_content": range_payload(df.get("合金含量（%）", pd.Series(dtype=float)).tolist()),
            "oxygen_real": range_payload(df.get("氧含量_实测值", pd.Series(dtype=float)).tolist()),
            "particle_size_real_lt_20": range_payload([item["particle_size_real_lt_20"] for item in particle_records]),
            "particle_size_real_20_38": range_payload([item["particle_size_real_20_38"] for item in particle_records]),
            "particle_size_real_38_40": range_payload([item["particle_size_real_38_40"] for item in particle_records]),
            "particle_size_real_gt_40": range_payload([item["particle_size_real_gt_40"] for item in particle_records]),
        },
        "particle_profiles": build_particle_profiles(particle_records),
        "powder_specs": sorted({sanitize_powder_spec(x) for x in df.get("锡粉规格", pd.Series(dtype=str)).dropna().astype(str)}),
        "wetting_classes": sorted({str(x) for x in df.get("润湿等级", pd.Series(dtype=str)).dropna().astype(str)}),
        "collapse_categories": sorted({str(x) for x in df.get("坍塌类别", pd.Series(dtype=str)).dropna().astype(str)}),
        "solderball_levels": sorted({str(x) for x in df.get("锡珠等级", pd.Series(dtype=str)).dropna().astype(str)}),
        "flux_pastes": sorted({str(x) for x in df.get("助焊膏", pd.Series(dtype=str)).dropna().astype(str)}),
        "particle_templates": particle_templates,
    }


@router.get("/alloys", response_model=List[AlloyPreset])
def get_alloys():
    global _alloy_presets_cache
    if _alloy_presets_cache is not None:
        return _alloy_presets_cache
    df = load_reference_dataframe()
    if df is None or "合金牌号" not in df.columns:
        _alloy_presets_cache = []
        return _alloy_presets_cache
    numeric_cols = ["Pb", "Ag", "Fe", "Cu", "Bi", "Sb", "氧含量_实测值"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)
    presets = []
    for alloy_grade, group in df.groupby("合金牌号", dropna=True):
        mean_pb = float(group["Pb"].mean())
        raw_pb_sample = group.get("Pb", pd.Series(dtype=object)).iloc[0] if len(group) else mean_pb
        presets.append(
            AlloyPreset(
                alloy_grade=str(alloy_grade),
                pb=mean_pb,
                ag=float(group["Ag"].mean()),
                fe=float(group["Fe"].mean()),
                cu=float(group["Cu"].mean()),
                bi=float(group["Bi"].mean()),
                sb=float(group["Sb"].mean()),
                oxygen_real=float(group["氧含量_实测值"].mean()),
                lead_type=detect_lead_type(alloy_grade, raw_pb_sample),
            )
        )
    _alloy_presets_cache = sorted(presets, key=lambda item: item.alloy_grade)
    return _alloy_presets_cache


@router.post("/model/retrain", dependencies=[Depends(require_admin)])
def retrain_model(db: Session = Depends(get_db)):
    try:
        data_items = db.query(SolderPasteData).all()
        if not data_items:
            return {"success": False, "message": "数据库中没有数据，无法训练"}
        df = training_dataframe_from_db(data_items)
        if df.empty:
            return {"success": False, "message": "数据库记录缺少原始训练字段，无法训练"}
        success, msg = ai_engine.train(df)
        db.add(
            Experiment(
                experiment_name=datetime.now().strftime("%Y%m%d-%H%M%S") + "-Training",
                composition_x={"data_count": len(df), "result": "Success" if success else "Failed"},
                properties_y={"accuracy": ai_engine.model_info.get("accuracy", {})},
            )
        )
        db.commit()
        return {"success": success, "message": msg, "info": ai_engine.model_info}
    except Exception as exc:
        db.rollback()
        return {"success": False, "message": f"训练触发异常: {exc}"}


@router.post("/predict", response_model=PredictionResponse)
def predict_performance(request: PredictionRequest, db: Session = Depends(get_db)):
    start_time = time.time()
    x = request.features
    flux_percent = float(x.get("flux_percent", 0) or 0)
    alloy_content = x.get("alloy_content")
    if alloy_content is None:
        alloy_content = 100 - flux_percent
    alloy_content = float(alloy_content or 0)
    particle_json = x.get(PARTICLE_JSON_COL) or x.get("particle_distribution_real_json")
    if isinstance(particle_json, dict):
        particle_json = json.dumps(particle_json, ensure_ascii=False)
    if not particle_json:
        particle_json = build_particle_json_from_legacy_fields(x)

    feature_payload = {
        "助焊膏": str(x.get("flux_paste", x.get("flux_type", "D1"))),
        "助焊剂比例%": flux_percent,
        "合金含量（%）": alloy_content,
        "Ag": float(x.get("ag", 0) or 0),
        "Cu": float(x.get("cu", 0) or 0),
        "Pb": float(x.get("pb", 0) or 0),
        "Fe": float(x.get("fe", 0) or 0),
        "Bi": float(x.get("bi", 0) or 0),
        "Sb": float(x.get("sb", 0) or 0),
        "氧含量_实测值": float(x.get("oxygen_real", x.get("oxygen", 0)) or 0),
        "Sn": x.get("sn", "余量"),
        PARTICLE_JSON_COL: particle_json,
    }

    try:
        ai_result = ai_engine.predict_forward(feature_payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    predictions = {
        "viscosity": ai_result.get("黏度初值", 0),
        "ti": ai_result.get("Ti", 0),
        "powder_spec": sanitize_powder_spec(ai_result.get("锡粉规格", "N/A")),
        "wetting_level": ai_result.get("润湿等级", "N/A"),
        "collapse_category": ai_result.get("坍塌类别", "N/A"),
        "solderball_level": ai_result.get("锡珠等级", "N/A"),
        "powder_spec_top_probs": sanitize_prob_list(ai_result.get("锡粉规格_top_probs")),
        "wetting_level_top_probs": sanitize_prob_list(ai_result.get("润湿等级_top_probs")),
        "collapse_category_top_probs": sanitize_prob_list(ai_result.get("坍塌类别_top_probs")),
        "solderball_level_top_probs": sanitize_prob_list(ai_result.get("锡珠等级_top_probs")),
    }
    score = score_from_predictions(predictions)
    execution_time = (time.time() - start_time) * 1000

    if request.log:
        try:
            db.add(
                Experiment(
                    experiment_name=datetime.now().strftime("%Y%m%d-%H%M%S") + "-Forward",
                    composition_x={**x, PARTICLE_JSON_COL: particle_json},
                    properties_y=predictions,
                )
            )
            db.commit()
        except Exception as exc:
            print(f"Failed to save experiment: {exc}")

    return {
        "predictions": predictions,
        "score": score,
        "execution_time_ms": round(execution_time, 2),
    }


# ── 报告导出 ──────────────────────────────────────────────

class ReportRequest(BaseModel):
    """报告生成请求。"""
    report_type: str  # "prediction" | "optimization"
    predictions: Optional[Dict[str, Any]] = None
    score: Optional[float] = None
    input_features: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[float] = 0
    best_result: Optional[Dict[str, Any]] = None
    recommended_params: Optional[Dict[str, Any]] = None
    impact_groups: Optional[List[Dict]] = None
    operator: Optional[str] = "Admin"


@router.post("/report")
def generate_report(req: ReportRequest):
    """
    生成 PDF 报告并返回文件流。

    - report_type="prediction" → 性能预测报告（需要 predictions + input_features）
    - report_type="optimization" → 配方优化报告（需要 best_result）
    """
    from backend.app.api.report_generator import (
        generate_prediction_report,
        generate_optimization_report,
    )

    try:
        # ── 兼容性：前端可能发了外层壳 {predictions:{...}, score, ...} ──
        preds = req.predictions or {}
        if not preds.get("viscosity") and preds.get("predictions"):
            # 旧版前端把整个响应对象当 predictions 发了，自动解包
            preds = preds["predictions"]
            req.score = preds.get("score") or req.score or 0

        if req.report_type == "prediction":
            if not preds or not req.input_features:
                raise HTTPException(400, "prediction 类型报告需要 predictions 和 input_features")
            pdf_bytes = generate_prediction_report(
                predictions=preds,
                score=req.score or 0,
                input_features=req.input_features,
                execution_time_ms=req.execution_time_ms or 0,
                operator=req.operator or "Admin",
            )
            filename = f"锡膏性能预测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        elif req.report_type == "optimization":
            pdf_bytes = generate_optimization_report(
                base_predictions=req.predictions or {},
                base_input=req.input_features or {},
                best_result=req.best_result or {},
                recommended_params=req.recommended_params,
                impact_groups=req.impact_groups,
                operator=req.operator or "Admin",
            )
            filename = f"锡膏配方优化报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        else:
            raise HTTPException(400, f"不支持的报告类型: {req.report_type}")

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"report.pdf\"; "
                    f"filename*=UTF-8''{quote(filename)}"
                )
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"[REPORT ERROR] type={type(exc).__name__}, msg={exc}")
        raise HTTPException(500, f"报告生成失败: {exc}")


@router.get("/history", response_model=HistoryResponse)
def get_history(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Experiment)
        if search:
            if search.isdigit():
                query = query.filter((Experiment.id == int(search)) | (Experiment.experiment_name.contains(search)))
            else:
                query = query.filter(Experiment.experiment_name.contains(search))
        total = query.count()
        sort_column = getattr(Experiment, sort_by, Experiment.created_at)
        query = query.order_by(asc(sort_column) if order == "asc" else desc(sort_column))
        return {"items": query.offset(skip).limit(limit).all(), "total": total}
    except OperationalError:
        return {"items": [], "total": 0}


@router.delete("/history/clear", dependencies=[Depends(require_admin)])
def clear_history(db: Session = Depends(get_db)) -> dict:
    """清空全部操作记录（Experiment）。危险操作，仅 Admin。

    仅删除操作记录，不影响训练数据(SolderPasteData)与上传记录(DataUpload)。
    """
    try:
        deleted = db.query(Experiment).delete()
        db.commit()
        return {"success": True, "message": f"已清空 {deleted} 条操作记录", "deleted": deleted}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清空操作记录失败: {exc}") from exc


@router.get("/history/export")
def export_history(
    search: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    db: Session = Depends(get_db),
):
    """导出操作记录为 Excel(.xlsx)，复用搜索/排序筛选；展开 composition_x/properties_y 为列。"""
    from openpyxl import Workbook

    try:
        query = db.query(Experiment)
        if search:
            if search.isdigit():
                query = query.filter(
                    (Experiment.id == int(search)) | (Experiment.experiment_name.contains(search))
                )
            else:
                query = query.filter(Experiment.experiment_name.contains(search))
        sort_column = getattr(Experiment, sort_by, Experiment.created_at)
        query = query.order_by(asc(sort_column) if order == "asc" else desc(sort_column))
        items = query.all()

        def rec_type(name):
            if not name:
                return "其他操作"
            if "Forward" in name:
                return "正向推理"
            if "Backward" in name:
                return "反向推理"
            if "Training" in name:
                return "模型训练"
            if "Vision" in name:
                return "图像识别"
            if "Upload" in name:
                return "数据上传"
            return "其他操作"

        x_keys: List[str] = []
        y_keys: List[str] = []
        for exp in items:
            x = exp.composition_x if isinstance(exp.composition_x, dict) else {}
            y = exp.properties_y if isinstance(exp.properties_y, dict) else {}
            for k in x:
                if k not in x_keys:
                    x_keys.append(k)
            for k in y:
                if k not in y_keys:
                    y_keys.append(k)

        wb = Workbook()
        ws = wb.active
        ws.title = "操作记录"
        headers = ["ID", "操作类型", "操作名称", "操作时间"] + [f"输入_{k}" for k in x_keys] + [f"输出_{k}" for k in y_keys]
        ws.append(headers)
        for idx, exp in enumerate(items):
            x = exp.composition_x if isinstance(exp.composition_x, dict) else {}
            y = exp.properties_y if isinstance(exp.properties_y, dict) else {}
            row = [
                exp.id,
                rec_type(exp.experiment_name),
                exp.experiment_name,
                exp.created_at.strftime("%Y-%m-%d %H:%M:%S") if exp.created_at else "",
            ]
            # 将非标量值（dict/list）转为 JSON 字符串，避免 openpyxl 写入失败
            import json
            for k in x_keys:
                v = x.get(k, "")
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                row.append(v)
            for k in y_keys:
                v = y.get(k, "")
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                row.append(v)
            ws.append(row)
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 18
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"操作记录_{ts}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=f"导出失败: {exc}\n{traceback.format_exc()}") from exc


# ---------------------------------------------------------------------------
# 用户个人信息（代理读写 portal SQLite 用户库，与数据管理平台实现一致）
# ---------------------------------------------------------------------------
_PORTAL_DIR = Path(__file__).resolve().parents[5] / "portal" / "backend"
_PORTAL_DB = _PORTAL_DIR / "yunxi_portal.db"


def _get_portal_conn() -> "sqlite3.Connection":
    if not _PORTAL_DB.exists():
        raise HTTPException(status_code=500, detail="门户用户库不存在")
    conn = sqlite3.connect(str(_PORTAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/user/profile")
def get_user_profile(user=Depends(require_login)):
    if user.id is None:
        raise HTTPException(status_code=401, detail="无效的用户标识")
    with _get_portal_conn() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, email, role FROM users WHERE id = ?",
            (user.id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row["email"],
        "role": row["role"],
    }


@router.put("/user/profile")
def update_user_profile(body: dict, user=Depends(require_login)):
    if user.id is None:
        raise HTTPException(status_code=401, detail="无效的用户标识")

    display_name = body.get("display_name")
    email = body.get("email")
    new_password = body.get("password")
    current_password = body.get("current_password")

    if email:
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email).strip()):
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        email = str(email).strip().lower()

    if new_password:
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码至少 6 位")
        if not current_password:
            raise HTTPException(status_code=400, detail="修改密码必须提供当前密码")
        from portal.backend.auth import verify_password, hash_password

        with _get_portal_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            if not row or not verify_password(current_password, row["password_hash"]):
                raise HTTPException(status_code=400, detail="当前密码错误")
        password_hash = hash_password(new_password)
    else:
        password_hash = None

    with _get_portal_conn() as conn:
        if email:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, user.id),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="该邮箱已被其他用户使用")

        sets = []
        params = []
        if display_name is not None:
            sets.append("display_name = ?")
            params.append(display_name)
        if email is not None:
            sets.append("email = ?")
            params.append(email)
        if password_hash:
            sets.append("password_hash = ?")
            params.append(password_hash)
        if not sets:
            return {"detail": "无变更"}
        params.append(user.id)
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    return {"detail": "更新成功"}


@router.get("/me")
def get_me(user=Depends(require_login)):
    base = user.to_dict()
    if user.id:
        try:
            portal_db = Path(__file__).resolve().parents[5] / "portal" / "backend" / "yunxi_portal.db"
            if portal_db.exists():
                conn = sqlite3.connect(str(portal_db))
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT display_name, email FROM users WHERE id = ?", (user.id,)
                ).fetchone()
                conn.close()
                if row:
                    base["display_name"] = row["display_name"]
                    base["email"] = row["email"]
        except Exception:
            pass
    return base
