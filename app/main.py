"""Orbion MVP FastAPI应用入口"""

from fastapi import FastAPI

from app.hub.channels.static import mount_static_files

app = FastAPI(title="Orbion MVP")

# API路由将在后续步骤中挂载
# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
