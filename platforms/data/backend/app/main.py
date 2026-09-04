from __future__ import annotations

import sys
import os
from datetime import datetime

# ---- SSO：把仓库根加入 sys.path，以便 import shared.auth_client ----
# 必须在任何业务模块 import 之前执行，否则 router 间接 import shared 会失败
from pathlib import Path as _Path

def _find_repo_root(start: _Path) -> _Path:
    cur = start.resolve()
    while True:
        if (cur / "shared").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("未找到 shared 目录，无法定位项目根")


_REPO_ROOT = _find_repo_root(_Path(__file__))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import Depends, HTTPException
from urllib.parse import quote
from shared.auth_client import require_login, require_admin

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.entities import IngestionRun

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="锡基材料数据管理与可视化平台后端 API",
)

app.state.max_upload_size = 500 * 1024 * 1024  # 500MB

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
frontend_dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_path, "assets")), name="assets")


class NoCacheMiddleware(BaseHTTPMiddleware):
    """给所有静态资源响应加 Cache-Control: no-store，避免浏览器缓存旧前端代码。"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") or request.url.path in ("/", "/logo.svg"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(NoCacheMiddleware)


def _recover_stale_runs() -> None:
    """启动自愈：把上一个（已退出）进程遗留的 running 状态运行标记为失败。

    后端是单进程模型，跑批在后台任务里同步执行。若进程被重启/中断，
    正在进行的 run 会永远卡在 running，既误导看板，又可能在有“是否运行中”
    判断时被误认成“还有任务在进行”。开机时把这类孤儿 run 收尾为 failed，
    可确保它绝不影响后续跑批。
    """
    try:
        with SessionLocal() as db:
            stale = db.execute(
                select(IngestionRun).where(
                    IngestionRun.status == "running",
                    IngestionRun.completed_at.is_(None),
                )
            ).scalars().all()
            for run in stale:
                run.status = "failed"
                run.message = "进程重启/中断，未完成运行被自动标记为失败"
                run.completed_at = datetime.utcnow()
            if stale:
                db.commit()
                ids = [r.id for r in stale]
                print(f"[Yunxi] recovered {len(stale)} stale run(s): {ids}", file=sys.stderr, flush=True)
    except Exception as exc:  # 自愈失败不应阻断启动
        print(f"[Yunxi] stale run recovery skipped: {exc}", file=sys.stderr, flush=True)


@app.on_event("startup")
def on_startup() -> None:
    app.state.db_ready = False
    app.state.database_error = None
    try:
        Base.metadata.create_all(bind=engine)
        app.state.db_ready = True
        if app.state.db_ready:
            _recover_stale_runs()
    except Exception as exc:
        app.state.database_error = (
            "数据库连接失败，请检查 backend/.env 中的 DATABASE_URL。"
            f" 当前错误: {exc}"
        )
        print(f"[Yunxi] {app.state.database_error}", file=sys.stderr, flush=True)


@app.get("/")
def root():
    index_path = os.path.join(frontend_dist_path, "index.html")
    return FileResponse(index_path, headers={"Cache-Control": "no-store"})


@app.get("/logo.svg")
def serve_logo():
    logo_path = os.path.join(frontend_dist_path, "logo.svg")
    return FileResponse(logo_path, headers={"Cache-Control": "no-store"})


# SSO：整组 /api/v1 接口要求登录
app.include_router(api_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_login)])


@app.get("/api/v1/manual")
def download_manual(user=Depends(require_login)):
    """下载《锡膏数据管理平台使用说明书》PDF。"""
    manual_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "static", "manual", "data_platform_manual.pdf",
    )
    if not os.path.exists(manual_path):
        raise HTTPException(status_code=404, detail="使用说明书文件不存在")
    filename = "锡膏数据管理平台V1.0使用说明书.pdf"
    return FileResponse(
        manual_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/v1/me")
def api_me(user=Depends(require_login)):
    base = user.to_dict()
    # 从 portal SQLite 补充 display_name / email
    if user.id:
        try:
            import sqlite3
            from pathlib import Path
            portal_db = Path(__file__).resolve().parents[4] / "portal" / "backend" / "yunxi_portal.db"
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
            pass  # 降级：返回基础信息
    return base


# ---- SPA 兜底：前端路由（/pipeline, /dashboard, /logs 等）刷新时返回 index.html ----
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """所有非 API、非静态资源的路径都返回 index.html，由 Vue Router 接管客户端路由。"""
    index_path = os.path.join(frontend_dist_path, "index.html")
    return FileResponse(index_path, headers={"Cache-Control": "no-store"})
