"""伏笔管理API路由"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.database import get_db
from app.api.common import verify_project_access
from app.services.foreshadow_service import foreshadow_service
from app.schemas.foreshadow import (
    ForeshadowCreate,
    ForeshadowUpdate,
    ForeshadowResponse,
    ForeshadowListResponse,
    ForeshadowStatsResponse,
    PlantForeshadowRequest,
    ResolveForeshadowRequest,
    SyncFromAnalysisRequest,
    SyncFromAnalysisResponse,
    ForeshadowContextResponse
)
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/foreshadows", tags=["foreshadows"])


@router.get("/projects/{project_id}", response_model=ForeshadowListResponse)
async def get_project_foreshadows(
    project_id: str,
    request: Request,
    status: Optional[str] = Query(None, description="状态筛选: pending/planted/resolved/abandoned"),
    category: Optional[str] = Query(None, description="分类筛选"),
    source_type: Optional[str] = Query(None, description="来源筛选: analysis/manual"),
    is_long_term: Optional[bool] = Query(None, description="是否长线伏笔"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(50, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取项目所有伏笔
    
    支持按状态、分类、来源筛选，支持分页
    """
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(project_id, user_id, db)
        
        result = await foreshadow_service.get_project_foreshadows(
            db=db,
            project_id=project_id,
            status=status,
            category=category,
            source_type=source_type,
            is_long_term=is_long_term,
            page=page,
            limit=limit
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取伏笔列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取伏笔列表失败: {str(e)}")


@router.get("/projects/{project_id}/stats", response_model=ForeshadowStatsResponse)
async def get_foreshadow_stats(
    project_id: str,
    request: Request,
    current_chapter: Optional[int] = Query(None, ge=1, description="当前章节号(用于计算超期)"),
    db: AsyncSession = Depends(get_db)
):
    """获取项目伏笔统计"""
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(project_id, user_id, db)
        
        stats = await foreshadow_service.get_stats(db, project_id, current_chapter)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取伏笔统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取伏笔统计失败: {str(e)}")


@router.get("/projects/{project_id}/context/{chapter_number}", response_model=ForeshadowContextResponse)
async def get_chapter_foreshadow_context(
    project_id: str,
    chapter_number: int,
    request: Request,
    include_pending: bool = Query(True, description="包含待埋入伏笔"),
    include_overdue: bool = Query(True, description="包含超期伏笔"),
    lookahead: int = Query(5, ge=1, le=20, description="向前看几章"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取章节生成的伏笔上下文
    
    用于在章节生成时提供伏笔提醒
    """
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(project_id, user_id, db)
        
        context = await foreshadow_service.build_chapter_context(
            db=db,
            project_id=project_id,
            chapter_number=chapter_number,
            include_pending=include_pending,
            include_overdue=include_overdue,
            lookahead=lookahead
        )
        
        return context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取伏笔上下文失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取伏笔上下文失败: {str(e)}")


@router.get("/projects/{project_id}/pending-resolve")
async def get_pending_resolve_foreshadows(
    project_id: str,
    request: Request,
    current_chapter: int = Query(..., ge=1, description="当前章节号"),
    lookahead: int = Query(5, ge=1, le=20, description="向前看几章"),
    db: AsyncSession = Depends(get_db)
):
    """获取待回收伏笔列表(用于章节生成提醒)"""
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(project_id, user_id, db)
        
        foreshadows = await foreshadow_service.get_pending_resolve_foreshadows(
            db=db,
            project_id=project_id,
            current_chapter=current_chapter,
            lookahead=lookahead
        )
        
        return {
            "total": len(foreshadows),
            "items": [f.to_dict() for f in foreshadows]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取待回收伏笔失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取待回收伏笔失败: {str(e)}")


@router.get("/{foreshadow_id}", response_model=ForeshadowResponse)
async def get_foreshadow(
    foreshadow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取单个伏笔详情"""
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        # 验证权限
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        return foreshadow.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取伏笔详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取伏笔详情失败: {str(e)}")


@router.post("", response_model=ForeshadowResponse)
async def create_foreshadow(
    data: ForeshadowCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    创建伏笔(手动添加)
    
    创建一个新的自定义伏笔
    """
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(data.project_id, user_id, db)
        
        foreshadow = await foreshadow_service.create_foreshadow(db, data)
        return foreshadow.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 创建伏笔失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建伏笔失败: {str(e)}")


@router.put("/{foreshadow_id}", response_model=ForeshadowResponse)
async def update_foreshadow(
    foreshadow_id: str,
    data: ForeshadowUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新伏笔"""
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        updated = await foreshadow_service.update_foreshadow(db, foreshadow_id, data)
        return updated.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 更新伏笔失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新伏笔失败: {str(e)}")


@router.delete("/{foreshadow_id}")
async def delete_foreshadow(
    foreshadow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除伏笔"""
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        await foreshadow_service.delete_foreshadow(db, foreshadow_id)
        
        return {"message": "伏笔删除成功", "id": foreshadow_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除伏笔失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除伏笔失败: {str(e)}")


@router.post("/{foreshadow_id}/plant", response_model=ForeshadowResponse)
async def plant_foreshadow(
    foreshadow_id: str,
    data: PlantForeshadowRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    标记伏笔为已埋入
    
    将伏笔状态从pending改为planted，记录埋入章节
    """
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        updated = await foreshadow_service.mark_as_planted(db, foreshadow_id, data)
        return updated.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 标记伏笔埋入失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"标记伏笔埋入失败: {str(e)}")


@router.post("/{foreshadow_id}/resolve", response_model=ForeshadowResponse)
async def resolve_foreshadow(
    foreshadow_id: str,
    data: ResolveForeshadowRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    标记伏笔为已回收
    
    将伏笔状态改为resolved或partially_resolved
    """
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        updated = await foreshadow_service.mark_as_resolved(db, foreshadow_id, data)
        return updated.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 标记伏笔回收失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"标记伏笔回收失败: {str(e)}")


@router.post("/{foreshadow_id}/abandon", response_model=ForeshadowResponse)
async def abandon_foreshadow(
    foreshadow_id: str,
    request: Request,
    reason: Optional[str] = Query(None, description="废弃原因"),
    db: AsyncSession = Depends(get_db)
):
    """
    标记伏笔为已废弃
    
    决定不再使用此伏笔
    """
    try:
        foreshadow = await foreshadow_service.get_foreshadow(db, foreshadow_id)
        
        if not foreshadow:
            raise HTTPException(status_code=404, detail="伏笔不存在")
        
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(foreshadow.project_id, user_id, db)
        
        updated = await foreshadow_service.mark_as_abandoned(db, foreshadow_id, reason)
        return updated.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 标记伏笔废弃失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"标记伏笔废弃失败: {str(e)}")


@router.post("/projects/{project_id}/sync-from-analysis", response_model=SyncFromAnalysisResponse)
async def sync_foreshadows_from_analysis(
    project_id: str,
    data: SyncFromAnalysisRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    从分析结果同步伏笔
    
    从章节分析结果中提取伏笔信息，同步到伏笔管理表
    """
    try:
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(project_id, user_id, db)
        
        result = await foreshadow_service.sync_from_analysis(db, project_id, data)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 同步伏笔失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"同步伏笔失败: {str(e)}")