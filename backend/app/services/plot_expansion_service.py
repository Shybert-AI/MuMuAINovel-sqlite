"""大纲剧情展开服务 - 将大纲节点展开为多个章节"""
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import json

from app.models.outline import Outline
from app.models.project import Project
from app.models.character import Character
from app.models.chapter import Chapter
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service, PromptService
from app.logger import get_logger

logger = get_logger(__name__)


class PlotExpansionService:
    """大纲剧情展开服务"""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
    
    async def analyze_outline_for_chapters(
        self,
        outline: Outline,
        project: Project,
        db: AsyncSession,
        target_chapter_count: int = 3,
        expansion_strategy: str = "balanced",
        enable_scene_analysis: bool = True,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: int = 5,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        分析单个大纲,生成多章节规划（支持分批生成）
        
        Args:
            outline: 大纲对象
            project: 项目对象
            db: 数据库会话
            target_chapter_count: 目标生成章节数
            expansion_strategy: 展开策略(balanced/climax/detail)
            enable_scene_analysis: 是否启用场景级分析
            provider: AI提供商
            model: AI模型
            batch_size: 每批生成的章节数（默认5章）
            progress_callback: 进度回调函数(可选)
            
        Returns:
            章节规划列表
        """
        logger.info(f"开始分析大纲 {outline.id}，目标生成 {target_chapter_count} 章")
        
        # 如果章节数较少，直接生成
        if target_chapter_count <= batch_size:
            return await self._generate_chapters_single_batch(
                outline=outline,
                project=project,
                db=db,
                target_chapter_count=target_chapter_count,
                expansion_strategy=expansion_strategy,
                enable_scene_analysis=enable_scene_analysis,
                provider=provider,
                model=model
            )
        
        # 章节数较多，分批生成
        logger.info(f"章节数({target_chapter_count})超过批次大小({batch_size})，启用分批生成")
        return await self._generate_chapters_in_batches(
            outline=outline,
            project=project,
            db=db,
            target_chapter_count=target_chapter_count,
            expansion_strategy=expansion_strategy,
            enable_scene_analysis=enable_scene_analysis,
            provider=provider,
            model=model,
            batch_size=batch_size,
            progress_callback=progress_callback
        )
    
    async def _generate_chapters_single_batch(
        self,
        outline: Outline,
        project: Project,
        db: AsyncSession,
        target_chapter_count: int,
        expansion_strategy: str,
        enable_scene_analysis: bool,
        provider: Optional[str],
        model: Optional[str]
    ) -> List[Dict[str, Any]]:
        """单批次生成章节规划"""
        # 获取角色信息
        characters_result = await db.execute(
            select(Character).where(Character.project_id == project.id)
        )
        characters = characters_result.scalars().all()
        characters_info = "\n".join([
            f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): "
            f"{char.personality[:100] if char.personality else '暂无描述'}"
            for char in characters
        ])
        
        # 获取大纲上下文（前后大纲）
        context_info = await self._get_outline_context(outline, project.id, db)
        
        # 获取自定义提示词模板
        template = await PromptService.get_template("OUTLINE_EXPAND_SINGLE", project.user_id, db)
        # 格式化提示词
        prompt = PromptService.format_prompt(
            template,
            project_title=project.title,
            project_genre=project.genre or '通用',
            project_theme=project.theme or '未设定',
            project_narrative_perspective=project.narrative_perspective or '第三人称',
            project_world_time_period=project.world_time_period or '未设定',
            project_world_location=project.world_location or '未设定',
            project_world_atmosphere=project.world_atmosphere or '未设定',
            characters_info=characters_info or '暂无角色',
            outline_order_index=outline.order_index,
            outline_title=outline.title,
            outline_content=outline.content,
            context_info=context_info,
            strategy_instruction=expansion_strategy,
            target_chapter_count=target_chapter_count,
            scene_instruction="",  # 暂时为空
            scene_field=""  # 暂时为空
        )
        
        # 调用AI生成章节规划
        logger.info(f"调用AI生成章节规划...")
        accumulated_text = ""
        async for chunk in self.ai_service.generate_text_stream(
            prompt=prompt,
            provider=provider,
            model=model
        ):
            accumulated_text += chunk
        
        # 提取内容
        ai_content = accumulated_text
        
        # 解析AI响应
        chapter_plans = self._parse_expansion_response(ai_content, outline.id)
        
        logger.info(f"成功生成 {len(chapter_plans)} 个章节规划")
        return chapter_plans
    
    async def _generate_chapters_in_batches(
        self,
        outline: Outline,
        project: Project,
        db: AsyncSession,
        target_chapter_count: int,
        expansion_strategy: str,
        enable_scene_analysis: bool,
        provider: Optional[str],
        model: Optional[str],
        batch_size: int,
        progress_callback: Optional[callable]
    ) -> List[Dict[str, Any]]:
        """分批生成章节规划（增强差异化版本）"""
        # 计算批次数
        total_batches = (target_chapter_count + batch_size - 1) // batch_size
        logger.info(f"分批生成计划: 总共{target_chapter_count}章，分{total_batches}批，每批{batch_size}章")
        
        # 获取角色信息（所有批次共用）
        characters_result = await db.execute(
            select(Character).where(Character.project_id == project.id)
        )
        characters = characters_result.scalars().all()
        characters_info = "\n".join([
            f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): "
            f"{char.personality[:100] if char.personality else '暂无描述'}"
            for char in characters
        ])
        
        # 获取大纲上下文
        context_info = await self._get_outline_context(outline, project.id, db)
        
        all_chapter_plans = []
        
        # 🔧 收集所有已使用的关键事件，用于防止重复
        used_key_events = set()
        
        for batch_num in range(total_batches):
            # 计算当前批次的章节数
            remaining_chapters = target_chapter_count - len(all_chapter_plans)
            current_batch_size = min(batch_size, remaining_chapters)
            current_start_index = len(all_chapter_plans) + 1
            
            logger.info(f"开始生成第{batch_num + 1}/{total_batches}批，章节范围: {current_start_index}-{current_start_index + current_batch_size - 1}")
            
            # 回调通知进度
            if progress_callback:
                await progress_callback(batch_num + 1, total_batches, current_start_index, current_batch_size)
            
            # 🔧 增强的上下文构建（包含完整的差异化信息）
            previous_context = ""
            if all_chapter_plans:
                # 构建完整的已生成章节摘要（包含关键事件）
                previous_summaries = []
                for ch in all_chapter_plans:  # 显示所有已生成章节
                    key_events_str = "、".join(ch.get('key_events', [])[:3]) if ch.get('key_events') else "无"
                    previous_summaries.append(
                        f"第{ch['sub_index']}节《{ch['title']}》:\n"
                        f"  - 剧情：{ch.get('plot_summary', '')[:150]}\n"
                        f"  - 关键事件：{key_events_str}\n"
                        f"  - 结尾方式：{ch.get('ending_type', '未知')}"
                    )
                
                # 提取所有已使用的关键事件
                all_used_events = []
                for ch in all_chapter_plans:
                    all_used_events.extend(ch.get('key_events', []))
                used_events_str = "、".join(all_used_events[-20:]) if all_used_events else "暂无"
                
                previous_context = f"""
【🔴 已生成章节完整信息（必须参考以确保差异化）】
{chr(10).join(previous_summaries)}

【🔴 已使用的关键事件（本批次不可重复使用）】
{used_events_str}

【🔴 差异化强制要求】
⚠️ 当前是第{current_start_index}-{current_start_index + current_batch_size - 1}节（共{target_chapter_count}节中的第{batch_num + 1}批）
⚠️ 每个新章节必须有完全不同的：
   1. 开场场景（不同地点/时间/人物状态）
   2. 核心事件（不与已生成章节的关键事件重复）
   3. 结尾悬念（不同类型的钩子）
⚠️ 新章节的key_events不得与上面【已使用的关键事件】中的任何事件相同或相似
"""
            # 获取自定义提示词模板
            template = await PromptService.get_template("OUTLINE_EXPAND_MULTI", project.user_id, db)
            # 格式化提示词
            prompt = PromptService.format_prompt(
                template,
                project_title=project.title,
                project_genre=project.genre or '通用',
                project_theme=project.theme or '未设定',
                project_narrative_perspective=project.narrative_perspective or '第三人称',
                project_world_time_period=project.world_time_period or '未设定',
                project_world_location=project.world_location or '未设定',
                project_world_atmosphere=project.world_atmosphere or '未设定',
                characters_info=characters_info or '暂无角色',
                outline_order_index=outline.order_index,
                outline_title=outline.title,
                outline_content=outline.content,
                context_info=context_info,
                previous_context=previous_context,
                strategy_instruction=expansion_strategy,
                start_index=current_start_index,
                end_index=current_start_index + current_batch_size - 1,
                target_chapter_count=current_batch_size,
                scene_instruction="", # 暂时为空
                scene_field="" # 暂时为空
            )
            
            # 调用AI生成当前批次
            logger.info(f"调用AI生成第{batch_num + 1}批...")
            accumulated_text = ""
            async for chunk in self.ai_service.generate_text_stream(
                prompt=prompt,
                provider=provider,
                model=model
            ):
                accumulated_text += chunk
            
            # 提取内容
            ai_content = accumulated_text
            
            # 解析AI响应
            batch_plans = self._parse_expansion_response(ai_content, outline.id)
            
            # 调整sub_index以保持连续性
            for i, plan in enumerate(batch_plans):
                plan["sub_index"] = current_start_index + i
            
            all_chapter_plans.extend(batch_plans)
            
            logger.info(f"第{batch_num + 1}批生成完成，本批生成{len(batch_plans)}章，累计{len(all_chapter_plans)}章")
        
        logger.info(f"分批生成完成，共生成 {len(all_chapter_plans)} 个章节规划")
        return all_chapter_plans
    
    async def batch_expand_outlines(
        self,
        project_id: str,
        db: AsyncSession,
        ai_service: AIService,
        target_chapters_per_outline: int = 3,
        expansion_strategy: str = "balanced",
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量展开所有大纲为章节
        
        Returns:
            {
                "total_outlines": 总大纲数,
                "total_chapters_planned": 规划的总章节数,
                "expansions": [每个大纲的展开结果]
            }
        """
        logger.info(f"开始批量展开项目 {project_id} 的所有大纲")
        
        # 获取项目
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError(f"项目 {project_id} 不存在")
        
        # 获取所有大纲
        outlines_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == project_id)
            .order_by(Outline.order_index)
        )
        outlines = outlines_result.scalars().all()
        
        if not outlines:
            logger.warning(f"项目 {project_id} 没有大纲")
            return {
                "total_outlines": 0,
                "total_chapters_planned": 0,
                "expansions": []
            }
        
        # 逐个展开大纲
        expansions = []
        total_chapters = 0
        
        for outline in outlines:
            try:
                chapter_plans = await self.analyze_outline_for_chapters(
                    outline=outline,
                    project=project,
                    db=db,
                    target_chapter_count=target_chapters_per_outline,
                    expansion_strategy=expansion_strategy,
                    provider=provider,
                    model=model
                )
                
                expansions.append({
                    "outline_id": outline.id,
                    "outline_title": outline.title,
                    "chapter_plans": chapter_plans,
                    "chapter_count": len(chapter_plans)
                })
                
                total_chapters += len(chapter_plans)
                logger.info(f"大纲 {outline.title} 展开为 {len(chapter_plans)} 章")
                
            except Exception as e:
                logger.error(f"展开大纲 {outline.id} 失败: {str(e)}")
                expansions.append({
                    "outline_id": outline.id,
                    "outline_title": outline.title,
                    "error": str(e),
                    "chapter_count": 0
                })
        
        result = {
            "total_outlines": len(outlines),
            "total_chapters_planned": total_chapters,
            "expansions": expansions
        }
        
        logger.info(f"批量展开完成: {len(outlines)} 个大纲 → {total_chapters} 个章节规划")
        return result
    
    async def create_chapters_from_plans(
        self,
        outline_id: str,
        chapter_plans: List[Dict[str, Any]],
        project_id: str,
        db: AsyncSession,
        start_chapter_number: int = None
    ) -> List[Chapter]:
        """
        根据章节规划创建实际的章节记录
        
        Args:
            outline_id: 大纲ID
            chapter_plans: 章节规划列表
            project_id: 项目ID
            db: 数据库会话
            start_chapter_number: 起始章节号（如果为None，则自动计算）
            
        Returns:
            创建的章节列表
        """
        logger.info(f"根据规划创建 {len(chapter_plans)} 个章节记录")
        
        # 如果没有指定起始章节号，根据大纲顺序自动计算
        if start_chapter_number is None:
            # 1. 获取当前大纲信息
            outline_result = await db.execute(
                select(Outline).where(Outline.id == outline_id)
            )
            current_outline = outline_result.scalar_one_or_none()
            
            if not current_outline:
                raise ValueError(f"大纲 {outline_id} 不存在")
            
            # 2. 查询所有在当前大纲之前的大纲（按order_index排序）
            prev_outlines_result = await db.execute(
                select(Outline)
                .where(
                    Outline.project_id == project_id,
                    Outline.order_index < current_outline.order_index
                )
                .order_by(Outline.order_index)
            )
            prev_outlines = prev_outlines_result.scalars().all()
            
            # 3. 计算前面所有大纲已展开的章节总数
            total_prev_chapters = 0
            for prev_outline in prev_outlines:
                count_result = await db.execute(
                    select(func.count(Chapter.id))
                    .where(
                        Chapter.project_id == project_id,
                        Chapter.outline_id == prev_outline.id
                    )
                )
                total_prev_chapters += count_result.scalar() or 0
            
            # 4. 起始章节号 = 前面所有大纲的章节数 + 1
            start_chapter_number = total_prev_chapters + 1
            logger.info(f"自动计算起始章节号: {start_chapter_number} (基于大纲order_index={current_outline.order_index}, 前置章节数={total_prev_chapters})")
        
        chapters = []
        for idx, plan in enumerate(chapter_plans):
            # 保存完整的展开规划数据（JSON格式）
            expansion_plan_json = json.dumps({
                "key_events": plan.get("key_events", []),
                "character_focus": plan.get("character_focus", []),
                "emotional_tone": plan.get("emotional_tone", ""),
                "narrative_goal": plan.get("narrative_goal", ""),
                "conflict_type": plan.get("conflict_type", ""),
                "estimated_words": plan.get("estimated_words", 3000),
                "scenes": plan.get("scenes", []) if plan.get("scenes") else None
            }, ensure_ascii=False)
            
            chapter = Chapter(
                project_id=project_id,
                outline_id=outline_id,
                chapter_number=start_chapter_number + idx,
                sub_index=plan.get("sub_index", idx + 1),
                title=plan.get("title", f"第{start_chapter_number + idx}章"),
                summary=plan.get("plot_summary", ""),
                expansion_plan=expansion_plan_json,
                status="draft"
            )
            db.add(chapter)
            chapters.append(chapter)
        
        await db.commit()
        
        for chapter in chapters:
            await db.refresh(chapter)
        
        logger.info(f"成功创建 {len(chapters)} 个章节记录（已保存展开规划数据）")
        
        # 重新排序当前大纲之后的所有章节
        await self._renumber_subsequent_chapters(
            project_id=project_id,
            current_outline_id=outline_id,
            db=db
        )
        
        return chapters
    
    async def _get_outline_context(
        self,
        outline: Outline,
        project_id: str,
        db: AsyncSession
    ) -> str:
        """获取大纲的上下文（前后大纲）"""
        # 获取前一个大纲
        prev_result = await db.execute(
            select(Outline)
            .where(
                Outline.project_id == project_id,
                Outline.order_index < outline.order_index
            )
            .order_by(Outline.order_index.desc())
            .limit(1)
        )
        prev_outline = prev_result.scalar_one_or_none()
        
        # 获取后一个大纲
        next_result = await db.execute(
            select(Outline)
            .where(
                Outline.project_id == project_id,
                Outline.order_index > outline.order_index
            )
            .order_by(Outline.order_index)
            .limit(1)
        )
        next_outline = next_result.scalar_one_or_none()
        
        context = ""
        if prev_outline:
            context += f"【前一节】{prev_outline.title}: {prev_outline.content[:200]}...\n\n"
        if next_outline:
            context += f"【后一节】{next_outline.title}: {next_outline.content[:200]}...\n"
        
        return context if context else "（无前后文）"
    
    
    def _parse_expansion_response(
        self,
        ai_response: str,
        outline_id: str
    ) -> List[Dict[str, Any]]:
        """解析AI的展开响应（使用统一的JSON清洗方法，增强差异化字段）"""
        try:
            # 使用统一的JSON清洗方法
            cleaned_text = self.ai_service._clean_json_response(ai_response)
            
            # 解析JSON
            chapter_plans = json.loads(cleaned_text)
            
            # 确保是列表
            if not isinstance(chapter_plans, list):
                chapter_plans = [chapter_plans]
            
            # 为每个章节规划添加outline_id和差异化标识
            for idx, plan in enumerate(chapter_plans):
                plan["outline_id"] = outline_id
                
                # 🔧 确保有 ending_type 字段（用于差异化追踪）
                if "ending_type" not in plan:
                    # 根据叙事目标推断结尾类型
                    narrative_goal = plan.get("narrative_goal", "")
                    if "悬念" in narrative_goal or "疑问" in narrative_goal:
                        plan["ending_type"] = "悬念"
                    elif "冲突" in narrative_goal or "对抗" in narrative_goal:
                        plan["ending_type"] = "冲突升级"
                    elif "转折" in narrative_goal:
                        plan["ending_type"] = "情节转折"
                    elif "情感" in narrative_goal or "情绪" in narrative_goal:
                        plan["ending_type"] = "情感收尾"
                    else:
                        plan["ending_type"] = f"自然过渡-{idx + 1}"
                
                # 🔧 确保 key_events 是列表且非空
                if not plan.get("key_events"):
                    plan["key_events"] = [f"章节{idx + 1}核心事件"]
            
            logger.info(f"✅ 成功解析 {len(chapter_plans)} 个章节规划（含差异化标识）")
            return chapter_plans
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ 解析AI响应失败: {e}, 响应内容: {ai_response[:500]}")
            # 返回一个基础规划
            return [{
                "outline_id": outline_id,
                "sub_index": 1,
                "title": "AI解析失败的默认章节",
                "plot_summary": ai_response[:500],
                "key_events": ["解析失败"],
                "character_focus": [],
                "emotional_tone": "未知",
                "narrative_goal": "需要重新生成",
                "conflict_type": "未知",
                "ending_type": "未知",
                "estimated_words": 3000
            }]
        except Exception as e:
            logger.error(f"❌ 解析异常: {str(e)}")
            return [{
                "outline_id": outline_id,
                "sub_index": 1,
                "title": "解析异常的默认章节",
                "plot_summary": "系统错误",
                "key_events": [],
                "character_focus": [],
                "emotional_tone": "未知",
                "narrative_goal": "需要重新生成",
                "conflict_type": "未知",
                "ending_type": "未知",
                "estimated_words": 3000
            }]


    async def _renumber_subsequent_chapters(
        self,
        project_id: str,
        current_outline_id: str,
        db: AsyncSession
    ):
        """
        重新计算当前大纲之后所有大纲的章节序号
        
        Args:
            project_id: 项目ID
            current_outline_id: 当前大纲ID
            db: 数据库会话
        """
        logger.info(f"开始重新排序大纲 {current_outline_id} 之后的所有章节")
        
        # 1. 获取当前大纲信息
        current_outline_result = await db.execute(
            select(Outline).where(Outline.id == current_outline_id)
        )
        current_outline = current_outline_result.scalar_one_or_none()
        
        if not current_outline:
            logger.warning(f"大纲 {current_outline_id} 不存在，跳过重新排序")
            return
        
        # 2. 获取当前大纲及之后的所有大纲（按order_index排序）
        subsequent_outlines_result = await db.execute(
            select(Outline)
            .where(
                Outline.project_id == project_id,
                Outline.order_index >= current_outline.order_index
            )
            .order_by(Outline.order_index)
        )
        subsequent_outlines = subsequent_outlines_result.scalars().all()
        
        # 3. 计算每个大纲的起始章节号
        current_chapter_number = 1
        
        # 先计算前面大纲的章节总数
        prev_outlines_result = await db.execute(
            select(Outline)
            .where(
                Outline.project_id == project_id,
                Outline.order_index < current_outline.order_index
            )
            .order_by(Outline.order_index)
        )
        prev_outlines = prev_outlines_result.scalars().all()
        
        for prev_outline in prev_outlines:
            count_result = await db.execute(
                select(func.count(Chapter.id))
                .where(
                    Chapter.project_id == project_id,
                    Chapter.outline_id == prev_outline.id
                )
            )
            current_chapter_number += count_result.scalar() or 0
        
        # 4. 逐个大纲更新章节序号
        updated_count = 0
        for outline in subsequent_outlines:
            # 获取该大纲的所有章节（按sub_index排序）
            chapters_result = await db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.outline_id == outline.id
                )
                .order_by(Chapter.sub_index)
            )
            chapters = chapters_result.scalars().all()
            
            # 更新每个章节的chapter_number
            for chapter in chapters:
                if chapter.chapter_number != current_chapter_number:
                    logger.debug(f"更新章节 {chapter.id}: {chapter.chapter_number} -> {current_chapter_number}")
                    chapter.chapter_number = current_chapter_number
                    updated_count += 1
                current_chapter_number += 1
        
        # 5. 提交更新
        await db.commit()
        logger.info(f"重新排序完成，共更新 {updated_count} 个章节的序号")


# 工厂函数
def create_plot_expansion_service(ai_service: AIService) -> PlotExpansionService:
    """创建剧情展开服务实例"""
    return PlotExpansionService(ai_service)