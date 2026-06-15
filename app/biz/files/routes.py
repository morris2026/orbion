"""文件操作 API 端点"""

import asyncio
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.files.models import FileContent, FileNode, WriteFileRequest
from app.biz.files.service import FileService
from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

router = APIRouter()


def _validate_repo_name(repo_name: str) -> None:
    if "/" in repo_name or "\\" in repo_name or ".." in repo_name:
        raise HTTPException(status_code=400, detail=f"无效的仓库名: {repo_name}")


def _get_file_service(request: Request) -> FileService:
    return cast(FileService, request.app.state.file_service)


def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


@router.get("/{project_id}/repos/{repo_name}/tree", response_model=list[FileNode])
async def get_file_tree(
    project_id: str,
    repo_name: str,
    user: User = Depends(get_current_user),
    file_service: FileService = Depends(_get_file_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[FileNode]:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    _validate_repo_name(repo_name)
    return file_service.get_file_tree(project_id, repo_name)


@router.get("/{project_id}/repos/{repo_name}/files", response_model=FileContent)
async def read_file(
    project_id: str,
    repo_name: str,
    path: str,
    ref: str | None = None,
    user: User = Depends(get_current_user),
    file_service: FileService = Depends(_get_file_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> FileContent:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    _validate_repo_name(repo_name)
    try:
        content = await asyncio.to_thread(file_service.read_file, project_id, repo_name, path, ref=ref)
    except ValueError:
        raise HTTPException(status_code=403, detail="路径越界")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    return FileContent(path=path, content=content)


@router.put("/{project_id}/repos/{repo_name}/files", response_model=FileContent)
async def write_file(
    project_id: str,
    repo_name: str,
    path: str,
    body: WriteFileRequest,
    user: User = Depends(get_current_user),
    file_service: FileService = Depends(_get_file_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> FileContent:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    _validate_repo_name(repo_name)
    try:
        await asyncio.to_thread(file_service.write_file, project_id, repo_name, path, body.content)
    except ValueError:
        raise HTTPException(status_code=403, detail="路径越界")
    return FileContent(path=path, content=body.content)
