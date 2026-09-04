from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from .config import PlatformPaths


@dataclass
class SourceFileRecord:
    source_type: str
    relative_path: str
    absolute_path: str
    file_name: str
    file_size: int
    modified_time: str
    file_hash: str


def hash_file(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_large_binary(file_path: Path, file_size: int, sample_size: int = 1024 * 512) -> str:
    digest = hashlib.sha256()
    digest.update(str(file_path.name).encode("utf-8", errors="ignore"))
    digest.update(str(file_size).encode("utf-8"))

    with file_path.open("rb") as handle:
        head = handle.read(sample_size)
        digest.update(head)
        if file_size > sample_size:
            tail_offset = max(file_size - sample_size, 0)
            handle.seek(tail_offset)
            digest.update(handle.read(sample_size))

    return digest.hexdigest()


def collect_source_files(
    paths: PlatformPaths,
    include_images: bool = False,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> pd.DataFrame:
    records: List[SourceFileRecord] = []
    processed_count = 0

    def collect(root: Path, source_type: str) -> None:
        nonlocal processed_count
        if not root.exists():
            return
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("~$"):
                continue
            if file_path.suffix.lower() not in {".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                continue

            stat = file_path.stat()
            suffix = file_path.suffix.lower()
            if suffix in {".xlsx", ".xls"}:
                file_hash = hash_file(file_path)
            else:
                # External image repositories can be very large; a sampled fingerprint keeps
                # ingestion responsive while still providing a stable dedupe key.
                file_hash = fingerprint_large_binary(file_path, stat.st_size)

            records.append(
                SourceFileRecord(
                    source_type=source_type,
                    relative_path=str(file_path.relative_to(paths.root_dir)) if file_path.is_relative_to(paths.root_dir) else str(file_path),
                    absolute_path=str(file_path),
                    file_name=file_path.name,
                    file_size=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    file_hash=file_hash,
                )
            )
            processed_count += 1
            if progress_callback and (processed_count == 1 or processed_count % 25 == 0):
                progress = min(18, 10 + processed_count // 25)
                progress_callback(f"正在扫描源文件：{file_path.name}", progress)

    collect(paths.excel_dir / "overall_data", "overall_excel")
    collect(paths.excel_dir / "specific_data", "specific_excel")
    collect(paths.overall_upload_dir, "overall_upload_excel")
    collect(paths.specific_upload_dir, "specific_upload_excel")
    if include_images:
        collect(paths.image_upload_dir, "uploaded_image")

    if progress_callback:
        progress_callback(f"源文件扫描完成，共发现 {processed_count} 个文件", 18)

    return pd.DataFrame([record.__dict__ for record in records])


def ensure_database(paths: PlatformPaths) -> sqlite3.Connection:
    paths.ensure_directories()
    conn = sqlite3.connect(paths.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_run (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_file_inventory (
            source_type TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            absolute_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            modified_time TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            UNIQUE(source_type, file_hash, relative_path)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_artifact (
            artifact_name TEXT PRIMARY KEY,
            artifact_path TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def start_ingestion_run(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "INSERT INTO ingestion_run (started_at, status, message) VALUES (?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), "running", ""),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_ingestion_run(conn: sqlite3.Connection, run_id: int, status: str, message: str) -> None:
    conn.execute(
        "UPDATE ingestion_run SET completed_at = ?, status = ?, message = ? WHERE run_id = ?",
        (datetime.now().isoformat(timespec="seconds"), status, message, run_id),
    )
    conn.commit()


def replace_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    if df.columns.empty:
        df = pd.DataFrame({"message": pd.Series(dtype="object")})
    df.to_sql(table_name, conn, if_exists="replace", index=False)


def upsert_source_inventory(conn: sqlite3.Connection, inventory_df: pd.DataFrame) -> None:
    if inventory_df.empty:
        return

    conn.execute("DELETE FROM source_file_inventory")
    inventory_df.to_sql("source_file_inventory", conn, if_exists="append", index=False)
    conn.commit()


def replace_tables(conn: sqlite3.Connection, tables: Dict[str, pd.DataFrame]) -> None:
    for table_name, df in tables.items():
        replace_table(conn, table_name, df)
    conn.commit()


def export_excel_tables(export_path: Path, sheets: Dict[str, pd.DataFrame]) -> None:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            output_df = df if not df.empty else pd.DataFrame({"message": ["No data"]})
            output_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)


def write_csv_bundle(target_dir: Path, tables: Dict[str, pd.DataFrame]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(target_dir / f"{name}.csv", index=False, encoding="utf-8-sig")


def write_json_summary(target_path: Path, payload: Dict[str, object]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def record_artifact(conn: sqlite3.Connection, artifact_name: str, artifact_path: Path, artifact_type: str) -> None:
    conn.execute(
        """
        INSERT INTO platform_artifact (artifact_name, artifact_path, artifact_type, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(artifact_name) DO UPDATE SET
            artifact_path=excluded.artifact_path,
            artifact_type=excluded.artifact_type,
            updated_at=excluded.updated_at
        """,
        (
            artifact_name,
            str(artifact_path),
            artifact_type,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
