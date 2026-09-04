from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

import pandas as pd

try:
    import cv2
    import numpy as np
    _cv_ok = True
except ImportError:
    _cv_ok = False


# 图片列 -> 对应的分级任务
_IMAGE_TO_TASK = {
    "Wetting_Image_Path": "wetting",
    "SolderBall_Image_Path": "solderball",
    "Collapse_Image_Path": "collapse",
}

# 每个任务输出的中文列 (等级列, 置信度列, 来源列)，对齐训练表 train_filled
_TASK_COLS = {
    "wetting": ("润湿等级", "润湿等级_置信度", "润湿等级_来源"),
    "solderball": ("锡珠等级", "锡珠等级_置信度", "锡珠等级_来源"),
    "collapse": ("坍塌类别", "坍塌类别_置信度", "坍塌类别_来源"),
}

# 每个 task 一把独立锁：三类使用不同 YOLO 模型，可真正并行；同类批量推理时串行。
_TASK_LOCKS = {task: threading.Lock() for task in ("wetting", "solderball", "collapse")}
_PROG_LOCK = threading.Lock()

DEFAULT_SOURCE_TAG = "YOLO自动分级"
DEFAULT_BATCH_SIZE = 16


def _resolve_image_path(raw: str, project_root: Optional[str] = None) -> Optional[str]:
    """将 delivery 中记录的（可能相对的）图片路径解析为真实存在的绝对路径。

    图片路径在 build_delivery_dataset 中按 project_root 记录为相对路径，
    但后端进程以 backend/ 为工作目录启动，os.path.abspath 会错解析到
    backend/uploads/...（不存在）。故：先试 CWD 解析，失败再试 project_root 解析。
    """
    if os.path.isabs(raw) and os.path.exists(raw):
        return raw
    candidates = []
    cwd_resolved = os.path.abspath(raw)
    candidates.append(cwd_resolved)
    if project_root:
        candidates.append(os.path.join(str(project_root), raw))
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    # 都不存在时返回 CWD 解析结果（供调用方记录错误原因）
    return cwd_resolved


def _read_images(paths: List[str]):
    imgs: List = []
    valid_idx: List[int] = []
    for i, p in enumerate(paths):
        try:
            img = cv2.imread(p)
        except Exception:
            img = None
        if img is not None:
            imgs.append(img)
            valid_idx.append(i)
    return imgs, valid_idx


def _grade_batch(image_paths: List[str], task: str, vision_service) -> List[Optional[dict]]:
    """对一批同 task 的图片做批量推理，返回与 image_paths 等长的列表。"""
    n = len(image_paths)
    out: List[Optional[dict]] = [{"error": "read_failed"} for _ in range(n)]
    if n == 0 or not _cv_ok:
        return out

    model = vision_service.models.get(task) if vision_service is not None else None
    if model is None:
        return [{"error": "model_not_loaded"} for _ in range(n)]

    imgs, valid_idx = _read_images(image_paths)
    if not imgs:
        return out

    with _TASK_LOCKS[task]:
        try:
            results = model(imgs)
        except Exception as e:
            print(f"[grade] inference error ({task}): {e}")
            return [{"error": f"inference_error:{e}"} for _ in range(n)]

    for j, r in enumerate(results):
        orig_i = valid_idx[j]
        try:
            if hasattr(r, "probs") and r.probs is not None:
                top1 = int(r.probs.top1)
                conf = float(r.probs.top1conf) if r.probs.top1conf is not None else 0.0
                out[orig_i] = {"class": r.names[top1], "confidence": conf}
            else:
                out[orig_i] = {"error": "no_result"}
        except Exception:
            out[orig_i] = {"error": "parse_error"}
    return out


def grade_delivery_images(
    delivery_df: pd.DataFrame,
    vision_service,
    batch_size: int = DEFAULT_BATCH_SIZE,
    source_tag: str = DEFAULT_SOURCE_TAG,
    progress_callback: Optional[Callable] = None,
    project_root: Optional[str] = None,
) -> pd.DataFrame:
    """对交付数据集的图片做自动视觉分级，直接写出训练表需要的中文标签列。

    相比旧版 auto_grade_delivery_images 的核心优化：
    1. 按 task 分组后批量推理 model([batch])，替代逐张串行，调用次数降 10~50x；
    2. 每个 task 独立锁，wetting/solderball/collapse 三类可真正并行；
    3. 路径预筛 + 准确进度（不再用 processed_tasks // 3 近似）。

    输出中文列（对齐智能计算平台 train_filled）：
        润湿等级 / 润湿等级_来源 / 润湿等级_置信度
        锡珠等级 / 锡珠等级_来源 / 锡珠等级_置信度
        坍塌类别 / 坍塌类别_来源 / 坍塌类别_置信度
    """
    if delivery_df.empty:
        return delivery_df

    # 初始化中文标签列为空
    for task, (level_col, conf_col, src_col) in _TASK_COLS.items():
        for col in (level_col, conf_col, src_col):
            if col not in delivery_df.columns:
                delivery_df[col] = None

    # 收集每个 task 需要推理的图片路径（记录行索引，便于回写）
    task_items: Dict[str, List[tuple]] = {"wetting": [], "solderball": [], "collapse": []}
    for idx, row in delivery_df.iterrows():
        for image_col, task in _IMAGE_TO_TASK.items():
            level_col, conf_col, _ = _TASK_COLS[task]
            raw = row.get(image_col)
            if raw and isinstance(raw, str) and str(raw).strip():
                # 后端以 backend/ 为 CWD 启动，而图片路径相对 project_root 记录，
                # 故优先用 CWD 解析，失败再回退 project_root，避免“无可用图片”误判。
                path = _resolve_image_path(raw, project_root)
                if path and os.path.exists(path):
                    task_items[task].append((idx, path, level_col, conf_col))

    total_images = sum(len(v) for v in task_items.values())
    if total_images == 0:
        if progress_callback:
            progress_callback("无可用图片，跳过自动分级", 97)
        return delivery_df

    print(f"[grade] 启动：{total_images} 张图 "
          f"(wetting={len(task_items['wetting'])}, "
          f"solderball={len(task_items['solderball'])}, "
          f"collapse={len(task_items['collapse'])})")

    counter = {"done": 0}

    def _run_task(task: str):
        items = task_items[task]
        _, _, src_col = _TASK_COLS[task]
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            paths = [p for (_, p, _, _) in batch]
            results = _grade_batch(paths, task, vision_service)
            for (idx, _, level_col, conf_col), res in zip(batch, results):
                if res and "error" not in res:
                    delivery_df.at[idx, level_col] = res.get("class")
                    delivery_df.at[idx, conf_col] = res.get("confidence")
                    delivery_df.at[idx, src_col] = source_tag
            with _PROG_LOCK:
                counter["done"] += len(batch)
                cur = counter["done"]
            if progress_callback:
                pct = 92 + int((cur / total_images) * 5)
                progress_callback(f"正在自动分级图片... ({cur}/{total_images})", min(97, pct))

    active_tasks = [t for t in ("wetting", "solderball", "collapse") if task_items[t]]
    with ThreadPoolExecutor(max_workers=len(active_tasks)) as executor:
        futures = [executor.submit(_run_task, t) for t in active_tasks]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"[grade] task error: {e}")

    if progress_callback:
        progress_callback(f"图片自动分级完成 ({total_images}/{total_images})", 97)
    print(f"[grade] 完成：{total_images} 张图")
    return delivery_df
