"""Vite SPA 静态文件挂载（开发阶段骨架）"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_static_files(app: FastAPI) -> None:
    """将web/dist/目录挂载为SPA静态文件服务。

    注意：必须在所有API路由之后调用mount，
    因为"/"会捕获所有未匹配的路径。
    前端构建产物在步骤17完成后才存在，
    开发阶段此mount不生效（目录不存在时跳过）。
    """
    try:
        app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")
    except RuntimeError:
        # web/dist/尚未构建，开发阶段跳过挂载
        pass
