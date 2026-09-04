import os
import sys
from pathlib import Path

# ---- SSO：把仓库根加入 sys.path，以便 import shared.auth_client ----
# 必须在任何业务模块 import 之前执行，否则 endpoints 间接 import shared 会失败
def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if (cur / "shared").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("未找到 shared 目录，无法定位项目根")


_REPO_ROOT = _find_repo_root(Path(__file__))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import Depends
from shared.auth_client import require_login, require_admin

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from urllib.parse import quote
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.core.database import engine, Base, migrate
from backend.app.models import experiment
from backend.app.api.endpoints import router as api_router

# 1. 自动初始化数据库表结构
Base.metadata.create_all(bind=engine)
# 2. 为已有表补充新增列（去重指纹字段）
migrate()

app = FastAPI(
    title="锡膏智能计算平台",
    description="Based on Multimodal Deep Learning for Solder Paste Industry",
    version="1.2.0",
)

# CORS
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
frontend_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_path, "assets")), name="assets")


class NoCacheMiddleware(BaseHTTPMiddleware):
    """给所有静态资源响应加 Cache-Control: no-store，避免浏览器缓存旧前端代码。"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") or request.url.path in ("/", "/logo.svg"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(NoCacheMiddleware)

# Include the API router（SSO：整组 /api/v1 接口要求登录）
app.include_router(api_router, prefix="/api/v1", dependencies=[Depends(require_login)])

@app.get("/")
def serve_index():
    index_path = os.path.join(frontend_dist_path, "index.html")
    return FileResponse(index_path, headers={"Cache-Control": "no-store"})

@app.get("/logo.svg")
def serve_logo():
    logo_path = os.path.join(frontend_dist_path, "logo.svg")
    return FileResponse(logo_path, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/manual")
def download_manual(user=Depends(require_login)):
    """下载《锡膏智能计算平台使用说明书》PDF。"""
    manual_path = os.path.join(
        os.path.dirname(__file__), "static", "manual", "compute_platform_manual.pdf"
    )
    if not os.path.exists(manual_path):
        raise HTTPException(status_code=404, detail="使用说明书文件不存在")
    filename = "锡膏智能计算平台V1.0使用说明书.pdf"
    return FileResponse(
        manual_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ---- SPA 兜底：前端路由刷新时返回 index.html ----
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """所有非 API、非静态资源的路径都返回 index.html，由 Vue Router 接管客户端路由。"""
    index_path = os.path.join(frontend_dist_path, "index.html")
    return FileResponse(index_path, headers={"Cache-Control": "no-store"})
