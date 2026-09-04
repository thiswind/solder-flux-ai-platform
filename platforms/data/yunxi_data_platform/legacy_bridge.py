"""Bridge between the pipeline service and the Excel parsing module.

Previously this module dynamically loaded ``excel/data_column.py`` from disk
and read from both the bundled ``excel/`` directory and ``uploads/``.  Now it
imports directly from :mod:`yunxi_data_platform.excel_parser` and reads
**only** from the user-uploaded files under ``uploads/``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd

from .config import PlatformPaths
from .excel_parser import read_overall_data_files, read_specific_data_files


def _dedup_excel_files(directory: Path) -> list[str]:
    """Walk *directory*, return Excel file paths de-duplicated by MD5 content hash."""
    seen: set[str] = set()
    out: list[str] = []
    if not os.path.isdir(directory):
        return out
    for root, _, names in os.walk(directory):
        for name in names:
            if (name.endswith(".xlsx") or name.endswith(".xls")) and not name.startswith("~$"):
                fp = os.path.join(root, name)
                try:
                    with open(fp, "rb") as fh:
                        h = hashlib.md5(fh.read()).hexdigest()
                except OSError:
                    continue
                if h not in seen:
                    seen.add(h)
                    out.append(fp)
    return out


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not valid_frames:
        return pd.DataFrame()
    return pd.concat(valid_frames, ignore_index=True, sort=False)


def read_overall_data(paths: PlatformPaths) -> pd.DataFrame:
    """Read overall data **only** from the user-uploaded files, de-duplicated by content hash."""
    files = _dedup_excel_files(paths.overall_upload_dir)
    if not files:
        return pd.DataFrame()
    return read_overall_data_files(files)


def read_specific_data(paths: PlatformPaths) -> pd.DataFrame:
    """Read specific data **only** from the user-uploaded files."""
    files = _dedup_excel_files(paths.specific_upload_dir)
    if not files:
        return pd.DataFrame()
    return read_specific_data_files(files)
