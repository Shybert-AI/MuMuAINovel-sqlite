"""伏笔管理数据模型 - 独立管理小说伏笔的埋入和回收"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Foreshadow(Base):
    """
    伏笔管理表 - 独立管理小说伏笔
    
    支持以下功能：
    1. 从章节分析结果自动同步伏笔
    2. 用户手动添加自定义伏笔
    3. 关联埋入章节和计划回收章节
    4. 长线伏笔管理
    5. 章节生成时的伏笔提醒
    """
    __tablename__ = "foreshadows"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # === 伏笔内容 ===
    title = Column(String(200), nullable=False, comment="伏笔标题")
    content = Column(Text, nullable=False, comment="伏笔详细内容/描述")
    hint_text = Column(Text, comment="埋伏笔时的暗示文本(原文摘录或概述)")
    resolution_text = Column(Text, comment="回收伏笔时的揭示文本(原文摘录或概述)")
    
    # === 来源信息 ===
    source_type = Column(String(20), default='manual', comment="来源类型: analysis=分析提取, manual=手动添加")
    source_memory_id = Column(String(100), comment="来源记忆ID(如从分析结果同步)")
    source_analysis_id = Column(String(36), comment="来源分析任务ID")
    
    # === 章节关联 ===
    # 埋入章节
    plant_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), comment="埋入章节ID")
    plant_chapter_number = Column(Integer, comment="埋入章节号(冗余存储便于查询)")
    
    # 计划回收章节
    target_resolve_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), comment="计划回收章节ID")
    target_resolve_chapter_number = Column(Integer, comment="计划回收章节号")
    
    # 实际回收章节
    actual_resolve_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), comment="实际回收章节ID")
    actual_resolve_chapter_number = Column(Integer, comment="实际回收章节号")
    
    # === 状态管理 ===
    status = Column(String(20), default='pending', index=True, comment="""
    伏笔状态:
    - pending: 待埋入(已规划但未写入章节)
    - planted: 已埋入(已在章节中埋下)
    - resolved: 已回收(已在章节中回收)
    - partially_resolved: 部分回收(长线伏笔可能分多次回收)
    - abandoned: 已废弃(决定不再使用此伏笔)
    """)
    
    is_long_term = Column(Boolean, default=False, comment="是否长线伏笔(跨多章的重要伏笔)")
    
    # === 重要性和优先级 ===
    importance = Column(Float, default=0.5, comment="重要性评分 0.0-1.0")
    strength = Column(Integer, default=5, comment="伏笔强度 1-10(影响读者多强烈)")
    subtlety = Column(Integer, default=5, comment="隐藏度 1-10(越高越隐蔽)")
    urgency = Column(Integer, default=0, comment="紧急度: 0=不紧急, 1=需关注, 2=急需回收")
    
    # === 关联信息 ===
    related_characters = Column(JSON, comment="关联角色名列表: ['角色1', '角色2']")
    related_foreshadow_ids = Column(JSON, comment="关联的其他伏笔ID列表(伏笔链)")
    tags = Column(JSON, comment="标签列表: ['身世', '悬念', '反转']")
    category = Column(String(50), comment="分类: identity(身世), mystery(悬念), item(物品), relationship(关系), event(事件)")
    
    # === 备注和说明 ===
    notes = Column(Text, comment="创作备注(仅作者可见)")
    resolution_notes = Column(Text, comment="回收方式说明")
    
    # === AI辅助设置 ===
    auto_remind = Column(Boolean, default=True, comment="是否在章节生成时自动提醒")
    remind_before_chapters = Column(Integer, default=5, comment="提前几章开始提醒回收")
    include_in_context = Column(Boolean, default=True, comment="是否包含在生成上下文中")
    
    # === 时间戳 ===
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    planted_at = Column(DateTime, comment="埋入时间")
    resolved_at = Column(DateTime, comment="回收时间")
    
    def __repr__(self):
        return f"<Foreshadow(id={self.id[:8]}, title={self.title}, status={self.status})>"
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "content": self.content,
            "hint_text": self.hint_text,
            "resolution_text": self.resolution_text,
            "source_type": self.source_type,
            "source_memory_id": self.source_memory_id,
            "plant_chapter_id": self.plant_chapter_id,
            "plant_chapter_number": self.plant_chapter_number,
            "target_resolve_chapter_id": self.target_resolve_chapter_id,
            "target_resolve_chapter_number": self.target_resolve_chapter_number,
            "actual_resolve_chapter_id": self.actual_resolve_chapter_id,
            "actual_resolve_chapter_number": self.actual_resolve_chapter_number,
            "status": self.status,
            "is_long_term": self.is_long_term,
            "importance": self.importance,
            "strength": self.strength,
            "subtlety": self.subtlety,
            "urgency": self.urgency,
            "related_characters": self.related_characters or [],
            "related_foreshadow_ids": self.related_foreshadow_ids or [],
            "tags": self.tags or [],
            "category": self.category,
            "notes": self.notes,
            "resolution_notes": self.resolution_notes,
            "auto_remind": self.auto_remind,
            "remind_before_chapters": self.remind_before_chapters,
            "include_in_context": self.include_in_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "planted_at": self.planted_at.isoformat() if self.planted_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
    
    def to_context_string(self) -> str:
        """
        转换为上下文字符串(用于章节生成提示)
        """
        parts = []
        
        # 基本信息
        parts.append(f"伏笔「{self.title}」")
        
        # 埋入信息
        if self.plant_chapter_number:
            parts.append(f"(第{self.plant_chapter_number}章埋下)")
        
        # 内容摘要
        content_preview = self.content[:100] if len(self.content) > 100 else self.content
        parts.append(f": {content_preview}")
        
        # 计划回收
        if self.target_resolve_chapter_number:
            parts.append(f" [计划第{self.target_resolve_chapter_number}章回收]")
        
        # 关联角色
        if self.related_characters:
            parts.append(f" 涉及: {', '.join(self.related_characters[:3])}")
        
        return "".join(parts)
    
    def get_urgency_level(self, current_chapter: int) -> int:
        """
        计算当前紧急度
        
        Args:
            current_chapter: 当前章节号
        
        Returns:
            0=不紧急, 1=需关注, 2=急需回收, 3=已超期
        """
        if self.status != 'planted' or not self.target_resolve_chapter_number:
            return 0
        
        chapters_remaining = self.target_resolve_chapter_number - current_chapter
        
        if chapters_remaining < 0:
            return 3  # 已超期
        elif chapters_remaining <= 2:
            return 2  # 急需回收
        elif chapters_remaining <= self.remind_before_chapters:
            return 1  # 需关注
        else:
            return 0  # 不紧急