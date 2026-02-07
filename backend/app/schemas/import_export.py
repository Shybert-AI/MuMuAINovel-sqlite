"""导入导出相关的Pydantic模型"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ExportOptions(BaseModel):
    """导出选项"""
    include_generation_history: bool = Field(False, description="是否包含生成历史")
    include_writing_styles: bool = Field(True, description="是否包含写作风格")
    include_careers: bool = Field(True, description="是否包含职业系统")
    include_memories: bool = Field(False, description="是否包含故事记忆（数据量可能较大）")
    include_plot_analysis: bool = Field(False, description="是否包含剧情分析")


class ChapterExportData(BaseModel):
    """章节导出数据"""
    title: str
    content: Optional[str] = None
    summary: Optional[str] = None
    chapter_number: int
    word_count: int = 0
    status: str = "draft"
    created_at: Optional[str] = None
    
    # 大纲细化功能新增字段
    outline_title: Optional[str] = None  # 关联的大纲标题（用于导入时重建关联）
    sub_index: Optional[int] = None  # 大纲下的子章节序号
    expansion_plan: Optional[Dict[str, Any]] = None  # 展开规划详情（JSON对象）


class CharacterExportData(BaseModel):
    """角色导出数据"""
    name: str
    age: Optional[str] = None
    gender: Optional[str] = None
    is_organization: bool = False
    role_type: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    appearance: Optional[str] = None
    relationships: Optional[str] = None
    traits: Optional[List[str]] = None
    organization_type: Optional[str] = None
    organization_purpose: Optional[str] = None
    organization_members: Optional[str] = None
    avatar_url: Optional[str] = None
    main_career_id: Optional[str] = None
    main_career_stage: Optional[int] = None
    sub_careers: Optional[str] = None
    # 组织专属字段
    power_level: Optional[int] = None
    location: Optional[str] = None
    motto: Optional[str] = None
    color: Optional[str] = None
    created_at: Optional[str] = None


class OutlineExportData(BaseModel):
    """大纲导出数据"""
    title: str
    content: Optional[str] = None
    structure: Optional[str] = None
    order_index: Optional[int] = None
    created_at: Optional[str] = None


class RelationshipExportData(BaseModel):
    """关系导出数据"""
    source_name: str
    target_name: str
    relationship_name: Optional[str] = None
    intimacy_level: int = 50
    status: str = "active"
    description: Optional[str] = None
    started_at: Optional[str] = None


class OrganizationExportData(BaseModel):
    """组织详情导出数据"""
    character_name: str
    parent_org_name: Optional[str] = None
    power_level: int = 50
    member_count: int = 0
    location: Optional[str] = None
    motto: Optional[str] = None
    color: Optional[str] = None


class OrganizationMemberExportData(BaseModel):
    """组织成员导出数据"""
    organization_name: str
    character_name: str
    position: str
    rank: int = 0
    status: str = "active"
    joined_at: Optional[str] = None
    loyalty: int = 50
    contribution: int = 0
    notes: Optional[str] = None


class WritingStyleExportData(BaseModel):
    """写作风格导出数据"""
    name: str
    style_type: str
    preset_id: Optional[str] = None
    description: Optional[str] = None
    prompt_content: str
    order_index: int = 0


class GenerationHistoryExportData(BaseModel):
    """生成历史导出数据"""
    chapter_title: Optional[str] = None
    prompt: Optional[str] = None
    generated_content: Optional[str] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    generation_time: Optional[float] = None
    created_at: Optional[str] = None


class CareerExportData(BaseModel):
    """职业导出数据"""
    name: str
    type: str  # main/sub
    description: Optional[str] = None
    category: Optional[str] = None
    stages: str  # JSON格式的阶段列表
    max_stage: int = 10
    requirements: Optional[str] = None
    special_abilities: Optional[str] = None
    worldview_rules: Optional[str] = None
    attribute_bonuses: Optional[str] = None
    source: str = "ai"
    created_at: Optional[str] = None


class CharacterCareerExportData(BaseModel):
    """角色职业关联导出数据"""
    character_name: str  # 通过名称关联
    career_name: str  # 通过名称关联
    career_type: str  # main/sub
    current_stage: int = 1
    stage_progress: int = 0
    started_at: Optional[str] = None
    reached_current_stage_at: Optional[str] = None
    notes: Optional[str] = None


class StoryMemoryExportData(BaseModel):
    """故事记忆导出数据"""
    chapter_title: Optional[str] = None  # 通过章节标题关联
    memory_type: str
    title: Optional[str] = None
    content: str
    full_context: Optional[str] = None
    related_characters: Optional[List[str]] = None  # 角色名称列表
    related_locations: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    importance_score: float = 0.5
    story_timeline: int
    chapter_position: int = 0
    text_length: int = 0
    is_foreshadow: int = 0
    foreshadow_strength: Optional[float] = None
    created_at: Optional[str] = None


class PlotAnalysisExportData(BaseModel):
    """剧情分析导出数据"""
    chapter_title: str  # 通过章节标题关联
    plot_stage: Optional[str] = None
    conflict_level: Optional[int] = None
    conflict_types: Optional[List[str]] = None
    emotional_tone: Optional[str] = None
    emotional_intensity: Optional[float] = None
    emotional_curve: Optional[Dict[str, float]] = None
    hooks: Optional[List[Dict[str, Any]]] = None
    hooks_count: int = 0
    hooks_avg_strength: Optional[float] = None
    foreshadows: Optional[List[Dict[str, Any]]] = None
    foreshadows_planted: int = 0
    foreshadows_resolved: int = 0
    plot_points: Optional[List[Dict[str, Any]]] = None
    plot_points_count: int = 0
    character_states: Optional[List[Dict[str, Any]]] = None
    scenes: Optional[List[Dict[str, Any]]] = None
    pacing: Optional[str] = None
    overall_quality_score: Optional[float] = None
    pacing_score: Optional[float] = None
    engagement_score: Optional[float] = None
    coherence_score: Optional[float] = None
    analysis_report: Optional[str] = None
    suggestions: Optional[List[str]] = None
    word_count: Optional[int] = None
    dialogue_ratio: Optional[float] = None
    description_ratio: Optional[float] = None
    created_at: Optional[str] = None


class ProjectDefaultStyleExportData(BaseModel):
    """项目默认风格导出数据"""
    style_name: str  # 通过风格名称关联


class ProjectExportData(BaseModel):
    """项目完整导出数据"""
    version: str = "1.1.0"  # 升级版本号
    export_time: str
    project: Dict[str, Any]
    chapters: List[ChapterExportData] = []
    characters: List[CharacterExportData] = []
    outlines: List[OutlineExportData] = []
    relationships: List[RelationshipExportData] = []
    organizations: List[OrganizationExportData] = []
    organization_members: List[OrganizationMemberExportData] = []
    writing_styles: List[WritingStyleExportData] = []
    generation_history: List[GenerationHistoryExportData] = []
    # 新增字段
    careers: List[CareerExportData] = []
    character_careers: List[CharacterCareerExportData] = []
    story_memories: List[StoryMemoryExportData] = []
    plot_analysis: List[PlotAnalysisExportData] = []
    project_default_style: Optional[ProjectDefaultStyleExportData] = None


class ImportValidationResult(BaseModel):
    """导入验证结果"""
    valid: bool
    version: str
    project_name: Optional[str] = None
    statistics: Dict[str, int] = {}
    errors: List[str] = []
    warnings: List[str] = []


class ImportResult(BaseModel):
    """导入结果"""
    success: bool
    project_id: Optional[str] = None
    message: str
    statistics: Dict[str, int] = {}
    details: Optional[Dict[str, List[str]]] = None
    warnings: List[str] = []


class CharactersExportRequest(BaseModel):
    """角色/组织批量导出请求"""
    character_ids: List[str] = Field(..., description="要导出的角色/组织ID列表")


class CharactersExportData(BaseModel):
    """角色/组织批量导出数据"""
    version: str = "1.0.0"
    export_time: str
    export_type: str = "characters"
    count: int
    data: List[CharacterExportData]


class CharactersImportResult(BaseModel):
    """角色/组织导入结果"""
    success: bool
    message: str
    statistics: Dict[str, int]
    details: Dict[str, List[str]]
    warnings: List[str] = []