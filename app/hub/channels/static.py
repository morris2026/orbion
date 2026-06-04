"""Vite SPA 静态文件挂载 — API路由优先，未匹配路径返回index.html"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST_DIR = Path("web/dist")
INDEX_HTML = DIST_DIR / "index.html"


def mount_static_files(app: FastAPI) -> None:
    """将web/dist/目录挂载为SPA静态文件服务。

    SPA路由策略：
    1. 静态资源（/assets/*等）由StaticFiles直接服务
    2. 所有未匹配的路径返回index.html（前端Router处理）
    3. 以上必须在所有API路由之后注册
    """
    if not INDEX_HTML.exists():
        # web/dist/尚未构建，开发阶段跳过挂载
        return

    # 静态资源子路径
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="static-assets")

    # favicon等根目录静态文件
    app.mount("/static", StaticFiles(directory=str(DIST_DIR)), name="static-files")

    # SPA fallback：所有未匹配的路径返回index.html
    @app.get("/{path:path}")
    async def spa_fallback(request: Request, path: str) -> FileResponse:
        # 如果请求的是dist目录中存在的静态文件，直接返回
        file_path = DIST_DIR / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # 否则返回index.html，让前端Router处理
        return FileResponse(str(INDEX_HTML))
