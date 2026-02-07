"""大纲相关的Pydantic模型"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# 角色预测相关Schema
class CharacterPredictionRequest(BaseModel):
    """角色预测请求"""
    project_id: str
    start_chapter: int
    chapter_count: int = 3
    plot_stage: str = "development"
    story_direction: Optional[str] = "自然延续"
    enable_mcp: bool = True


class PredictedCharacter(BaseModel):
    """预测的角色信息"""
    name: Optional[str] = None
    role_description: str
    suggested_role_type: str
    importance: str
    appearance_chapter: int
    key_abilities: List[str] = []
    plot_function: str
    relationship_suggestions: List[Dict[str, str]] = []


class CharacterPredictionResponse(BaseModel):
    """角色预测响应"""
    needs_new_characters: bool
    reason: str
    character_count: int
    predicted_characters: List[PredictedCharacter]


# 组织预测相关Schema
class OrganizationPredictionRequest(BaseModel):
    """组织预测请求"""
    project_id: str
    start_chapter: int
    chapter_count: int = 3
    plot_stage: str = "development"
    story_direction: Optional[str] = "自然延续"
    enable_mcp: bool = True


class PredictedOrganization(BaseModel):
    """预测的组织信息"""
    name: Optional[str] = None
    organization_description: str
    organization_type: str
    importance: str
    appearance_chapter: int
    power_level: int = 50
    plot_function: str
    location: Optional[str] = None
    motto: Optional[str] = None
    initial_members: List[Dict[str, Any]] = []
    relationship_suggestions: List[Dict[str, str]] = []


class OrganizationPredictionResponse(BaseModel):
    """组织预测响应"""
    needs_new_organizations: bool
    reason: str
    organization_count: int
    predicted_organizations: List[PredictedOrganization]


class OutlineBase(BaseModel):
    """大纲基础模型"""
    title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节内容概要")


class OutlineCreate(BaseModel):
    """创建大纲的请求模型"""
    project_id: str = Field(..., description="所属项目ID")
    title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节内容概要")
    order_index: int = Field(..., description="章节序号", ge=1)
    structure: Optional[str] = Field(None, description="结构化大纲数据(JSON)")


class OutlineUpdate(BaseModel):
    """更新大纲的请求模型"""
    title: Optional[str] = None
    content: Optional[str] = None
    # order_index 不允许通过普通更新修改，只能通过 reorder_outlines 接口批量调整
    # structure 暂不支持修改


class OutlineResponse(BaseModel):
    """大纲响应模型"""
    id: str
    project_id: str
    title: str
    content: str
    structure: Optional[str] = None
    order_index: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OutlineGenerateRequest(BaseModel):
    """AI生成大纲的请求模型 - 支持全新生成和智能续写"""
    project_id: str = Field(..., description="项目ID")
    genre: Optional[str] = Field(None, description="小说类型，如：玄幻、都市、悬疑等")
    theme: str = Field(..., description="小说主题")
    chapter_count: int = Field(..., ge=1, description="章节数量")
    narrative_perspective: str = Field(..., description="叙事视角")
    world_context: Optional[dict] = Field(None, description="世界观背景")
    characters_context: Optional[list] = Field(None, description="角色信息")
    target_words: int = Field(100000, description="目标字数")
    requirements: Optional[str] = Field(None, description="其他特殊要求")
    provider: Optional[str] = Field(None, description="AI提供商")
    model: Optional[str] = Field(None, description="AI模型")
    
    # 续写相关参数
    mode: str = Field("auto", description="生成模式: auto(自动判断), new(全新生成), continue(续写)")
    story_direction: Optional[str] = Field(None, description="故事发展方向提示(续写时使用)")
    plot_stage: str = Field("development", description="情节阶段: development(发展), climax(高潮), ending(结局)")
    keep_existing: bool = Field(False, description="是否保留现有大纲(续写时)")
    enable_mcp: bool = Field(True, description="是否启用MCP工具增强（搜索情节设计参考）")
    
    # 自动角色引入相关参数
    enable_auto_characters: bool = Field(True, description="是否启用自动角色引入（根据剧情推进自动创建新角色）")
    require_character_confirmation: bool = Field(True, description="是否需要用户确认新角色（False则AI预测的角色直接创建）")
    confirmed_characters: Optional[List[Dict[str, Any]]] = Field(None, description="用户确认的角色列表（跳过预测直接创建）")
    
    # 自动组织引入相关参数
    enable_auto_organizations: bool = Field(True, description="是否启用自动组织引入（根据剧情推进自动创建新组织）")
    require_organization_confirmation: bool = Field(True, description="是否需要用户确认新组织（False则AI预测的组织直接创建）")
    confirmed_organizations: Optional[List[Dict[str, Any]]] = Field(None, description="用户确认的组织列表（跳过预测直接创建）")


class ChapterOutlineGenerateRequest(BaseModel):
    """为单个章节生成大纲的请求模型"""
    outline_id: str = Field(..., description="大纲ID")
    context: Optional[str] = Field(None, description="额外上下文")
    provider: Optional[str] = Field(None, description="AI提供商")
    model: Optional[str] = Field(None, description="AI模型")


class OutlineListResponse(BaseModel):
    """大纲列表响应模型"""
    total: int
    items: list[OutlineResponse]


class ChapterPlanItem(BaseModel):
    """单个章节规划项"""
    sub_index: int = Field(..., description="子章节序号", ge=1)
    title: str = Field(..., description="章节标题")
    plot_summary: str = Field(..., description="剧情摘要(200-300字)")
    key_events: list[str] = Field(..., description="关键事件列表")
    character_focus: list[str] = Field(..., description="主要涉及的角色")
    emotional_tone: str = Field(..., description="情感基调")
    narrative_goal: str = Field(..., description="叙事目标")
    conflict_type: str = Field(..., description="冲突类型")
    estimated_words: int = Field(3000, description="预计字数", ge=1000)
    scenes: Optional[list[str]] = Field(None, description="场景列表(可选)")


class OutlineExpansionRequest(BaseModel):
    """大纲展开为多章节的请求模型（outline_id从路径参数获取）"""
    target_chapter_count: int = Field(3, description="目标章节数", ge=1, le=10)
    expansion_strategy: str = Field("balanced", description="展开策略: balanced(均衡), climax(高潮重点), detail(细节丰富)")
    enable_scene_analysis: bool = Field(False, description="是否包含场景规划")
    auto_create_chapters: bool = Field(True, description="是否自动创建章节记录")
    provider: Optional[str] = Field(None, description="AI提供商")
    model: Optional[str] = Field(None, description="AI模型")


class OutlineExpansionResponse(BaseModel):
    """大纲展开响应模型"""
    outline_id: str = Field(..., description="大纲ID")
    outline_title: str = Field(..., description="大纲标题")
    target_chapter_count: int = Field(..., description="目标章节数")
    actual_chapter_count: int = Field(..., description="实际生成的章节数")
    expansion_strategy: str = Field(..., description="使用的展开策略")
    chapter_plans: list[ChapterPlanItem] = Field(..., description="章节规划列表")
    created_chapters: Optional[list] = Field(None, description="已创建的章节列表")


class BatchOutlineExpansionRequest(BaseModel):
    """批量大纲展开请求模型"""
    project_id: str = Field(..., description="项目ID")
    outline_ids: Optional[list[str]] = Field(None, description="要展开的大纲ID列表(为空则展开所有)")
    chapters_per_outline: int = Field(3, description="每个大纲的目标章节数", ge=1, le=10)
    expansion_strategy: str = Field("balanced", description="展开策略")
    enable_scene_analysis: bool = Field(False, description="是否包含场景规划")
    auto_create_chapters: bool = Field(True, description="是否自动创建章节记录")
    provider: Optional[str] = Field(None, description="AI提供商")
    model: Optional[str] = Field(None, description="AI模型")


class BatchOutlineExpansionResponse(BaseModel):
    """批量大纲展开响应模型"""
    project_id: str = Field(..., description="项目ID")
    total_outlines_expanded: int = Field(..., description="总共展开的大纲数")
    total_chapters_created: int = Field(..., description="总共创建的章节数")
    expansion_results: list[OutlineExpansionResponse] = Field(..., description="展开结果列表")
    skipped_outlines: Optional[list[dict]] = Field(None, description="跳过的大纲列表(已展开)")


class CreateChaptersFromPlansRequest(BaseModel):
    """根据已有规划创建章节的请求模型"""
    chapter_plans: list[ChapterPlanItem] = Field(..., description="章节规划列表（来自之前的AI生成结果）")


class CreateChaptersFromPlansResponse(BaseModel):
    """根据已有规划创建章节的响应模型"""
    outline_id: str = Field(..., description="大纲ID")
    outline_title: str = Field(..., description="大纲标题")
    chapters_created: int = Field(..., description="创建的章节数")
    created_chapters: list = Field(..., description="创建的章节列表")