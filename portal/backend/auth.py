"""认证工具 — 密码哈希(bcrypt) + JWT(httpOnly Cookie)。"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Optional

import bcrypt
import jwt

# ---- 单一密钥来源：优先载入仓库根 .env 的 PORTAL_SECRET_KEY ----
# 保证门户与 compute/data 平台用同一把密钥签发/验签 JWT（SSO 同源）。
def _load_repo_env() -> None:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(env_path)
    except Exception:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val


_load_repo_env()

SECRET_KEY = os.getenv("PORTAL_SECRET_KEY", "yunxi-portal-secret-2026-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("PORTAL_TOKEN_HOURS", "12"))


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: int, username: str, role: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_demo_token(user_id: int, username: str, role: str, days: int = 30) -> str:
    """长时效演示令牌（typ=demo 区分普通登录令牌），供 URL 直登使用。"""
    now = datetime.datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "typ": "demo",
        "iat": now,
        "exp": now + datetime.timedelta(days=days),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None
