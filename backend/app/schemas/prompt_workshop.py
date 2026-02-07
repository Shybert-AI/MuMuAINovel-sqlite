"""提示词工坊 Pydantic Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ==================== 请求模型 ====================

class ImportRequest(BaseModel):
    """导入提示词请求"""
    custom_name: Optional[str] = Field(None, max_length=100, description="自定义名称")


class DownloadRequest(BaseModel):
    """记录下载请求（云端使用）"""
    instance_id: str = Field(..., description="实例标识")
    user_identifier: str = Field(..., description="用户标识")


class PromptSubmissionCreate(BaseModel):
    """提交提示词请求"""
    name: str = Field(..., max_length=100, description="提示词名称")
    description: Optional[str] = Field(None, description="提示词描述")
    prompt_content: str = Field(..., description="提示词内容")
    category: str = Field(default="general", max_length=50, description="分类")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    author_display_name: Optional[str] = Field(None, max_length=100, description="作者显示名")
    is_anonymous: bool = Field(default=False, description="是否匿名发布")
    source_style_id: Optional[int] = Field(None, description="来源写作风格ID")


class ReviewRequest(BaseModel):
    """审核请求"""
    action: str = Field(..., pattern="^(approve|reject)$", description="操作：approve/reject")
    review_note: Optional[str] = Field(None, description="审核备注")
    category: Optional[str] = Field(None, description="分类（可调整）")
    tags: Optional[List[str]] = Field(None, description="标签（可调整）")


class AdminItemCreate(BaseModel):
    """管理员创建提示词"""
    name: str = Field(..., max_length=100, description="提示词名称")
    description: Optional[str] = Field(None, description="提示词描述")
    prompt_content: str = Field(..., description="提示词内容")
    category: str = Field(default="general", description="分类")
    tags: Optional[List[str]] = Field(None, description="标签列表")


class AdminItemUpdate(BaseModel):
    """管理员更新提示词"""
    name: Optional[str] = Field(None, max_length=100, description="提示词名称")
    description: Optional[str] = Field(None, description="提示词描述")
    prompt_content: Optional[str] = Field(None, description="提示词内容")
    category: Optional[str] = Field(None, description="分类")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    status: Optional[str] = Field(None, description="状态")


# ==================== 响应模型 ====================

class PromptWorkshopItemResponse(BaseModel):
    """提示词条目响应"""
    id: str
    name: str
    description: Optional[str] = None
    prompt_content: str
    category: str
    tags: Optional[List[str]] = None
    author_name: Optional[str] = None
    is_official: bool
    download_count: int
    like_count: int
    is_liked: Optional[bool] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class PromptSubmissionResponse(BaseModel):
    """提交记录响应"""
    id: str
    name: str
    description: Optional[str] = None
    prompt_content: Optional[str] = None
    category: str
    tags: Optional[List[str]] = None
    author_display_name: Optional[str] = None
    is_anonymous: bool
    status: str
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    source_instance: Optional[str] = None
    submitter_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class CategoryInfo(BaseModel):
    """分类信息"""
    id: str
    name: str
    count: int


class WorkshopItemsListResponse(BaseModel):
    """提示词列表响应"""
    success: bool = True
    data: dict  # 包含 total, page, limit, items, categories


class WorkshopStatusResponse(BaseModel):
    """服务状态响应"""
    mode: str
    instance_id: str
    cloud_url: Optional[str] = None
    cloud_connected: Optional[bool] = None