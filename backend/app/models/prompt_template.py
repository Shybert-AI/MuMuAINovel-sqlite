"""提示词模板数据模型"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base
import uuid


class PromptTemplate(Base):
    """提示词模板表"""
    __tablename__ = "prompt_templates"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, index=True, comment="用户ID")
    template_key = Column(String(100), nullable=False, comment="模板键名")
    template_name = Column(String(200), nullable=False, comment="模板显示名称")
    template_content = Column(Text, nullable=False, comment="模板内容")
    description = Column(Text, comment="模板描述")
    category = Column(String(50), comment="模板分类")
    parameters = Column(Text, comment="模板参数定义(JSON)")
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_system_default = Column(Boolean, default=False, comment="是否为系统默认模板")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_user_template', 'user_id', 'template_key', unique=True),
    )
    
    def __repr__(self):
        return f"<PromptTemplate(id={self.id}, user_id={self.user_id}, template_key={self.template_key})>"