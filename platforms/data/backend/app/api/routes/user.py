"""用户个人信息 API（代理查询/更新 portal SQLite 用户库）。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from shared.auth_client import require_login, CurrentUser

router = APIRouter(prefix="/user", tags=["user"])

# 定位 portal SQLite（从 routes/user.py 上 6 层到项目根 F:\Yunxi_Project）
_PORTAL_DIR = Path(__file__).resolve().parents[6] / "portal" / "backend"
_PORTAL_DB = _PORTAL_DIR / "yunxi_portal.db"


def _get_portal_conn() -> sqlite3.Connection:
    if not _PORTAL_DB.exists():
        raise HTTPException(status_code=500, detail="门户用户库不存在")
    conn = sqlite3.connect(str(_PORTAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/profile")
def get_profile(user: CurrentUser = Depends(require_login)) -> dict:
    """返回当前用户的完整信息（含 display_name / email）。"""
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


@router.put("/profile")
def update_profile(
    body: dict,
    user: CurrentUser = Depends(require_login),
) -> dict:
    """更新当前用户的 display_name / email / password。"""
    if user.id is None:
        raise HTTPException(status_code=401, detail="无效的用户标识")

    display_name = body.get("display_name")
    email = body.get("email")
    new_password = body.get("password")
    current_password = body.get("current_password")

    # 邮箱格式校验
    if email:
        import re
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email).strip()):
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        email = str(email).strip().lower()

    # 改密码必须验证当前密码
    if new_password:
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码至少 6 位")
        if not current_password:
            raise HTTPException(status_code=400, detail="修改密码必须提供当前密码")

        from portal.backend.auth import verify_password

        with _get_portal_conn() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user.id,)
            ).fetchone()
            if not row or not verify_password(current_password, row["password_hash"]):
                raise HTTPException(status_code=400, detail="当前密码错误")

        from portal.backend.auth import hash_password
        password_hash = hash_password(new_password)
    else:
        password_hash = None

    with _get_portal_conn() as conn:
        # 检查邮箱唯一性（排除自己）
        if email:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, user.id),
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="该邮箱已被其他用户使用")

        # 构建动态 UPDATE
        sets: list[str] = []
        params: list = []

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
