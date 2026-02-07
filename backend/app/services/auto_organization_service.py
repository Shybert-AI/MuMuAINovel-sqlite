"""自动组织引入服务 - 在续写大纲时根据剧情推进自动引入新组织"""
from typing import List, Dict, Any, Optional, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from app.models.character import Character
from app.models.relationship import Organization, OrganizationMember
from app.models.project import Project
from app.services.ai_service import AIService
from app.services.prompt_service import PromptService
from app.logger import get_logger

logger = get_logger(__name__)


class AutoOrganizationService:
    """自动组织引入服务"""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
    
    async def analyze_and_create_organizations(
        self,
        project_id: str,
        outline_content: str,
        existing_characters: List[Character],
        existing_organizations: List[Dict[str, Any]],
        db: AsyncSession,
        user_id: str = None,
        enable_mcp: bool = True,
        all_chapters_brief: str = "",
        start_chapter: int = 1,
        chapter_count: int = 3,
        plot_stage: str = "发展",
        story_direction: str = "继续推进主线剧情",
        preview_only: bool = False,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        预测性分析并创建需要的新组织
        
        Args:
            project_id: 项目ID
            outline_content: 当前批次大纲内容（用于向后兼容，实际不使用）
            existing_characters: 现有角色列表
            existing_organizations: 现有组织列表
            db: 数据库会话
            user_id: 用户ID(用于MCP和自定义提示词)
            enable_mcp: 是否启用MCP增强
            all_chapters_brief: 已有章节概览
            start_chapter: 起始章节号
            chapter_count: 续写章节数
            plot_stage: 剧情阶段
            story_direction: 故事发展方向
            preview_only: 仅预测不创建（用于组织确认机制）
            
        Returns:
            {
                "new_organizations": [组织对象列表],  # preview_only=True时为空
                "members_created": [成员关系列表],  # preview_only=True时为空
                "organization_count": 新增组织数量,
                "analysis_result": AI分析结果,
                "predicted_organizations": [预测的组织数据]  # 仅preview_only=True时返回
                "needs_new_organizations": bool,
                "reason": str
            }
        """
        logger.info(f"🏛️ 【组织引入】预测性分析：检测是否需要引入新组织...")
        logger.info(f"  - 项目ID: {project_id}")
        logger.info(f"  - 续写计划: 第{start_chapter}章起，共{chapter_count}章")
        logger.info(f"  - 剧情阶段: {plot_stage}")
        logger.info(f"  - 发展方向: {story_direction}")
        logger.info(f"  - 现有角色数: {len(existing_characters)}")
        logger.info(f"  - 现有组织数: {len(existing_organizations)}")
        
        # 1. 获取项目信息
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError("项目不存在")
        
        # 2. 构建现有组织信息摘要
        existing_orgs_summary = self._build_organization_summary(existing_organizations)
        existing_chars_summary = self._build_character_summary(existing_characters)
        
        # 3. AI预测性分析是否需要新组织
        if progress_callback:
            await progress_callback("🤖 AI分析组织需求...")
        
        analysis_result = await self._analyze_organization_needs(
            project=project,
            outline_content=outline_content,
            existing_orgs_summary=existing_orgs_summary,
            existing_chars_summary=existing_chars_summary,
            db=db,
            user_id=user_id,
            enable_mcp=enable_mcp,
            all_chapters_brief=all_chapters_brief,
            start_chapter=start_chapter,
            chapter_count=chapter_count,
            plot_stage=plot_stage,
            story_direction=story_direction
        )
        
        if progress_callback:
            await progress_callback("✅ 组织需求分析完成")
        
        # 4. 判断是否需要创建组织
        if not analysis_result or not analysis_result.get("needs_new_organizations"):
            logger.info("✅ AI判断：当前剧情不需要引入新组织")
            return {
                "new_organizations": [],
                "members_created": [],
                "organization_count": 0,
                "analysis_result": analysis_result,
                "predicted_organizations": [],
                "needs_new_organizations": False,
                "reason": analysis_result.get("reason", "当前剧情不需要新组织")
            }
        
        # 5. 如果是预览模式，仅返回预测结果，不创建组织
        if preview_only:
            organization_specs = analysis_result.get("organization_specifications", [])
            logger.info(f"🔮 预览模式：预测到 {len(organization_specs)} 个组织，不创建数据库记录")
            return {
                "new_organizations": [],
                "members_created": [],
                "organization_count": 0,
                "analysis_result": analysis_result,
                "predicted_organizations": organization_specs,
                "needs_new_organizations": True,
                "reason": analysis_result.get("reason", "预测需要新组织")
            }
        
        # 6. 批量生成新组织（非预览模式）
        new_organizations = []
        members_created = []
        
        organization_specs = analysis_result.get("organization_specifications", [])
        logger.info(f"🎯 AI建议引入 {len(organization_specs)} 个新组织")
        
        for idx, spec in enumerate(organization_specs):
            try:
                spec_name = spec.get('name', spec.get('organization_description', '未命名'))
                logger.info(f"  [{idx+1}/{len(organization_specs)}] 生成组织规格: {spec_name}")
                logger.debug(f"     组织规格内容: {json.dumps(spec, ensure_ascii=False)}")
                
                if progress_callback:
                    await progress_callback(f"🏛️ [{idx+1}/{len(organization_specs)}] 生成组织详情: {spec_name}")
                
                # 生成组织详细信息
                organization_data = await self._generate_organization_details(
                    spec=spec,
                    project=project,
                    existing_characters=existing_characters,
                    existing_organizations=existing_organizations,
                    db=db,
                    user_id=user_id,
                    enable_mcp=enable_mcp
                )
                
                logger.debug(f"     AI生成的组织数据: {json.dumps(organization_data, ensure_ascii=False)[:200]}")
                
                if progress_callback:
                    await progress_callback(f"💾 [{idx+1}/{len(organization_specs)}] 保存组织: {organization_data.get('name', spec_name)}")
                
                # 创建组织记录（先创建Character记录，再创建Organization记录）
                character, organization = await self._create_organization_record(
                    project_id=project_id,
                    organization_data=organization_data,
                    db=db
                )
                
                new_organizations.append({
                    "character": character,
                    "organization": organization
                })
                logger.info(f"  ✅ 创建新组织: {character.name}, ID: {organization.id}")
                
                if progress_callback:
                    await progress_callback(f"✅ [{idx+1}/{len(organization_specs)}] 组织创建成功: {character.name}")
                
                # 建立成员关系
                members_data = organization_data.get("initial_members", [])
                if members_data:
                    logger.info(f"  🔗 开始创建 {len(members_data)} 个成员关系...")
                    
                    if progress_callback:
                        await progress_callback(f"🔗 [{idx+1}/{len(organization_specs)}] 建立 {len(members_data)} 个成员关系")
                    
                    members = await self._create_member_relationships(
                        organization=organization,
                        member_specs=members_data,
                        existing_characters=existing_characters,
                        project_id=project_id,
                        db=db
                    )
                    members_created.extend(members)
                    logger.info(f"  ✅ 实际创建了 {len(members)} 个成员关系记录")
                
            except Exception as e:
                logger.error(f"  ❌ 创建组织失败: {e}", exc_info=True)
                continue
        
        # 7. 提交事务（注意：这里只flush，让调用方commit）
        await db.flush()
        
        logger.info(f"🎉 自动组织引入完成: 新增{len(new_organizations)}个组织, {len(members_created)}个成员关系")
        
        return {
            "new_organizations": new_organizations,
            "members_created": members_created,
            "organization_count": len(new_organizations),
            "analysis_result": analysis_result,
            "predicted_organizations": [],
            "needs_new_organizations": True,
            "reason": analysis_result.get("reason", "")
        }
    
    def _build_organization_summary(self, organizations: List[Dict[str, Any]]) -> str:
        """构建现有组织摘要"""
        if not organizations:
            return "暂无组织"
        
        summary = []
        for org in organizations:
            org_name = org.get("name", "未知")
            org_type = org.get("organization_type", "未知类型")
            power_level = org.get("power_level", 50)
            purpose = (org.get("organization_purpose") or "")[:50]
            summary.append(f"- {org_name} ({org_type}, 势力等级:{power_level}): {purpose}")
        
        return "\n".join(summary[:15])  # 最多显示15个
    
    def _build_character_summary(self, characters: List[Character]) -> str:
        """构建现有角色摘要"""
        if not characters:
            return "暂无角色"
        
        summary = []
        for char in characters:
            if not char.is_organization:  # 只统计非组织角色
                char_role = char.role_type or "未知"
                personality = (char.personality or "")[:30]
                summary.append(f"- {char.name} ({char_role}): {personality}")
        
        return "\n".join(summary[:20])  # 最多显示20个
    
    async def _analyze_organization_needs(
        self,
        project: Project,
        outline_content: str,
        existing_orgs_summary: str,
        existing_chars_summary: str,
        db: AsyncSession,
        user_id: str,
        enable_mcp: bool,
        all_chapters_brief: str = "",
        start_chapter: int = 1,
        chapter_count: int = 3,
        plot_stage: str = "发展",
        story_direction: str = "继续推进主线剧情"
    ) -> Dict[str, Any]:
        """AI预测性分析是否需要新组织"""
        
        # 构建分析提示词
        template = await PromptService.get_template(
            "AUTO_ORGANIZATION_ANALYSIS",
            user_id,
            db
        )
        
        # 使用新的预测性分析参数
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=project.theme or "未设定",
            genre=project.genre or "未设定",
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            existing_organizations=existing_orgs_summary,
            existing_characters=existing_chars_summary,
            all_chapters_brief=all_chapters_brief,
            start_chapter=start_chapter,
            chapter_count=chapter_count,
            plot_stage=plot_stage,
            story_direction=story_direction
        )
        
        try:
            # 使用统一的JSON调用方法（支持自动MCP工具加载）
            analysis = await self.ai_service.call_with_json_retry(
                prompt=prompt,
                max_retries=3,
            )
            
            logger.info(f"  ✅ AI分析完成: needs_new_organizations={analysis.get('needs_new_organizations')}")
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ 组织需求分析JSON解析失败: {e}")
            return {"needs_new_organizations": False}
        except Exception as e:
            logger.error(f"  ❌ 组织需求分析失败: {e}")
            return {"needs_new_organizations": False}
    
    async def _generate_organization_details(
        self,
        spec: Dict[str, Any],
        project: Project,
        existing_characters: List[Character],
        existing_organizations: List[Dict[str, Any]],
        db: AsyncSession,
        user_id: str,
        enable_mcp: bool
    ) -> Dict[str, Any]:
        """生成组织详细信息"""
        
        # 构建组织生成提示词
        template = await PromptService.get_template(
            "AUTO_ORGANIZATION_GENERATION",
            user_id,
            db
        )
        
        existing_orgs_summary = self._build_organization_summary(existing_organizations)
        existing_chars_summary = self._build_character_summary(existing_characters)
        
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            genre=project.genre or "未设定",
            theme=project.theme or "未设定",
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            rules=project.world_rules or "未设定",
            existing_organizations=existing_orgs_summary,
            existing_characters=existing_chars_summary,
            plot_context="根据剧情需要引入的新组织",
            organization_specification=json.dumps(spec, ensure_ascii=False, indent=2),
            mcp_references=""  # 暂时不使用MCP增强
        )
        
        # 调用AI生成（使用统一的JSON调用方法）
        try:
            # 使用统一的JSON调用方法（支持自动MCP工具加载）
            organization_data = await self.ai_service.call_with_json_retry(
                prompt=prompt,
                max_retries=3,
            )
            
            org_name = organization_data.get('name', '未知')
            logger.info(f"    ✅ 组织详情生成成功: {org_name}")
            logger.debug(f"       组织数据字段: {list(organization_data.keys())}")
            
            # 确保关键字段存在
            if 'name' not in organization_data or not organization_data['name']:
                logger.warning(f"    ⚠️ AI返回的组织数据缺少name字段，使用规格中的信息")
                organization_data['name'] = spec.get('name', f"新组织{spec.get('organization_description', '')[:10]}")
            
            return organization_data
            
        except Exception as e:
            logger.error(f"    ❌ 生成组织详情失败: {e}")
            raise
    
    async def _create_organization_record(
        self,
        project_id: str,
        organization_data: Dict[str, Any],
        db: AsyncSession
    ) -> tuple:
        """创建组织数据库记录（包括Character和Organization）"""
        
        # 首先创建Character记录（is_organization=True）
        character = Character(
            project_id=project_id,
            name=organization_data.get("name", "未命名组织"),
            is_organization=True,
            role_type=organization_data.get("role_type", "supporting"),
            personality=organization_data.get("personality", ""),  # 组织特性
            background=organization_data.get("background", ""),  # 组织背景
            appearance=organization_data.get("appearance", ""),  # 外在表现
            organization_type=organization_data.get("organization_type"),
            organization_purpose=organization_data.get("organization_purpose"),
            traits=json.dumps(organization_data.get("traits", []), ensure_ascii=False) if organization_data.get("traits") else None
        )
        
        db.add(character)
        await db.flush()
        
        # 然后创建Organization记录
        organization = Organization(
            character_id=character.id,
            project_id=project_id,
            power_level=organization_data.get("power_level", 50),
            member_count=0,
            location=organization_data.get("location"),
            motto=organization_data.get("motto"),
            color=organization_data.get("color")
        )
        
        db.add(organization)
        await db.flush()
        
        logger.info(f"    ✅ 创建组织记录: {character.name}, Organization ID: {organization.id}")
        
        return character, organization
    
    async def _create_member_relationships(
        self,
        organization: Organization,
        member_specs: List[Dict[str, Any]],
        existing_characters: List[Character],
        project_id: str,
        db: AsyncSession
    ) -> List[OrganizationMember]:
        """创建组织成员关系"""
        
        if not member_specs:
            return []
        
        members = []
        
        for member_spec in member_specs:
            try:
                character_name = member_spec.get("character_name")
                if not character_name:
                    continue
                
                # 查找目标角色
                target_char = next(
                    (c for c in existing_characters if c.name == character_name and not c.is_organization),
                    None
                )
                
                if not target_char:
                    logger.warning(f"    ⚠️ 目标角色不存在: {character_name}")
                    continue
                
                # 检查成员关系是否已存在
                existing_member = await db.execute(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == organization.id,
                        OrganizationMember.character_id == target_char.id
                    )
                )
                if existing_member.scalar_one_or_none():
                    logger.debug(f"    ℹ️ 成员关系已存在: {character_name} -> {organization.id}")
                    continue
                
                # 创建成员关系
                member = OrganizationMember(
                    organization_id=organization.id,
                    character_id=target_char.id,
                    position=member_spec.get("position", "成员"),
                    rank=member_spec.get("rank", 0),
                    loyalty=member_spec.get("loyalty", 50),
                    status=member_spec.get("status", "active"),
                    joined_at=member_spec.get("joined_at"),
                    source="auto"  # 标记为自动生成
                )
                
                db.add(member)
                members.append(member)
                
                logger.info(
                    f"    ✅ 创建成员关系: {character_name} -> {organization.id} "
                    f"({member_spec.get('position', '成员')})"
                )
                
            except Exception as e:
                logger.warning(f"    ❌ 创建成员关系失败: {e}")
                continue
        
        # 更新组织成员数量
        if members:
            organization.member_count = (organization.member_count or 0) + len(members)
        
        return members


# 全局实例缓存
_auto_organization_service_instance: Optional[AutoOrganizationService] = None


def get_auto_organization_service(ai_service: AIService) -> AutoOrganizationService:
    """获取自动组织服务实例（单例模式）"""
    global _auto_organization_service_instance
    if _auto_organization_service_instance is None:
        _auto_organization_service_instance = AutoOrganizationService(ai_service)
    return _auto_organization_service_instance