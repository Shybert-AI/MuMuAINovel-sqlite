"""职业数据模型"""
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Career(Base):
    """职业表"""
    __tablename__ = "careers"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # 基本信息
    name = Column(String(100), nullable=False, comment="职业名称")
    type = Column(String(20), nullable=False, comment="职业类型: main(主职业)/sub(副职业)")
    description = Column(Text, comment="职业描述")
    category = Column(String(50), comment="职业分类（如：战斗系、生产系、辅助系）")
    
    # 阶段设定
    stages = Column(Text, nullable=False, comment="职业阶段列表(JSON): [{level:1, name:'', description:''}, ...]")
    max_stage = Column(Integer, nullable=False, default=10, comment="最大阶段数")
    
    # 职业特性
    requirements = Column(Text, comment="职业要求/限制")
    special_abilities = Column(Text, comment="特殊能力描述")
    worldview_rules = Column(Text, comment="世界观规则关联")
    
    # 职业属性加成（可选，JSON格式）
    attribute_bonuses = Column(Text, comment="属性加成(JSON): {strength: '+10%', intelligence: '+5%'}")
    
    # 元数据
    source = Column(String(20), default='ai', comment="来源: ai/manual")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_project_id', 'project_id'),
        Index('idx_type', 'type'),
    )
    
    def __repr__(self):
        return f"<Career(id={self.id}, name={self.name}, type={self.type})>"


class CharacterCareer(Base):
    """角色职业关联表"""
    __tablename__ = "character_careers"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    character_id = Column(String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    career_id = Column(String(36), ForeignKey("careers.id", ondelete="CASCADE"), nullable=False)
    career_type = Column(String(20), nullable=False, comment="main(主职业)/sub(副职业)")
    
    # 阶段进度
    current_stage = Column(Integer, nullable=False, default=1, comment="当前阶段（对应职业中的数值）")
    stage_progress = Column(Integer, default=0, comment="阶段内进度（0-100）")
    
    # 时间记录
    started_at = Column(String(100), comment="开始修炼时间（小说时间线）")
    reached_current_stage_at = Column(String(100), comment="到达当前阶段时间")
    
    # 备注
    notes = Column(Text, comment="备注（如：修炼心得、特殊事件）")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_character_id', 'character_id'),
        Index('idx_career_type', 'career_type'),
        Index('idx_character_career', 'character_id', 'career_id', unique=True),
    )
    
    def __repr__(self):
        return f"<CharacterCareer(character_id={self.character_id}, career_id={self.career_id}, type={self.career_type})>"