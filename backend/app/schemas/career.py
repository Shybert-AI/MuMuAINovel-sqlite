"""职业相关的Pydantic模型"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class CareerStage(BaseModel):
    """职业阶段模型"""
    level: int = Field(..., description="阶段等级")
    name: str = Field(..., description="阶段名称")
    description: Optional[str] = Field(None, description="阶段描述")


class CareerBase(BaseModel):
    """职业基础模型"""
    name: str = Field(..., description="职业名称")
    type: str = Field(..., description="职业类型: main(主职业)/sub(副职业)")
    description: Optional[str] = Field(None, description="职业描述")
    category: Optional[str] = Field(None, description="职业分类")
    stages: List[CareerStage] = Field(..., description="职业阶段列表")
    max_stage: int = Field(10, description="最大阶段数")
    requirements: Optional[str] = Field(None, description="职业要求/限制")
    special_abilities: Optional[str] = Field(None, description="特殊能力描述")
    worldview_rules: Optional[str] = Field(None, description="世界观规则关联")
    attribute_bonuses: Optional[Dict[str, str]] = Field(None, description="属性加成")


class CareerCreate(CareerBase):
    """创建职业的请求模型"""
    project_id: str = Field(..., description="项目ID")
    source: str = Field("manual", description="来源: ai/manual")


class CareerUpdate(BaseModel):
    """更新职业的请求模型"""
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    stages: Optional[List[CareerStage]] = None
    max_stage: Optional[int] = None
    requirements: Optional[str] = None
    special_abilities: Optional[str] = None
    worldview_rules: Optional[str] = None
    attribute_bonuses: Optional[Dict[str, str]] = None


class CareerResponse(BaseModel):
    """职业响应模型"""
    id: str
    project_id: str
    name: str
    type: str
    description: Optional[str] = None
    category: Optional[str] = None
    stages: List[CareerStage]
    max_stage: int
    requirements: Optional[str] = None
    special_abilities: Optional[str] = None
    worldview_rules: Optional[str] = None
    attribute_bonuses: Optional[Dict[str, str]] = None
    source: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class CareerListResponse(BaseModel):
    """职业列表响应模型"""
    total: int
    main_careers: List[CareerResponse] = Field(default_factory=list, description="主职业列表")
    sub_careers: List[CareerResponse] = Field(default_factory=list, description="副职业列表")


class CareerGenerateRequest(BaseModel):
    """AI生成职业体系的请求模型"""
    project_id: str = Field(..., description="项目ID")
    main_career_count: int = Field(5, description="主职业数量", ge=1, le=20)
    sub_career_count: int = Field(8, description="副职业数量", ge=0, le=30)
    enable_mcp: bool = Field(False, description="是否启用MCP工具增强")


# ===== 角色职业关联相关 =====

class CharacterCareerBase(BaseModel):
    """角色职业关联基础模型"""
    career_id: str = Field(..., description="职业ID")
    career_type: str = Field(..., description="main(主职业)/sub(副职业)")
    current_stage: int = Field(1, description="当前阶段", ge=1)
    stage_progress: int = Field(0, description="阶段内进度（0-100）", ge=0, le=100)
    started_at: Optional[str] = Field(None, description="开始修炼时间")
    reached_current_stage_at: Optional[str] = Field(None, description="到达当前阶段时间")
    notes: Optional[str] = Field(None, description="备注")


class CharacterCareerCreate(CharacterCareerBase):
    """创建角色职业关联的请求模型"""
    character_id: str = Field(..., description="角色ID")


class CharacterCareerUpdate(BaseModel):
    """更新角色职业关联的请求模型"""
    current_stage: Optional[int] = Field(None, ge=1)
    stage_progress: Optional[int] = Field(None, ge=0, le=100)
    reached_current_stage_at: Optional[str] = None
    notes: Optional[str] = None


class CharacterCareerDetail(BaseModel):
    """角色职业详情模型（包含职业信息）"""
    id: str
    character_id: str
    career_id: str
    career_name: str = Field(..., description="职业名称")
    career_type: str
    current_stage: int
    stage_name: str = Field(..., description="当前阶段名称")
    stage_description: Optional[str] = Field(None, description="当前阶段描述")
    stage_progress: int
    max_stage: int = Field(..., description="该职业的最大阶段")
    started_at: Optional[str] = None
    reached_current_stage_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CharacterCareerResponse(BaseModel):
    """角色职业响应模型"""
    main_career: Optional[CharacterCareerDetail] = Field(None, description="主职业")
    sub_careers: List[CharacterCareerDetail] = Field(default_factory=list, description="副职业列表")


class SetMainCareerRequest(BaseModel):
    """设置主职业请求模型"""
    career_id: str = Field(..., description="职业ID")
    current_stage: int = Field(1, description="当前阶段", ge=1)
    started_at: Optional[str] = Field(None, description="开始修炼时间")


class AddSubCareerRequest(BaseModel):
    """添加副职业请求模型"""
    career_id: str = Field(..., description="职业ID")
    current_stage: int = Field(1, description="当前阶段", ge=1)
    started_at: Optional[str] = Field(None, description="开始修炼时间")


class UpdateCareerStageRequest(BaseModel):
    """更新职业阶段请求模型"""
    current_stage: int = Field(..., description="新的阶段", ge=1)
    stage_progress: int = Field(0, description="阶段进度", ge=0, le=100)
    reached_current_stage_at: Optional[str] = Field(None, description="到达时间")
    notes: Optional[str] = Field(None, description="备注")