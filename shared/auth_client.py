"""shared/auth_client.py — 跨平台 SSO 验签客户端（纯库，不监听端口）。

被 compute / data 平台的 FastAPI 后端 import，仅做「读 Cookie → 验签 → 返回用户名+角色」，
不连接用户库、不校验密码。与 portal/backend/auth.py 共用同一个 PORTAL_SECRET_KEY。

设计原则：
- 无状态：平台只信任 portal 用同一把密钥签发的 JWT，不再查用户表。
- 与门户同源：浏览器在 localhost 各端口间共享 yx_token Cookie（同站跨端口），
  所以平台后端能从请求里读到 Cookie 并验签。
- 单一密钥来源：若仓库根 .env 存在，会优先载入；否则回退到同字面值默认密钥。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Cookie, Depends, HTTPException

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None

# ---- 定位仓库根并优先载入根 .env（保证门户与平台密钥一致） ----
def _load_repo_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(env_path)
    except Exception:
        # 极简 .env 解析器，避免依赖 python-dotenv
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
COOKIE_NAME = "yx_token"


class CurrentUser:
    """门户令牌中携带的当前用户信息（仅来自 JWT claims，不查库）。"""

    def __init__(self, payload: dict):
        sub = payload.get("sub")
        self.id = int(sub) if sub not in (None, "") else None
        self.username = payload.get("username")
        self.role = payload.get("role") or "Users"
        self.payload = payload

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "role": self.role}

    def is_admin(self) -> bool:
        return self.role == "Admin"


def decode_token(token: str) -> Optional[dict]:
    if jwt is None:
        raise RuntimeError("PyJWT 未安装，无法校验令牌")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None


def require_login(token: Optional[str] = Cookie(None, alias=COOKIE_NAME)) -> CurrentUser:
    """FastAPI 依赖：从 Cookie 读取 yx_token 并验签。失败抛 401。

    直接挂在 API router 上即可让整组接口要求登录。
    """
    if not token:
        raise HTTPException(status_code=401, detail="未登录，请先通过统一门户登录")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期或无效，请重新登录")
    return CurrentUser(payload)


def require_admin(user: CurrentUser = Depends(require_login)) -> CurrentUser:
    """FastAPI 依赖：在 require_login 之上再要求 Admin 角色。失败抛 403。"""
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
