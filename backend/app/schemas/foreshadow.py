"""伏笔管理 Pydantic Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ForeshadowStatus(str, Enum):
    """伏笔状态枚举"""
    PENDING = "pending"  # 待埋入
    PLANTED = "planted"  # 已埋入
    RESOLVED = "resolved"  # 已回收
    PARTIALLY_RESOLVED = "partially_resolved"  # 部分回收
    ABANDONED = "abandoned"  # 已废弃


class ForeshadowSourceType(str, Enum):
    """伏笔来源类型"""
    ANALYSIS = "analysis"  # 分析提取
    MANUAL = "manual"  # 手动添加


class ForeshadowCategory(str, Enum):
    """伏笔分类"""
    IDENTITY = "identity"  # 身世
    MYSTERY = "mystery"  # 悬念
    ITEM = "item"  # 物品
    RELATIONSHIP = "relationship"  # 关系
    EVENT = "event"  # 事件
    ABILITY = "ability"  # 能力
    PROPHECY = "prophecy"  # 预言


class ForeshadowBase(BaseModel):
    """伏笔基础信息"""
    title: str = Field(..., min_length=1, max_length=200, description="伏笔标题")
    content: str = Field(..., min_length=1, description="伏笔详细内容/描述")
    hint_text: Optional[str] = Field(None, description="埋伏笔时的暗示文本")
    resolution_text: Optional[str] = Field(None, description="回收伏笔时的揭示文本")
    
    # 章节关联
    plant_chapter_number: Optional[int] = Field(None, ge=1, description="计划埋入章节号")
    target_resolve_chapter_number: Optional[int] = Field(None, ge=1, description="计划回收章节号")
    
    # 状态
    is_long_term: bool = Field(False, description="是否长线伏笔")
    
    # 重要性
    importance: float = Field(0.5, ge=0.0, le=1.0, description="重要性评分 0.0-1.0")
    strength: int = Field(5, ge=1, le=10, description="伏笔强度 1-10")
    subtlety: int = Field(5, ge=1, le=10, description="隐藏度 1-10")
    
    # 关联信息
    related_characters: Optional[List[str]] = Field(None, description="关联角色名列表")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    category: Optional[str] = Field(None, description="分类")
    
    # 备注
    notes: Optional[str] = Field(None, description="创作备注")
    resolution_notes: Optional[str] = Field(None, description="回收方式说明")
    
    # AI辅助设置
    auto_remind: bool = Field(True, description="是否自动提醒")
    remind_before_chapters: int = Field(5, ge=1, le=20, description="提前几章提醒")
    include_in_context: bool = Field(True, description="是否包含在生成上下文中")


class ForeshadowCreate(ForeshadowBase):
    """创建伏笔请求"""
    project_id: str = Field(..., description="项目ID")


class ForeshadowUpdate(BaseModel):
    """更新伏笔请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    hint_text: Optional[str] = None
    resolution_text: Optional[str] = None
    
    plant_chapter_number: Optional[int] = Field(None, ge=1)
    target_resolve_chapter_number: Optional[int] = Field(None, ge=1)
    
    status: Optional[ForeshadowStatus] = None
    is_long_term: Optional[bool] = None
    
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    strength: Optional[int] = Field(None, ge=1, le=10)
    subtlety: Optional[int] = Field(None, ge=1, le=10)
    urgency: Optional[int] = Field(None, ge=0, le=3)
    
    related_characters: Optional[List[str]] = None
    related_foreshadow_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    
    notes: Optional[str] = None
    resolution_notes: Optional[str] = None
    
    auto_remind: Optional[bool] = None
    remind_before_chapters: Optional[int] = Field(None, ge=1, le=20)
    include_in_context: Optional[bool] = None


class ForeshadowResponse(ForeshadowBase):
    """伏笔响应"""
    id: str
    project_id: str
    
    source_type: Optional[str] = None
    source_memory_id: Optional[str] = None
    source_analysis_id: Optional[str] = None
    
    plant_chapter_id: Optional[str] = None
    target_resolve_chapter_id: Optional[str] = None
    actual_resolve_chapter_id: Optional[str] = None
    actual_resolve_chapter_number: Optional[int] = None
    
    status: str = "pending"
    urgency: int = 0
    
    related_foreshadow_ids: Optional[List[str]] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    planted_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ForeshadowListResponse(BaseModel):
    """伏笔列表响应"""
    total: int
    items: List[ForeshadowResponse]
    stats: Optional[dict] = None


class ForeshadowStatsResponse(BaseModel):
    """伏笔统计响应"""
    total: int
    pending: int
    planted: int
    resolved: int
    partially_resolved: int
    abandoned: int
    long_term_count: int
    overdue_count: int  # 超期未回收数量


class PlantForeshadowRequest(BaseModel):
    """标记伏笔埋入请求"""
    chapter_id: str = Field(..., description="埋入章节ID")
    chapter_number: int = Field(..., ge=1, description="埋入章节号")
    hint_text: Optional[str] = Field(None, description="暗示文本")


class ResolveForeshadowRequest(BaseModel):
    """标记伏笔回收请求"""
    chapter_id: str = Field(..., description="回收章节ID")
    chapter_number: int = Field(..., ge=1, description="回收章节号")
    resolution_text: Optional[str] = Field(None, description="揭示文本")
    is_partial: bool = Field(False, description="是否部分回收")


class SyncFromAnalysisRequest(BaseModel):
    """从分析同步伏笔请求"""
    chapter_ids: Optional[List[str]] = Field(None, description="指定章节ID列表，为空则同步全部")
    overwrite_existing: bool = Field(False, description="是否覆盖已存在的伏笔")
    auto_set_planted: bool = Field(True, description="自动设置为已埋入状态")


class SyncFromAnalysisResponse(BaseModel):
    """从分析同步伏笔响应"""
    synced_count: int
    skipped_count: int
    new_foreshadows: List[ForeshadowResponse]
    skipped_reasons: List[dict]


class ForeshadowContextRequest(BaseModel):
    """获取章节伏笔上下文请求"""
    chapter_number: int = Field(..., ge=1, description="章节号")
    include_pending: bool = Field(True, description="包含待埋入伏笔")
    include_overdue: bool = Field(True, description="包含超期伏笔")
    lookahead: int = Field(5, ge=1, le=20, description="向前看几章")


class ForeshadowContextResponse(BaseModel):
    """伏笔上下文响应"""
    chapter_number: int
    context_text: str
    pending_plant: List[ForeshadowResponse]  # 本章待埋入
    pending_resolve: List[ForeshadowResponse]  # 即将需要回收
    overdue: List[ForeshadowResponse]  # 超期未回收
    recently_planted: List[ForeshadowResponse]  # 最近埋入（可铺垫）