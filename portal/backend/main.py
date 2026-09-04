"""云锡统一门户 — FastAPI 应用 (端口 8003)。

提供: 注册 / 登录 / 登出 / 当前用户 / 平台清单 / 用户管理(Admin)。
前端为静态单页(Vanilla JS + 自定义 CSS), 风格对齐两个现有平台。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import auth, db, models, schemas

app = FastAPI(title="云锡统一门户 Yunxi Portal")


@app.on_event("startup")
def _startup() -> None:
    """启动期: 建表 + 旧库迁移(补 email 列) + 默认管理员。"""
    db.init_db()


# ---- CORS(便于本地前后端分离调试) ----
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8003").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COOKIE_NAME = "yx_token"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---------------- 依赖 ----------------
def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()


def get_current_user(request: Request, database: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = auth.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    user = database.get(models.User, int(payload["sub"]))
    if not user or user.disabled:
        raise HTTPException(status_code=401, detail="用户不可用")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def _to_out(u: models.User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "display_name": u.display_name,
        "email": u.email,
        "disabled": u.disabled,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# 简单邮箱格式校验(无需引入 email-validator 依赖)
import re as _re
_EMAIL_RE = _re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ---------------- 认证 ----------------
@app.post("/api/v1/auth/register")
def register(data: schemas.RegisterIn, database: Session = Depends(get_db)):
    """开放注册, 默认角色 Users(注册用户与 Admin 登录后均看到两张平台卡片)。"""
    email = (data.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if database.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if database.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="该邮箱已被注册")
    user = models.User(
        username=data.username,
        password_hash=auth.hash_password(data.password),
        role="Users",
        display_name=data.display_name or data.username,
        email=email,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return {"msg": "注册成功", "user": _to_out(user)}


@app.post("/api/v1/auth/login")
def login(data: schemas.LoginIn, response: Response, database: Session = Depends(get_db)):
    user = database.query(models.User).filter(models.User.username == data.username).first()
    if not user or not auth.verify_password(data.password, user.password_hash) or user.disabled:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_token(user.id, user.username, user.role)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=auth.TOKEN_EXPIRE_HOURS * 3600,
        path="/",
    )
    return {"msg": "登录成功", "user": _to_out(user), "role": user.role}


@app.post("/api/v1/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"msg": "已退出登录"}


# ---------------- 演示令牌（URL 直登）----------------
DEMO_TOKEN_DAYS = int(os.getenv("DEMO_TOKEN_DAYS", "30"))


@app.post("/api/v1/auth/demo-token")
def issue_demo_token(user: models.User = Depends(get_current_user)):
    """为当前登录用户签发长效演示令牌（30 天）。演示场景：把直登链接发给访问者即可免密进入。"""
    token = auth.create_demo_token(user.id, user.username, user.role, days=DEMO_TOKEN_DAYS)
    return {"token": token, "days": DEMO_TOKEN_DAYS, "username": user.username}


@app.get("/t/{token}")
def token_login(token: str):
    """URL 令牌直登：验签通过即种 SSO Cookie 并回门户首页。"""
    payload = auth.decode_token(token)
    if not payload or payload.get("typ") != "demo":
        raise HTTPException(status_code=401, detail="演示令牌无效或已过期")
    resp = RedirectResponse(url="../#/home", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=DEMO_TOKEN_DAYS * 86400,
        path="/",
    )
    return resp


@app.get("/api/v1/auth/me")
def me(user: models.User = Depends(get_current_user)):
    return _to_out(user)


@app.get("/api/v1/platforms")
def platforms(_: models.User = Depends(get_current_user)):
    """登录后展示的两张平台卡片(权限差异在各平台内部实现)。"""
    return [
        {
            "id": "compute",
            "name": "锡膏智能计算平台",
            "url": os.getenv("COMPUTE_URL", "http://localhost:8001"),
            "color": "blue",
            "accent": "#2080f0",
        },
        {
            "id": "data",
            "name": "锡膏数据管理平台",
            "url": os.getenv("DATA_URL", "http://localhost:8000"),
            "color": "multicolor",
            "accent": "#18a058",
        },
    ]


# ---------------- 用户管理(Admin) ----------------
@app.get("/api/v1/users")
def list_users(_: models.User = Depends(require_admin), database: Session = Depends(get_db)):
    return [_to_out(u) for u in database.query(models.User).order_by(models.User.id).all()]


@app.post("/api/v1/users")
def create_user(data: schemas.UserCreate, _: models.User = Depends(require_admin),
                database: Session = Depends(get_db)):
    if database.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    email = None
    if data.email:
        email = data.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        if database.query(models.User).filter(models.User.email == email).first():
            raise HTTPException(status_code=400, detail="该邮箱已被注册")
    role = data.role if data.role in ("Admin", "Users") else "Users"
    user = models.User(
        username=data.username,
        password_hash=auth.hash_password(data.password),
        role=role,
        display_name=data.display_name or data.username,
        email=email,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return {"msg": "创建成功", "user": _to_out(user)}


@app.put("/api/v1/users/{user_id}")
def update_user(user_id: int, data: schemas.UserUpdate, _: models.User = Depends(require_admin),
                database: Session = Depends(get_db)):
    user = database.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if data.password:
        user.password_hash = auth.hash_password(data.password)
    if data.role in ("Admin", "Users"):
        user.role = data.role
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        new_email = data.email.strip().lower() if data.email else None
        if new_email:
            if not _EMAIL_RE.match(new_email):
                raise HTTPException(status_code=400, detail="邮箱格式不正确")
            dup = database.query(models.User).filter(
                models.User.email == new_email, models.User.id != user_id
            ).first()
            if dup:
                raise HTTPException(status_code=400, detail="该邮箱已被注册")
        user.email = new_email
    if data.disabled is not None:
        if user.username == "admin" and data.disabled:
            raise HTTPException(status_code=400, detail="默认管理员不可禁用")
        user.disabled = data.disabled
    database.commit()
    return {"msg": "更新成功", "user": _to_out(user)}


@app.delete("/api/v1/users/{user_id}")
def delete_user(user_id: int, _: models.User = Depends(require_admin),
                database: Session = Depends(get_db)):
    user = database.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="默认管理员不可删除")
    database.delete(user)
    database.commit()
    return {"msg": "删除成功"}


# ---------------- 静态前端 ----------------
if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
        raise HTTPException(status_code=404, detail="Not Found")
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-store"})
    return JSONResponse({"detail": "portal 前端未构建"}, status_code=200)
