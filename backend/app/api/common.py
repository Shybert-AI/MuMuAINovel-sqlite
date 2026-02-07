"""API 公共函数模块

包含跨 API 模块共享的通用函数和工具。
"""
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.models.project import Project
from app.logger import get_logger

logger = get_logger(__name__)


async def verify_project_access(
    project_id: str, 
    user_id: Optional[str], 
    db: AsyncSession
) -> Project:
    """
    验证用户是否有权访问指定项目
    
    统一的项目访问验证函数，确保：
    1. 用户已登录
    2. 项目存在
    3. 用户有权访问该项目
    
    Args:
        project_id: 项目ID
        user_id: 用户ID（从 request.state.user_id 获取）
        db: 数据库会话
        
    Returns:
        Project: 验证通过后返回项目对象
        
    Raises:
        HTTPException: 
            - 401: 用户未登录
            - 404: 项目不存在或用户无权访问
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        logger.warning(f"项目访问被拒绝: project_id={project_id}, user_id={user_id}")
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    
    return project


def get_user_id(request: Request) -> Optional[str]:
    """
    从请求中获取用户ID
    
    这是一个便捷函数，用于从 request.state 中提取 user_id。
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        用户ID，如果未登录则返回 None
    """
    return getattr(request.state, 'user_id', None)


async def verify_project_access_from_request(
    project_id: str,
    request: Request,
    db: AsyncSession
) -> Project:
    """
    从请求中验证项目访问权限（便捷函数）
    
    结合 get_user_id 和 verify_project_access，简化调用。
    
    Args:
        project_id: 项目ID
        request: FastAPI 请求对象
        db: 数据库会话
        
    Returns:
        Project: 验证通过后返回项目对象
        
    Raises:
        HTTPException: 401/404
        
    Usage:
        project = await verify_project_access_from_request(project_id, request, db)
    """
    user_id = get_user_id(request)
    return await verify_project_access(project_id, user_id, db)