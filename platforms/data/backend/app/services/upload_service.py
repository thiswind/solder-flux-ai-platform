from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from yunxi_data_platform.config import PlatformPaths
ALLOWED_EXTENSIONS = {
    "overall": {".xlsx", ".xls"},
    "specific": {".xlsx", ".xls"},
    "image": {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"},
}
# 与 yunxi_data_platform.image_inventory.LEAD_GROUPS 保持一致：
# 图片匹配只认 uploads/image/ 下第一层为 有铅/无铅 的目录
IMAGE_LEAD_GROUPS = {"有铅", "无铅"}

# 上传去重：每个上传目录维护一份「内容 sha256 -> 文件名」索引，避免重复内容落盘。
_HASH_INDEX_NAME = ".upload_hash_index.json"
_HASH_INDEX_LOCKS: dict[Path, threading.Lock] = {}
_HASH_INDEX_LOCKS_GUARD = threading.Lock()


def _hash_index_path(upload_dir: Path) -> Path:
    return upload_dir / _HASH_INDEX_NAME


def _get_dir_lock(upload_dir: Path) -> threading.Lock:
    with _HASH_INDEX_LOCKS_GUARD:
        lock = _HASH_INDEX_LOCKS.get(upload_dir)
        if lock is None:
            lock = threading.Lock()
            _HASH_INDEX_LOCKS[upload_dir] = lock
        return lock


def _load_hash_index(upload_dir: Path) -> dict[str, str]:
    path = _hash_index_path(upload_dir)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_hash_index(upload_dir: Path, index: dict[str, str]) -> None:
    path = _hash_index_path(upload_dir)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _sanitize_filename(file_name: str) -> str:
    return Path(file_name or "uploaded_file").name


def _sanitize_relative_path(raw_path: str) -> str:
    """Sanitize a relative path from the frontend to prevent path traversal."""
    if not raw_path:
        return ""
    normalized = raw_path.replace("\\", "/")
    if len(normalized) > 1 and normalized[1] == ":":
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    parts = []
    for part in normalized.split("/"):
        if part in ("", ".", ".."):
            continue
        parts.append(part)
    return "/".join(parts)


def _build_target_path(target_dir: Path, file_name: str) -> Path:
    candidate = target_dir / _sanitize_filename(file_name)
    if not candidate.exists():
        return candidate

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = candidate.stem
    suffix = candidate.suffix
    return target_dir / f"{stem}_{timestamp}{suffix}"


def _normalize_image_rel(raw_path: str) -> str:
    """图片按目录层级匹配（有铅/无铅 → 锡膏型号 → 批次目录）。

    浏览器选择文件夹上传时，webkitRelativePath 会以『所选文件夹名』作为第一层，
    例如：测试素材/有铅/Sn63Pb37/12345/img.png。
    这里自动剥掉最外层的『包装文件夹』，让第一层对齐到 有铅/无铅，
    否则模型匹配会因第一层不是 有铅/无铅 而整层跳过。
    若路径中从头到尾都不含 有铅/无铅（用户可能选错了目录），则保留原始结构，避免数据丢失。
    """
    parts = [p for p in _sanitize_relative_path(raw_path).split("/") if p]
    original = parts[:]
    while parts and parts[0] not in IMAGE_LEAD_GROUPS:
        parts = parts[1:]
    if not parts:
        parts = original
    return "/".join(parts)


def resolve_upload_dir(project_root: Path, dataset_type: str) -> Path:
    paths = PlatformPaths.from_root(project_root)
    upload_targets = {
        "overall": paths.overall_upload_dir,
        "specific": paths.specific_upload_dir,
        "image": paths.image_upload_dir,
    }
    if dataset_type not in upload_targets:
        raise ValueError(f"不支持的数据类型: {dataset_type}")
    upload_dir = upload_targets[dataset_type]
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


async def _stream_write_upload(upload: UploadFile, target_path: Path) -> str:
    """分块流式写入：边收边写并实时计算内容 sha256，避免整批文件同时驻留内存；
    写盘丢进线程池，不阻塞单进程 uvicorn 的事件循环（否则大图批次会卡死整个服务端）。
    返回文件内容摘要，供上传去重判定复用。"""
    CHUNK_SIZE = 1024 * 1024  # 1 MB
    digest = hashlib.sha256()

    def _write() -> None:
        with open(target_path, "wb") as fh:
            while True:
                chunk = upload.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                fh.write(chunk)

    await run_in_threadpool(_write)
    return digest.hexdigest()


async def save_upload_files(
    project_root: Path,
    dataset_type: str,
    files: list[UploadFile],
    relative_paths: list[str] | None = None,
) -> dict[str, object]:
    """保存上传文件。遇到不支持的文件类型会跳过而不是整批失败。
    
    返回 dict: { saved_files: [...], skipped: [{filename, reason}, ...] }
    """
    if dataset_type not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的数据类型: {dataset_type}")

    upload_dir = resolve_upload_dir(project_root, dataset_type)
    allowed_extensions = ALLOWED_EXTENSIONS[dataset_type]
    saved_files: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    dir_lock = _get_dir_lock(upload_dir)

    for i, upload in enumerate(files):
        raw_rel = ""
        if relative_paths and i < len(relative_paths) and relative_paths[i]:
            raw_rel = relative_paths[i]
        else:
            raw_rel = upload.filename or ""

        if dataset_type == "image":
            # 图片按目录层级匹配，需保证第一层是 有铅/无铅
            safe_rel = _normalize_image_rel(raw_rel)
        elif raw_rel:
            safe_rel = _sanitize_relative_path(raw_rel)
        else:
            safe_rel = _sanitize_filename(upload.filename or "")

        target_path = upload_dir / safe_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)

        suffix = target_path.suffix.lower()
        if suffix not in allowed_extensions:
            skipped.append({
                "filename": upload.filename or f"文件#{i}",
                "reason": f"不支持的文件类型 .{suffix}（允许: {', '.join(sorted(allowed_extensions))}）",
            })
            await upload.close()
            continue

        # 先流式写入临时文件并实时计算内容 hash（单次 I/O，不重复读盘）
        part_path = target_path.with_suffix(target_path.suffix + ".part")
        content_hash = await _stream_write_upload(upload, part_path)
        await upload.close()

        with dir_lock:
            index = _load_hash_index(upload_dir)
            existing = index.get(content_hash)
            if existing is not None:
                # 已存在相同内容的文件 → 丢弃本次副本，不重复存储
                try:
                    part_path.unlink()
                except OSError:
                    pass
                duplicates.append({"filename": target_path.name, "existing": existing})
                continue

            # 确定最终落盘文件名（处理同名冲突）
            final_path = target_path
            if final_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_path = final_path.parent / f"{final_path.stem}_{timestamp}{final_path.suffix}"
            try:
                os.replace(part_path, final_path)
            except OSError:
                part_path.replace(final_path)

            index[content_hash] = final_path.name
            _save_hash_index(upload_dir, index)

        target_path = final_path

        try:
            rel_path = str(target_path.relative_to(project_root))
        except ValueError:
            rel_path = str(target_path)

        saved_files.append(
            {
                "dataset_type": dataset_type,
                "file_name": target_path.name,
                "absolute_path": str(target_path),
                "relative_path": rel_path,
                "file_size": target_path.stat().st_size,
                "modified_time": datetime.fromtimestamp(target_path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )

    return {"saved_files": saved_files, "skipped": skipped, "duplicates": duplicates}


def list_uploaded_files(project_root: Path) -> list[dict[str, object]]:
    paths = PlatformPaths.from_root(project_root)
    upload_targets = {
        "overall": paths.overall_upload_dir,
        "specific": paths.specific_upload_dir,
        "image": paths.image_upload_dir,
    }
    records: list[dict[str, object]] = []
    for dataset_type, upload_dir in upload_targets.items():
        if not upload_dir.exists():
            continue

        for file_path in upload_dir.rglob("*"):
            if not file_path.is_file():
                continue
            # 排除上传去重用的隐藏索引文件与未完成的临时文件
            if file_path.name.startswith(".") or file_path.suffix == ".part":
                continue
            stat = file_path.stat()
            try:
                rel_path = str(file_path.relative_to(project_root))
            except ValueError:
                rel_path = str(file_path)
            records.append(
                {
                    "dataset_type": dataset_type,
                    "file_name": file_path.name,
                    "absolute_path": str(file_path),
                    "relative_path": rel_path,
                    "file_size": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )

    return sorted(records, key=lambda item: item["modified_time"], reverse=True)


def compute_source_signature(project_root: Path) -> tuple[str, int]:
    """对三个上传桶做一次轻量指纹：只 stat（不读文件内容），收集每条文件的
    (类型, 相对路径, 大小, 修改时间) 并排序后做 sha256。

    与 list_uploaded_files 过滤规则保持一致：跳过以 "." 开头的隐藏索引文件与
    未完成的 ".part" 临时文件。图片目录即使有上千个文件也只需 stat，开销极低。

    返回 (signature_hex, file_count)。当上传目录完全无变化时，两次调用的
    signature 必然一致；任一文件被新增/删除/替换（mtime 或 size 变化）都会改变结果。
    """
    paths = PlatformPaths.from_root(project_root)
    upload_targets = {
        "overall": paths.overall_upload_dir,
        "specific": paths.specific_upload_dir,
        "image": paths.image_upload_dir,
    }
    entries: list[tuple[str, str, int, str]] = []
    for dataset_type, upload_dir in upload_targets.items():
        if not upload_dir.exists():
            continue
        for file_path in upload_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith(".") or file_path.suffix == ".part":
                continue
            stat = file_path.stat()
            try:
                rel_path = str(file_path.relative_to(project_root))
            except ValueError:
                rel_path = str(file_path)
            entries.append(
                (
                    dataset_type,
                    rel_path,
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                )
            )

    entries.sort()
    digest = hashlib.sha256()
    for entry in entries:
        digest.update("|".join(map(str, entry)).encode("utf-8"))
    return digest.hexdigest(), len(entries)
