"""项目创建向导流式API - 使用SSE避免超时"""
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, AsyncGenerator
import json
import re

from app.database import get_db
from app.models.project import Project
from app.models.character import Character
from app.models.outline import Outline
from app.models.chapter import Chapter
from app.models.career import Career, CharacterCareer
from app.models.relationship import CharacterRelationship, Organization, OrganizationMember, RelationshipType
from app.models.writing_style import WritingStyle
from app.models.project_default_style import ProjectDefaultStyle
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service, PromptService
from app.services.plot_expansion_service import PlotExpansionService
from app.logger import get_logger
from app.utils.sse_response import SSEResponse, create_sse_response, WizardProgressTracker
from app.api.settings import get_user_ai_service

router = APIRouter(prefix="/wizard-stream", tags=["项目创建向导(流式)"])
logger = get_logger(__name__)


async def world_building_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """世界构建流式生成器 - 支持MCP工具增强"""
    # 标记数据库会话是否已提交
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("世界观")
    
    try:
        # 发送开始消息
        yield await tracker.start()
        
        # 提取参数
        title = data.get("title")
        description = data.get("description")
        theme = data.get("theme")
        genre = data.get("genre")
        narrative_perspective = data.get("narrative_perspective")
        target_words = data.get("target_words")
        chapter_count = data.get("chapter_count")
        character_count = data.get("character_count")
        outline_mode = data.get("outline_mode", "one-to-many")  # 大纲模式，默认一对多
        provider = data.get("provider")
        model = data.get("model")
        enable_mcp = data.get("enable_mcp", True)  # 默认启用MCP
        user_id = data.get("user_id")  # 从中间件注入
        
        if not title or not description or not theme or not genre:
            yield await tracker.error("title、description、theme 和 genre 是必需的参数", 400)
            return
        
        # 获取基础提示词（支持自定义）
        yield await tracker.preparing("准备AI提示词...")
        template = await PromptService.get_template("WORLD_BUILDING", user_id, db)
        base_prompt = PromptService.format_prompt(
            template,
            title=title,
            theme=theme,
            genre=genre or "通用类型",
            description=description or "暂无简介"
        )
        
        # 设置用户信息以启用MCP
        if user_id:
            user_ai_service.user_id = user_id
            user_ai_service.db_session = db
        
        # ===== 流式生成世界观（带重试机制） =====
        MAX_WORLD_RETRIES = 3  # 最多重试3次
        world_retry_count = 0
        world_generation_success = False
        world_data = {}
        estimated_total = 1000
        
        while world_retry_count < MAX_WORLD_RETRIES and not world_generation_success:
            try:
                # 重试时重置生成进度
                if world_retry_count > 0:
                    tracker.reset_generating_progress()
                
                yield await tracker.generating(
                    current_chars=0,
                    estimated_total=estimated_total,
                    retry_count=world_retry_count,
                    max_retries=MAX_WORLD_RETRIES
                )
                
                # 流式生成世界观
                accumulated_text = ""
                chunk_count = 0
                
                async for chunk in user_ai_service.generate_text_stream(
                    prompt=base_prompt,
                    provider=provider,
                    model=model,
                    tool_choice="required",
                ):
                    chunk_count += 1
                    accumulated_text += chunk
                    
                    # 发送内容块
                    yield await tracker.generating_chunk(chunk)
                    
                    # 定期更新进度
                    current_len = len(accumulated_text)
                    if chunk_count % 10 == 0:
                        yield await tracker.generating(
                            current_chars=current_len,
                            estimated_total=estimated_total,
                            retry_count=world_retry_count,
                            max_retries=MAX_WORLD_RETRIES
                        )
                    
                    # 每20个块发送心跳
                    if chunk_count % 20 == 0:
                        yield await tracker.heartbeat()
                
                # 检查是否返回空响应
                if not accumulated_text or not accumulated_text.strip():
                    logger.warning(f"⚠️ AI返回空世界观（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）")
                    world_retry_count += 1
                    if world_retry_count < MAX_WORLD_RETRIES:
                        yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "AI返回为空")
                        continue
                    else:
                        # 达到最大重试次数，使用默认值
                        logger.error("❌ 世界观生成多次返回空响应")
                        world_data = {
                            "time_period": "AI多次返回为空，请稍后重试",
                            "location": "AI多次返回为空，请稍后重试",
                            "atmosphere": "AI多次返回为空，请稍后重试",
                            "rules": "AI多次返回为空，请稍后重试"
                        }
                        world_generation_success = True  # 标记为成功以继续流程
                        break
                
                # 解析结果 - 使用统一的JSON清洗方法
                yield await tracker.parsing("解析世界观数据...")
                
                try:
                    logger.info(f"🔍 开始清洗JSON，原始长度: {len(accumulated_text)}")
                    logger.info(f"   原始内容预览: {accumulated_text[:300]}...")
                    
                    # ✅ 使用 AIService 的统一清洗方法
                    cleaned_text = user_ai_service._clean_json_response(accumulated_text)
                    logger.info(f"✅ JSON清洗完成，清洗后长度: {len(cleaned_text)}")
                    logger.info(f"   清洗后预览: {cleaned_text[:300]}...")
                    
                    world_data = json.loads(cleaned_text)
                    logger.info(f"✅ 世界观JSON解析成功（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）")
                    world_generation_success = True  # 解析成功，标记完成
                            
                except json.JSONDecodeError as e:
                    logger.error(f"❌ 世界构建JSON解析失败（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）: {e}")
                    logger.error(f"   原始内容长度: {len(accumulated_text)}")
                    logger.error(f"   原始内容预览: {accumulated_text[:200]}")
                    world_retry_count += 1
                    if world_retry_count < MAX_WORLD_RETRIES:
                        yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "JSON解析失败")
                        continue
                    else:
                        # 达到最大重试次数，使用默认值
                        world_data = {
                            "time_period": "AI返回格式错误，请重试",
                            "location": "AI返回格式错误，请重试",
                            "atmosphere": "AI返回格式错误，请重试",
                            "rules": "AI返回格式错误，请重试"
                        }
                        world_generation_success = True  # 标记为成功以继续流程
                        
            except Exception as e:
                logger.error(f"❌ 世界构建生成异常（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）: {type(e).__name__}: {e}")
                world_retry_count += 1
                if world_retry_count < MAX_WORLD_RETRIES:
                    yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "生成异常")
                    continue
                else:
                    # 最后一次重试仍失败，抛出异常
                    logger.error(f"   accumulated_text 长度: {len(accumulated_text) if 'accumulated_text' in locals() else 'N/A'}")
                    raise
        
        # 保存到数据库
        yield await tracker.saving("保存世界观到数据库...")
        
        # 确保user_id存在
        if not user_id:
            yield await SSEResponse.send_error("用户ID缺失，无法创建项目", 401)
            return
        
        project = Project(
            user_id=user_id,  # 添加user_id字段
            title=title,
            description=description,
            theme=theme,
            genre=genre,
            world_time_period=world_data.get("time_period"),
            world_location=world_data.get("location"),
            world_atmosphere=world_data.get("atmosphere"),
            world_rules=world_data.get("rules"),
            narrative_perspective=narrative_perspective,
            target_words=target_words,
            chapter_count=chapter_count,
            character_count=character_count,
            outline_mode=outline_mode,  # 设置大纲模式
            wizard_status="incomplete",
            wizard_step=1,
            status="planning"
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        
        # 自动设置默认写作风格为第一个全局预设风格
        try:
            result = await db.execute(
                select(WritingStyle).where(
                    WritingStyle.user_id.is_(None),
                    WritingStyle.order_index == 1
                ).limit(1)
            )
            first_style = result.scalar_one_or_none()
            
            if first_style:
                default_style = ProjectDefaultStyle(
                    project_id=project.id,
                    style_id=first_style.id
                )
                db.add(default_style)
                await db.commit()
                logger.info(f"为项目 {project.id} 自动设置默认风格: {first_style.name}")
            else:
                logger.warning(f"未找到order_index=1的全局预设风格，项目 {project.id} 未设置默认风格")
        except Exception as e:
            logger.warning(f"设置默认写作风格失败: {e}，不影响项目创建")
        
        # 更新向导步骤状态为1（世界观已完成）
        # wizard_step: 0=未开始, 1=世界观已完成, 2=职业体系已完成, 3=角色已完成, 4=大纲已完成
        project.wizard_step = 1
        await db.commit()
        
        # ===== 世界观生成完成 =====
        db_committed = True
        
        yield await tracker.complete()
        
        # 发送世界观结果
        yield await tracker.result({
            "project_id": project.id,
            "time_period": world_data.get("time_period"),
            "location": world_data.get("location"),
            "atmosphere": world_data.get("atmosphere"),
            "rules": world_data.get("rules")
        })
        
        # 发送世界观完成信号
        yield await tracker.done()
        
        logger.info(f"✅ 世界观生成完成，项目ID: {project.id}")
        
    except GeneratorExit:
        # SSE连接断开，回滚未提交的事务
        logger.warning("世界构建生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界构建事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"世界构建流式生成失败: {str(e)}")
        # 异常时回滚事务
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界构建事务已回滚（异常）")
        yield await tracker.error(f"生成失败: {str(e)}")


@router.post("/world-building", summary="流式生成世界构建")
async def generate_world_building_stream(
    request: Request,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成世界构建，避免超时
    前端使用EventSource接收实时进度和结果
    """
    # 从中间件注入user_id到data中
    if hasattr(request.state, 'user_id'):
        data['user_id'] = request.state.user_id
    
    return create_sse_response(world_building_generator(data, db, user_ai_service))


async def career_system_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """职业体系生成流式生成器 - 独立接口"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("职业体系")
    
    try:
        yield await tracker.start()
        
        # 提取参数
        project_id = data.get("project_id")
        provider = data.get("provider")
        model = data.get("model")
        user_id = data.get("user_id")
        
        if not project_id:
            yield await tracker.error("project_id 是必需的参数", 400)
            return
        
        # 获取项目信息
        yield await tracker.loading("加载项目信息...")
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        # 设置用户信息以启用MCP
        if user_id:
            user_ai_service.user_id = user_id
            user_ai_service.db_session = db
        
        # 获取世界观数据
        world_data = {
            "time_period": project.world_time_period or "未设定",
            "location": project.world_location or "未设定",
            "atmosphere": project.world_atmosphere or "未设定",
            "rules": project.world_rules or "未设定"
        }
        
        # 获取职业生成提示词模板（支持用户自定义）
        yield await tracker.preparing("准备AI提示词...")
        template = await PromptService.get_template("CAREER_SYSTEM_GENERATION", user_id, db)
        career_prompt = PromptService.format_prompt(
            template,
            title=project.title,
            genre=project.genre or '未设定',
            theme=project.theme or '未设定',
            time_period=world_data.get('time_period', '未设定'),
            location=world_data.get('location', '未设定'),
            atmosphere=world_data.get('atmosphere', '未设定'),
            rules=world_data.get('rules', '未设定')
        )
        
        estimated_total = 5000
        MAX_CAREER_RETRIES = 3  # 最多重试3次
        career_retry_count = 0
        career_generation_success = False
        
        while career_retry_count < MAX_CAREER_RETRIES and not career_generation_success:
            try:
                # 重试时重置生成进度
                if career_retry_count > 0:
                    tracker.reset_generating_progress()
                
                yield await tracker.generating(
                    current_chars=0,
                    estimated_total=estimated_total,
                    retry_count=career_retry_count,
                    max_retries=MAX_CAREER_RETRIES
                )
                
                # 使用流式生成职业体系
                career_response = ""
                chunk_count = 0
                
                async for chunk in user_ai_service.generate_text_stream(
                    prompt=career_prompt,
                    provider=provider,
                    model=model,
                ):
                    chunk_count += 1
                    career_response += chunk
                    
                    # 发送内容块
                    yield await tracker.generating_chunk(chunk)
                    
                    # 定期更新进度
                    current_len = len(career_response)
                    if chunk_count % 10 == 0:
                        yield await tracker.generating(
                            current_chars=current_len,
                            estimated_total=estimated_total,
                            retry_count=career_retry_count,
                            max_retries=MAX_CAREER_RETRIES
                        )
                    
                    # 每20个块发送心跳
                    if chunk_count % 20 == 0:
                        yield await tracker.heartbeat()
                
                if not career_response or not career_response.strip():
                    logger.warning(f"⚠️ AI返回空职业体系（尝试{career_retry_count+1}/{MAX_CAREER_RETRIES}）")
                    career_retry_count += 1
                    if career_retry_count < MAX_CAREER_RETRIES:
                        yield await tracker.retry(career_retry_count, MAX_CAREER_RETRIES, "AI返回为空")
                        continue
                    else:
                        yield await tracker.error("职业体系生成失败（AI多次返回为空）")
                        return
                
                yield await tracker.parsing("解析职业体系数据...")
                
                # 清洗并解析JSON
                try:
                    cleaned_response = user_ai_service._clean_json_response(career_response)
                    career_data = json.loads(cleaned_response)
                    logger.info(f"✅ 职业体系JSON解析成功（尝试{career_retry_count+1}/{MAX_CAREER_RETRIES}）")
                    
                    yield await tracker.saving("保存职业数据...")
                    
                    # 保存主职业
                    main_careers_created = []
                    for idx, career_info in enumerate(career_data.get("main_careers", [])):
                        try:
                            stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                            attribute_bonuses = career_info.get("attribute_bonuses")
                            attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                            
                            career = Career(
                                project_id=project.id,
                                name=career_info.get("name", f"未命名主职业{idx+1}"),
                                type="main",
                                description=career_info.get("description"),
                                category=career_info.get("category"),
                                stages=stages_json,
                                max_stage=career_info.get("max_stage", 10),
                                requirements=career_info.get("requirements"),
                                special_abilities=career_info.get("special_abilities"),
                                worldview_rules=career_info.get("worldview_rules"),
                                attribute_bonuses=attribute_bonuses_json,
                                source="ai"
                            )
                            db.add(career)
                            await db.flush()
                            main_careers_created.append(career.name)
                            logger.info(f"  ✅ 创建主职业：{career.name}")
                        except Exception as e:
                            logger.error(f"  ❌ 创建主职业失败：{str(e)}")
                            continue
                    
                    # 保存副职业
                    sub_careers_created = []
                    for idx, career_info in enumerate(career_data.get("sub_careers", [])):
                        try:
                            stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                            attribute_bonuses = career_info.get("attribute_bonuses")
                            attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                            
                            career = Career(
                                project_id=project.id,
                                name=career_info.get("name", f"未命名副职业{idx+1}"),
                                type="sub",
                                description=career_info.get("description"),
                                category=career_info.get("category"),
                                stages=stages_json,
                                max_stage=career_info.get("max_stage", 5),
                                requirements=career_info.get("requirements"),
                                special_abilities=career_info.get("special_abilities"),
                                worldview_rules=career_info.get("worldview_rules"),
                                attribute_bonuses=attribute_bonuses_json,
                                source="ai"
                            )
                            db.add(career)
                            await db.flush()
                            sub_careers_created.append(career.name)
                            logger.info(f"  ✅ 创建副职业：{career.name}")
                        except Exception as e:
                            logger.error(f"  ❌ 创建副职业失败：{str(e)}")
                            continue
                    
                    # 更新向导步骤状态为2（职业体系已完成）
                    # wizard_step: 0=未开始, 1=世界观已完成, 2=职业体系已完成, 3=角色已完成, 4=大纲已完成
                    project.wizard_step = 2
                    
                    await db.commit()
                    db_committed = True
                    
                    # 标记成功
                    career_generation_success = True
                    logger.info(f"🎉 职业体系生成完成：主职业{len(main_careers_created)}个，副职业{len(sub_careers_created)}个")
                    
                    yield await tracker.complete()
                    
                    # 发送结果
                    yield await tracker.result({
                        "project_id": project.id,
                        "main_careers_count": len(main_careers_created),
                        "sub_careers_count": len(sub_careers_created),
                        "main_careers": main_careers_created,
                        "sub_careers": sub_careers_created
                    })
                    
                    yield await tracker.done()
                    
                except json.JSONDecodeError as e:
                    logger.error(f"❌ 职业体系JSON解析失败（尝试{career_retry_count+1}/{MAX_CAREER_RETRIES}）: {e}")
                    career_retry_count += 1
                    if career_retry_count < MAX_CAREER_RETRIES:
                        yield await tracker.retry(career_retry_count, MAX_CAREER_RETRIES, "JSON解析失败")
                        continue
                    else:
                        yield await tracker.error("职业体系解析失败（已达最大重试次数）")
                        return
                except Exception as e:
                    logger.error(f"❌ 职业体系保存失败（尝试{career_retry_count+1}/{MAX_CAREER_RETRIES}）: {e}")
                    career_retry_count += 1
                    if career_retry_count < MAX_CAREER_RETRIES:
                        yield await tracker.retry(career_retry_count, MAX_CAREER_RETRIES, "保存失败")
                        continue
                    else:
                        yield await tracker.error("职业体系保存失败（已达最大重试次数）")
                        return
            
            except Exception as e:
                logger.error(f"❌ 职业体系生成异常（尝试{career_retry_count+1}/{MAX_CAREER_RETRIES}）: {e}")
                career_retry_count += 1
                if career_retry_count < MAX_CAREER_RETRIES:
                    yield await tracker.retry(career_retry_count, MAX_CAREER_RETRIES, "生成异常")
                    continue
                else:
                    yield await tracker.error(f"职业体系生成失败: {str(e)}")
                    return
        
    except GeneratorExit:
        logger.warning("职业体系生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("职业体系事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"职业体系流式生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("职业体系事务已回滚（异常）")
        yield await tracker.error(f"生成失败: {str(e)}")


@router.post("/career-system", summary="流式生成职业体系")
async def generate_career_system_stream(
    request: Request,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成职业体系，避免超时
    前端使用EventSource接收实时进度和结果
    """
    # 从中间件注入user_id到data中
    if hasattr(request.state, 'user_id'):
        data['user_id'] = request.state.user_id
    
    return create_sse_response(career_system_generator(data, db, user_ai_service))


async def characters_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """角色批量生成流式生成器 - 优化版:分批+重试+MCP工具增强"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("角色")
    
    try:
        yield await tracker.start()
        
        project_id = data.get("project_id")
        count = data.get("count", 5)
        world_context = data.get("world_context")
        theme = data.get("theme", "")
        genre = data.get("genre", "")
        requirements = data.get("requirements", "")
        provider = data.get("provider")
        model = data.get("model")
        enable_mcp = data.get("enable_mcp", True)  # 默认启用MCP
        user_id = data.get("user_id")  # 从中间件注入
        
        # 验证项目
        yield await tracker.loading("验证项目...", 0.3)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        project.wizard_step = 2
        
        world_context = world_context or {
            "time_period": project.world_time_period or "未设定",
            "location": project.world_location or "未设定",
            "atmosphere": project.world_atmosphere or "未设定",
            "rules": project.world_rules or "未设定"
        }
        
        # 设置用户信息以启用MCP
        if user_id:
            user_ai_service.user_id = user_id
            user_ai_service.db_session = db
        
        # 获取项目的职业列表，用于角色职业分配
        yield await tracker.loading("加载职业体系...", 0.8)
        career_result = await db.execute(
            select(Career).where(Career.project_id == project_id).order_by(Career.type, Career.id)
        )
        careers = career_result.scalars().all()
        
        main_careers = [c for c in careers if c.type == "main"]
        sub_careers = [c for c in careers if c.type == "sub"]
        
        # 构建职业上下文
        careers_context = ""
        if main_careers or sub_careers:
            careers_context = "\n\n【职业体系】\n"
            if main_careers:
                careers_context += "主职业：\n"
                for career in main_careers:
                    careers_context += f"- {career.name}: {career.description or '暂无描述'}\n"
            if sub_careers:
                careers_context += "\n副职业：\n"
                for career in sub_careers:
                    careers_context += f"- {career.name}: {career.description or '暂无描述'}\n"
            
            careers_context += "\n请为每个角色分配职业：\n"
            careers_context += "- 每个角色必须有1个主职业（从上述主职业中选择）\n"
            careers_context += "- 每个角色可以有0-2个副职业（从上述副职业中选择，可选）\n"
            careers_context += "- 主职业初始阶段建议为1-3\n"
            careers_context += "- 副职业初始阶段建议为1-2\n"
            careers_context += "- 请在返回的JSON中包含 career_assignment 字段：\n"
            careers_context += '  {"main_career": "职业名称", "main_stage": 2, "sub_careers": [{"career": "副职业名称", "stage": 1}]}\n'
            logger.info(f"✅ 加载了{len(main_careers)}个主职业和{len(sub_careers)}个副职业")
        else:
            logger.warning("⚠️ 项目没有职业体系，跳过职业分配")
        
        # 优化的分批策略:每批生成5个,平衡效率和成功率
        BATCH_SIZE = 5  # 每批生成5个角色
        MAX_RETRIES = 3  # 每批最多重试3次
        all_characters = []
        total_batches = (count + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(total_batches):
            # 精确计算当前批次应该生成的数量
            remaining = count - len(all_characters)
            current_batch_size = min(BATCH_SIZE, remaining)
            
            # 如果已经达到目标数量,直接退出
            if current_batch_size <= 0:
                logger.info(f"已生成{len(all_characters)}个角色,达到目标数量{count}")
                break
            
            batch_progress = 15 + (batch_idx * 60 // total_batches)
            
            # 重试逻辑
            retry_count = 0
            batch_success = False
            batch_error_message = ""
            
            while retry_count < MAX_RETRIES and not batch_success:
                try:
                    # 重试时重置生成进度
                    if retry_count > 0:
                        tracker.reset_generating_progress()
                    
                    yield await tracker.generating(
                        current_chars=0,
                        estimated_total=BATCH_SIZE * 800,
                        message=f"生成第{batch_idx+1}/{total_batches}批角色 ({current_batch_size}个)",
                        retry_count=retry_count,
                        max_retries=MAX_RETRIES
                    )
                    
                    # 构建批次要求 - 包含已生成角色信息保持连贯
                    existing_chars_context = ""
                    if all_characters:
                        existing_chars_context = "\n\n【已生成的角色】:\n"
                        for char in all_characters:
                            existing_chars_context += f"- {char.get('name')}: {char.get('role_type', '未知')}, {char.get('personality', '暂无')[:50]}...\n"
                        existing_chars_context += "\n请确保新角色与已有角色形成合理的关系网络和互动。\n"
                    
                    # 构建精确的批次要求,明确告诉AI要生成的数量
                    if batch_idx == 0:
                        if current_batch_size == 1:
                            batch_requirements = f"{requirements}\n请生成1个主角(protagonist)"
                        else:
                            batch_requirements = f"{requirements}\n请精确生成{current_batch_size}个角色:1个主角(protagonist)和{current_batch_size-1}个核心配角(supporting)"
                    else:
                        batch_requirements = f"{requirements}\n请精确生成{current_batch_size}个角色{existing_chars_context}"
                        if batch_idx == total_batches - 1:
                            batch_requirements += "\n可以包含组织或反派(antagonist)"
                        else:
                            batch_requirements += "\n主要是配角(supporting)和反派(antagonist)"
                    
                    # 获取自定义提示词模板
                    template = await PromptService.get_template("CHARACTERS_BATCH_GENERATION", user_id, db)
                    # 构建基础提示词
                    base_prompt = PromptService.format_prompt(
                        template,
                        count=current_batch_size,  # 传递精确数量
                        time_period=world_context.get("time_period", ""),
                        location=world_context.get("location", ""),
                        atmosphere=world_context.get("atmosphere", ""),
                        rules=world_context.get("rules", ""),
                        theme=theme or project.theme or "",
                        genre=genre or project.genre or "",
                        requirements=batch_requirements + careers_context  # 添加职业上下文
                    )
                    
                    prompt = base_prompt
                    
                    # 流式生成（带字数统计）
                    accumulated_text = ""
                    chunk_count = 0
                    
                    estimated_total = BATCH_SIZE * 800
                    
                    async for chunk in user_ai_service.generate_text_stream(
                        prompt=prompt,
                        provider=provider,
                        model=model,
                        tool_choice="required",
                    ):
                        chunk_count += 1
                        accumulated_text += chunk
                        
                        # 发送内容块
                        yield await tracker.generating_chunk(chunk)
                        
                        # 定期更新进度
                        current_len = len(accumulated_text)
                        if chunk_count % 10 == 0:
                            yield await tracker.generating(
                                current_chars=current_len,
                                estimated_total=estimated_total,
                                message=f"生成第{batch_idx+1}/{total_batches}批角色中",
                                retry_count=retry_count,
                                max_retries=MAX_RETRIES
                            )
                        
                        # 每20个块发送心跳
                        if chunk_count % 20 == 0:
                            yield await tracker.heartbeat()
                    
                    # 解析批次结果 - 使用统一的JSON清洗方法
                    cleaned_text = user_ai_service._clean_json_response(accumulated_text)
                    characters_data = json.loads(cleaned_text)
                    if not isinstance(characters_data, list):
                        characters_data = [characters_data]
                    
                    # 严格验证生成数量是否精确匹配
                    if len(characters_data) != current_batch_size:
                        error_msg = f"批次{batch_idx+1}生成数量不正确: 期望{current_batch_size}个, 实际{len(characters_data)}个"
                        logger.error(error_msg)
                        
                        # 如果还有重试机会，继续重试
                        if retry_count < MAX_RETRIES - 1:
                            retry_count += 1
                            yield await tracker.retry(retry_count, MAX_RETRIES, error_msg)
                            continue
                        else:
                            # 最后一次重试仍失败，直接返回错误
                            yield await tracker.error(error_msg)
                            return
                    
                    all_characters.extend(characters_data)
                    batch_success = True
                    logger.info(f"批次{batch_idx+1}成功添加{len(characters_data)}个角色,当前总数{len(all_characters)}/{count}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"批次{batch_idx+1}解析失败(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    batch_error_message = f"JSON解析失败: {str(e)}"
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await tracker.retry(retry_count, MAX_RETRIES, "JSON解析失败")
                except Exception as e:
                    logger.error(f"批次{batch_idx+1}生成异常(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    batch_error_message = f"生成异常: {str(e)}"
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await tracker.retry(retry_count, MAX_RETRIES, "生成异常")
            
            # 检查批次是否成功
            if not batch_success:
                error_msg = f"批次{batch_idx+1}在{MAX_RETRIES}次重试后仍然失败"
                if batch_error_message:
                    error_msg += f": {batch_error_message}"
                logger.error(error_msg)
                yield await tracker.error(error_msg)
                return
        
        # 保存到数据库 - 分阶段处理以保证一致性
        yield await tracker.parsing("验证角色数据...")
        
        # 预处理：构建本批次所有实体的名称集合
        valid_entity_names = set()
        valid_organization_names = set()
        
        for char_data in all_characters:
            entity_name = char_data.get("name", "")
            if entity_name:
                valid_entity_names.add(entity_name)
                if char_data.get("is_organization", False):
                    valid_organization_names.add(entity_name)
        
        # 清理幻觉引用
        cleaned_count = 0
        for char_data in all_characters:
            # 清理关系数组中的无效引用
            if "relationships_array" in char_data and isinstance(char_data["relationships_array"], list):
                original_rels = char_data["relationships_array"]
                valid_rels = []
                for rel in original_rels:
                    target_name = rel.get("target_character_name", "")
                    if target_name in valid_entity_names:
                        valid_rels.append(rel)
                    else:
                        cleaned_count += 1
                        logger.debug(f"  🧹 清理无效关系引用：{char_data.get('name')} -> {target_name}")
                char_data["relationships_array"] = valid_rels
            
            # 清理组织成员关系中的无效引用
            if "organization_memberships" in char_data and isinstance(char_data["organization_memberships"], list):
                original_orgs = char_data["organization_memberships"]
                valid_orgs = []
                for org_mem in original_orgs:
                    org_name = org_mem.get("organization_name", "")
                    if org_name in valid_organization_names:
                        valid_orgs.append(org_mem)
                    else:
                        cleaned_count += 1
                        logger.debug(f"  🧹 清理无效组织引用：{char_data.get('name')} -> {org_name}")
                char_data["organization_memberships"] = valid_orgs
        
        if cleaned_count > 0:
            logger.info(f"✨ 清理了{cleaned_count}个AI幻觉引用")
            yield await tracker.parsing(f"已清理{cleaned_count}个无效引用", 0.7)
        
        yield await tracker.saving("保存角色到数据库...")
        
        # 第一阶段：创建所有Character记录
        created_characters = []
        character_name_to_obj = {}  # 名称到对象的映射，用于后续关系创建
        
        for char_data in all_characters:
            # 从relationships_array提取文本描述以保持向后兼容
            relationships_text = ""
            relationships_array = char_data.get("relationships_array", [])
            if relationships_array and isinstance(relationships_array, list):
                # 将关系数组转换为可读文本
                rel_descriptions = []
                for rel in relationships_array:
                    target = rel.get("target_character_name", "未知")
                    rel_type = rel.get("relationship_type", "关系")
                    desc = rel.get("description", "")
                    rel_descriptions.append(f"{target}({rel_type}): {desc}")
                relationships_text = "; ".join(rel_descriptions)
            # 兼容旧格式
            elif isinstance(char_data.get("relationships"), dict):
                relationships_text = json.dumps(char_data.get("relationships"), ensure_ascii=False)
            elif isinstance(char_data.get("relationships"), str):
                relationships_text = char_data.get("relationships")
            
            # 判断是否为组织
            is_organization = char_data.get("is_organization", False)
            
            character = Character(
                project_id=project_id,
                name=char_data.get("name", "未命名角色"),
                age=str(char_data.get("age", "")) if not is_organization else None,
                gender=char_data.get("gender") if not is_organization else None,
                is_organization=is_organization,
                role_type=char_data.get("role_type", "supporting"),
                personality=char_data.get("personality", ""),
                background=char_data.get("background", ""),
                appearance=char_data.get("appearance", ""),
                relationships=relationships_text,
                organization_type=char_data.get("organization_type") if is_organization else None,
                organization_purpose=char_data.get("organization_purpose") if is_organization else None,
                organization_members=json.dumps(char_data.get("organization_members", []), ensure_ascii=False) if is_organization else None,
                traits=json.dumps(char_data.get("traits", []), ensure_ascii=False) if char_data.get("traits") else None
            )
            db.add(character)
            created_characters.append((character, char_data))
        
        await db.flush()  # 获取所有角色的ID
        
        # 第二阶段：为角色分配职业并创建CharacterCareer关联
        if main_careers or sub_careers:
            yield await tracker.saving("分配角色职业...", 0.3)
            careers_assigned = 0
            
            # 构建职业名称到对象的映射
            career_name_to_obj = {c.name: c for c in careers}
            
            for character, char_data in created_characters:
                # 跳过组织
                if character.is_organization:
                    continue
                
                try:
                    career_assignment = char_data.get("career_assignment", {})
                    
                    # 分配主职业
                    main_career_name = career_assignment.get("main_career")
                    main_career_stage = career_assignment.get("main_stage", 1)
                    
                    if main_career_name and main_career_name in career_name_to_obj:
                        main_career = career_name_to_obj[main_career_name]
                        
                        # 创建CharacterCareer关联
                        char_career = CharacterCareer(
                            character_id=character.id,
                            career_id=main_career.id,
                            career_type="main",
                            current_stage=min(main_career_stage, main_career.max_stage),
                            stage_progress=0
                        )
                        db.add(char_career)
                        
                        # 更新Character冗余字段
                        character.main_career_id = main_career.id
                        character.main_career_stage = char_career.current_stage
                        
                        careers_assigned += 1
                        logger.info(f"  ✅ 分配主职业：{character.name} -> {main_career.name} (阶段{char_career.current_stage})")
                    else:
                        if main_career_name:
                            logger.warning(f"  ⚠️ 主职业不存在：{character.name} -> {main_career_name}")
                    
                    # 分配副职业
                    sub_career_assignments = career_assignment.get("sub_careers", [])
                    sub_career_list = []
                    
                    for sub_assign in sub_career_assignments[:2]:  # 最多2个副职业
                        sub_career_name = sub_assign.get("career")
                        sub_career_stage = sub_assign.get("stage", 1)
                        
                        if sub_career_name and sub_career_name in career_name_to_obj:
                            sub_career = career_name_to_obj[sub_career_name]
                            
                            # 创建CharacterCareer关联
                            char_career = CharacterCareer(
                                character_id=character.id,
                                career_id=sub_career.id,
                                career_type="sub",
                                current_stage=min(sub_career_stage, sub_career.max_stage),
                                stage_progress=0
                            )
                            db.add(char_career)
                            
                            # 添加到副职业列表
                            sub_career_list.append({
                                "career_id": sub_career.id,
                                "stage": char_career.current_stage
                            })
                            
                            careers_assigned += 1
                            logger.info(f"  ✅ 分配副职业：{character.name} -> {sub_career.name} (阶段{char_career.current_stage})")
                        else:
                            if sub_career_name:
                                logger.warning(f"  ⚠️ 副职业不存在：{character.name} -> {sub_career_name}")
                    
                    # 更新Character冗余字段
                    if sub_career_list:
                        character.sub_careers = json.dumps(sub_career_list, ensure_ascii=False)
                    
                except Exception as e:
                    logger.warning(f"  ❌ 分配职业失败：{character.name} - {str(e)}")
                    continue
            
            await db.flush()
            logger.info(f"💼 职业分配完成：共分配{careers_assigned}个职业")
            yield await tracker.saving(f"已分配{careers_assigned}个职业", 0.4)
        
        # 刷新并建立名称映射
        for character, _ in created_characters:
            await db.refresh(character)
            character_name_to_obj[character.name] = character
            logger.info(f"向导创建角色：{character.name} (ID: {character.id}, 是否组织: {character.is_organization})")
        
        # 第三阶段：为is_organization=True的角色创建Organization记录
        yield await tracker.saving("创建组织记录...", 0.5)
        organization_name_to_obj = {}  # 组织名称到Organization对象的映射
        
        for character, char_data in created_characters:
            if character.is_organization:
                # 检查是否已存在Organization记录
                org_check = await db.execute(
                    select(Organization).where(Organization.character_id == character.id)
                )
                existing_org = org_check.scalar_one_or_none()
                
                if not existing_org:
                    # 创建Organization记录
                    org = Organization(
                        character_id=character.id,
                        project_id=project_id,
                        member_count=0,  # 初始为0，后续添加成员时会更新
                        power_level=char_data.get("power_level", 50),
                        location=char_data.get("location"),
                        motto=char_data.get("motto"),
                        color=char_data.get("color")
                    )
                    db.add(org)
                    logger.info(f"向导创建组织记录：{character.name}")
                else:
                    org = existing_org
                
                # 建立组织名称映射（无论是新建还是已存在）
                organization_name_to_obj[character.name] = org
        
        await db.flush()  # 确保Organization记录有ID
        
        # 刷新角色以获取ID
        for character, _ in created_characters:
            await db.refresh(character)
        
        # 第四阶段：创建角色间的关系
        yield await tracker.saving("创建角色关系...", 0.7)
        relationships_created = 0
        
        for character, char_data in created_characters:
            # 跳过组织实体的角色关系处理（组织通过成员关系关联）
            if character.is_organization:
                continue
            
            # 处理relationships数组
            relationships_data = char_data.get("relationships_array", [])
            if not relationships_data and isinstance(char_data.get("relationships"), list):
                relationships_data = char_data.get("relationships")
            
            if relationships_data and isinstance(relationships_data, list):
                for rel in relationships_data:
                    try:
                        target_name = rel.get("target_character_name")
                        if not target_name:
                            logger.debug(f"  ⚠️  {character.name}的关系缺少target_character_name，跳过")
                            continue
                        
                        # 使用名称映射快速查找
                        target_char = character_name_to_obj.get(target_name)
                        
                        if target_char:
                            # 避免创建重复关系
                            existing_rel = await db.execute(
                                select(CharacterRelationship).where(
                                    CharacterRelationship.project_id == project_id,
                                    CharacterRelationship.character_from_id == character.id,
                                    CharacterRelationship.character_to_id == target_char.id
                                )
                            )
                            if existing_rel.scalar_one_or_none():
                                logger.debug(f"  ℹ️  关系已存在：{character.name} -> {target_name}")
                                continue
                            
                            relationship = CharacterRelationship(
                                project_id=project_id,
                                character_from_id=character.id,
                                character_to_id=target_char.id,
                                relationship_name=rel.get("relationship_type", "未知关系"),
                                intimacy_level=rel.get("intimacy_level", 50),
                                description=rel.get("description", ""),
                                started_at=rel.get("started_at"),
                                source="ai"
                            )
                            
                            # 匹配预定义关系类型
                            rel_type_result = await db.execute(
                                select(RelationshipType).where(
                                    RelationshipType.name == rel.get("relationship_type")
                                )
                            )
                            rel_type = rel_type_result.scalar_one_or_none()
                            if rel_type:
                                relationship.relationship_type_id = rel_type.id
                            
                            db.add(relationship)
                            relationships_created += 1
                            logger.info(f"  ✅ 向导创建关系：{character.name} -> {target_name} ({rel.get('relationship_type')})")
                        else:
                            logger.warning(f"  ⚠️  目标角色不存在：{character.name} -> {target_name}（可能是AI幻觉）")
                    except Exception as e:
                        logger.warning(f"  ❌ 向导创建关系失败：{character.name} - {str(e)}")
                        continue
            
        # 第五阶段：创建组织成员关系
        yield await tracker.saving("创建组织成员关系...", 0.9)
        members_created = 0
        
        for character, char_data in created_characters:
            # 跳过组织实体本身
            if character.is_organization:
                continue
            
            # 处理组织成员关系
            org_memberships = char_data.get("organization_memberships", [])
            if org_memberships and isinstance(org_memberships, list):
                for membership in org_memberships:
                    try:
                        org_name = membership.get("organization_name")
                        if not org_name:
                            logger.debug(f"  ⚠️  {character.name}的组织成员关系缺少organization_name，跳过")
                            continue
                        
                        # 使用映射快速查找组织
                        org = organization_name_to_obj.get(org_name)
                        
                        if org:
                            # 检查是否已存在成员关系
                            existing_member = await db.execute(
                                select(OrganizationMember).where(
                                    OrganizationMember.organization_id == org.id,
                                    OrganizationMember.character_id == character.id
                                )
                            )
                            if existing_member.scalar_one_or_none():
                                logger.debug(f"  ℹ️  成员关系已存在：{character.name} -> {org_name}")
                                continue
                            
                            # 创建成员关系
                            member = OrganizationMember(
                                organization_id=org.id,
                                character_id=character.id,
                                position=membership.get("position", "成员"),
                                rank=membership.get("rank", 0),
                                loyalty=membership.get("loyalty", 50),
                                joined_at=membership.get("joined_at"),
                                status=membership.get("status", "active"),
                                source="ai"
                            )
                            db.add(member)
                            
                            # 更新组织成员计数
                            org.member_count += 1
                            
                            members_created += 1
                            logger.info(f"  ✅ 向导添加成员：{character.name} -> {org_name} ({membership.get('position')})")
                        else:
                            # 这种情况理论上已经被预处理清理了，但保留日志以防万一
                            logger.debug(f"  ℹ️  组织引用已被清理：{character.name} -> {org_name}")
                    except Exception as e:
                        logger.warning(f"  ❌ 向导添加组织成员失败：{character.name} - {str(e)}")
                        continue
        
        logger.info(f"📊 向导数据统计：")
        logger.info(f"  - 创建角色/组织：{len(created_characters)} 个")
        logger.info(f"  - 创建组织详情：{len(organization_name_to_obj)} 个")
        logger.info(f"  - 创建角色关系：{relationships_created} 条")
        logger.info(f"  - 创建组织成员：{members_created} 条")
        
        # 更新项目的角色数量和向导步骤状态为3（角色已完成）
        # wizard_step: 0=未开始, 1=世界观已完成, 2=职业体系已完成, 3=角色已完成, 4=大纲已完成
        project.character_count = len(created_characters)
        project.wizard_step = 3
        logger.info(f"✅ 更新项目角色数量: {project.character_count}")
        
        await db.commit()
        db_committed = True
        
        # 重新提取character对象
        created_characters = [char for char, _ in created_characters]
        
        yield await tracker.complete()
        
        # 发送结果
        yield await tracker.result({
            "message": f"成功生成{len(created_characters)}个角色/组织（分{total_batches}批完成）",
            "count": len(created_characters),
            "batches": total_batches,
            "characters": [
                {
                    "id": char.id,
                    "project_id": char.project_id,
                    "name": char.name,
                    "age": char.age,
                    "gender": char.gender,
                    "is_organization": char.is_organization,
                    "role_type": char.role_type,
                    "personality": char.personality,
                    "background": char.background,
                    "appearance": char.appearance,
                    "relationships": char.relationships,
                    "organization_type": char.organization_type,
                    "organization_purpose": char.organization_purpose,
                    "organization_members": char.organization_members,
                    "traits": char.traits,
                    "created_at": char.created_at.isoformat() if char.created_at else None,
                    "updated_at": char.updated_at.isoformat() if char.updated_at else None
                } for char in created_characters
            ]
        })
        
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("角色生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("角色生成事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"角色生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("角色生成事务已回滚（异常）")
        yield await tracker.error(f"生成失败: {str(e)}")


@router.post("/characters", summary="流式批量生成角色")
async def generate_characters_stream(
    request: Request,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式批量生成角色，避免超时
    支持MCP工具增强
    """
    # 从中间件注入user_id到data中
    if hasattr(request.state, 'user_id'):
        data['user_id'] = request.state.user_id
    
    return create_sse_response(characters_generator(data, db, user_ai_service))


async def outline_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """大纲生成流式生成器 - 向导仅生成大纲节点，不展开章节（避免等待过久）"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("大纲")
    
    try:
        yield await tracker.start()
        
        project_id = data.get("project_id")
        # 向导固定生成3个大纲节点（不展开）
        outline_count = data.get("chapter_count", 3)
        narrative_perspective = data.get("narrative_perspective")
        target_words = data.get("target_words", 100000)
        requirements = data.get("requirements", "")
        provider = data.get("provider")
        model = data.get("model")
        enable_mcp = data.get("enable_mcp", True)  # 默认启用MCP
        user_id = data.get("user_id")  # 从中间件注入
        
        # 获取项目信息
        yield await tracker.loading("加载项目信息...", 0.3)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        # 获取角色信息
        yield await tracker.loading("加载角色信息...", 0.8)
        result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = result.scalars().all()
        
        characters_info = "\n".join([
            f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): {char.personality[:100] if char.personality else '暂无描述'}"
            for char in characters
        ])
        
        # 准备提示词
        yield await tracker.preparing(f"准备生成{outline_count}个大纲节点...")
        
        outline_requirements = f"{requirements}\n\n【重要说明】这是小说的开局部分，请生成{outline_count}个大纲节点，重点关注：\n"
        outline_requirements += "1. 引入主要角色和世界观设定\n"
        outline_requirements += "2. 建立主线冲突和故事钩子\n"
        outline_requirements += "3. 展开初期情节，为后续发展埋下伏笔\n"
        outline_requirements += "4. 不要试图完结故事，这只是开始部分\n"
        outline_requirements += "5. 不要在JSON字符串值中使用中文引号（""''），请使用【】或《》标记\n"
        
        # 获取自定义提示词模板
        template = await PromptService.get_template("OUTLINE_CREATE", user_id, db)
        outline_prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=project.theme or "未设定",
            genre=project.genre or "通用",
            chapter_count=outline_count,
            narrative_perspective=narrative_perspective,
            target_words=target_words // 10,  # 开局约占总字数的1/10
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            rules=project.world_rules or "未设定",
            characters_info=characters_info or "暂无角色信息",
            mcp_references="",
            requirements=outline_requirements
        )
        
        # 流式生成大纲
        estimated_total = 1000
        accumulated_text = ""
        chunk_count = 0
        
        yield await tracker.generating(current_chars=0, estimated_total=estimated_total)
        
        async for chunk in user_ai_service.generate_text_stream(
            prompt=outline_prompt,
            provider=provider,
            model=model,
        ):
            chunk_count += 1
            accumulated_text += chunk
            
            # 发送内容块
            yield await tracker.generating_chunk(chunk)
            
            # 定期更新进度
            current_len = len(accumulated_text)
            if chunk_count % 10 == 0:
                yield await tracker.generating(
                    current_chars=current_len,
                    estimated_total=estimated_total
                )
            
            # 每20个块发送心跳
            if chunk_count % 20 == 0:
                yield await tracker.heartbeat()
        
        # 解析大纲结果 - 使用统一的JSON清洗方法
        yield await tracker.parsing("解析大纲数据...")
        
        try:
            cleaned_text = user_ai_service._clean_json_response(accumulated_text)
            outline_data = json.loads(cleaned_text)
            if not isinstance(outline_data, list):
                outline_data = [outline_data]
        except json.JSONDecodeError as e:
            logger.error(f"大纲JSON解析失败: {e}")
            yield await tracker.error("大纲生成失败，请重试")
            return
        
        # 保存大纲到数据库
        yield await tracker.saving("保存大纲到数据库...")
        created_outlines = []
        for index, outline_item in enumerate(outline_data[:outline_count], 1):
            outline = Outline(
                project_id=project_id,
                title=outline_item.get("title", f"第{index}节"),
                content=outline_item.get("summary", outline_item.get("content", "")),
                structure=json.dumps(outline_item, ensure_ascii=False),
                order_index=index
            )
            db.add(outline)
            created_outlines.append(outline)
        
        await db.flush()  # 获取大纲ID
        for outline in created_outlines:
            await db.refresh(outline)
        
        logger.info(f"✅ 成功创建{len(created_outlines)}个大纲节点")
        
        # 根据项目的大纲模式决定是否自动创建章节
        created_chapters = []
        if project.outline_mode == 'one-to-one':
            # 一对一模式：自动为每个大纲创建对应的章节
            yield await tracker.saving("一对一模式：自动创建章节...", 0.7)
            
            for outline in created_outlines:
                chapter = Chapter(
                    project_id=project_id,
                    title=outline.title,
                    content="",  # 空内容，等待用户生成
                    outline_id=None,  # 一对一模式下不关联outline_id
                    chapter_number=outline.order_index,  # 使用chapter_number而不是order_index
                    status="pending"
                )
                db.add(chapter)
                created_chapters.append(chapter)
            
            await db.flush()
            for chapter in created_chapters:
                await db.refresh(chapter)
            
            logger.info(f"✅ 一对一模式：自动创建了{len(created_chapters)}个章节")
            yield await tracker.saving(f"已自动创建{len(created_chapters)}个章节", 0.9)
        else:
            # 一对多模式：跳过自动创建，用户可手动展开
            yield await tracker.saving("细化模式：跳过自动创建章节", 0.9)
            logger.info(f"📝 细化模式：跳过章节创建，用户可在大纲页面手动展开")
        
        # 更新项目信息
        # wizard_step: 0=未开始, 1=世界观已完成, 2=职业体系已完成, 3=角色已完成, 4=大纲已完成
        project.chapter_count = len(created_chapters)  # 记录实际创建的章节数
        project.narrative_perspective = narrative_perspective
        project.target_words = target_words
        project.status = "writing"
        project.wizard_status = "completed"
        project.wizard_step = 4
        
        await db.commit()
        db_committed = True
        
        logger.info(f"📊 向导大纲生成完成：")
        logger.info(f"  - 创建大纲节点：{len(created_outlines)} 个")
        logger.info(f"  - 创建章节：{len(created_chapters)} 个")
        logger.info(f"  - 大纲模式：{project.outline_mode}")
        
        # 构建结果消息
        if project.outline_mode == 'one-to-one':
            result_message = f"成功生成{len(created_outlines)}个大纲节点并自动创建{len(created_chapters)}个章节（传统模式）"
            result_note = "已自动创建章节，可直接生成内容"
        else:
            result_message = f"成功生成{len(created_outlines)}个大纲节点（细化模式，可在大纲页面手动展开）"
            result_note = "可在大纲页面展开为多个章节"
        
        yield await tracker.complete()
        
        # 发送结果
        yield await tracker.result({
            "message": result_message,
            "outline_count": len(created_outlines),
            "chapter_count": len(created_chapters),
            "outline_mode": project.outline_mode,
            "outlines": [
                {
                    "id": outline.id,
                    "order_index": outline.order_index,
                    "title": outline.title,
                    "content": outline.content[:100] + "..." if len(outline.content) > 100 else outline.content,
                    "note": result_note
                } for outline in created_outlines
            ],
            "chapters": [
                {
                    "id": chapter.id,
                    "chapter_number": chapter.chapter_number,
                    "title": chapter.title,
                    "status": chapter.status
                } for chapter in created_chapters
            ] if created_chapters else []
        })
        
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("大纲生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲生成事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"大纲生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲生成事务已回滚（异常）")
        yield await tracker.error(f"生成失败: {str(e)}")

@router.post("/outline", summary="流式生成完整大纲")
async def generate_outline_stream(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成完整大纲，避免超时
    """
    return create_sse_response(outline_generator(data, db, user_ai_service))


async def world_building_regenerate_generator(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """世界观重新生成流式生成器"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("世界观")
    
    try:
        yield await tracker.start("开始重新生成世界观...")
        
        # 获取项目信息
        yield await tracker.loading("加载项目信息...")
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        # 提取参数
        provider = data.get("provider")
        model = data.get("model")
        enable_mcp = data.get("enable_mcp", True)
        user_id = data.get("user_id")
        
        # 获取基础提示词（支持自定义）
        yield await tracker.preparing("准备AI提示词...")
        template = await PromptService.get_template("WORLD_BUILDING", user_id, db)
        base_prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=project.theme or "未设定",
            genre=project.genre or "通用",
            description=project.description or "暂无简介"
        )
        
        # 设置用户信息以启用MCP
        if user_id:
            user_ai_service.user_id = user_id
            user_ai_service.db_session = db
        
        # ===== 流式生成世界观（带重试机制） =====
        MAX_WORLD_RETRIES = 3  # 最多重试3次
        world_retry_count = 0
        world_generation_success = False
        world_data = {}
        estimated_total = 1000
        
        while world_retry_count < MAX_WORLD_RETRIES and not world_generation_success:
            try:
                # 重试时重置生成进度
                if world_retry_count > 0:
                    tracker.reset_generating_progress()
                
                yield await tracker.generating(
                    current_chars=0,
                    estimated_total=estimated_total,
                    message="重新生成世界观",
                    retry_count=world_retry_count,
                    max_retries=MAX_WORLD_RETRIES
                )
                
                # 流式生成世界观
                accumulated_text = ""
                chunk_count = 0
                
                async for chunk in user_ai_service.generate_text_stream(
                    prompt=base_prompt,
                    provider=provider,
                    model=model,
                    tool_choice="required",
                ):
                    chunk_count += 1
                    accumulated_text += chunk
                    
                    yield await tracker.generating_chunk(chunk)
                    
                    # 定期更新进度
                    current_len = len(accumulated_text)
                    if chunk_count % 10 == 0:
                        yield await tracker.generating(
                            current_chars=current_len,
                            estimated_total=estimated_total,
                            message="重新生成世界观",
                            retry_count=world_retry_count,
                            max_retries=MAX_WORLD_RETRIES
                        )
                    
                    if chunk_count % 20 == 0:
                        yield await tracker.heartbeat()
                
                # 检查是否返回空响应
                if not accumulated_text or not accumulated_text.strip():
                    logger.warning(f"⚠️ AI返回空世界观（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）")
                    world_retry_count += 1
                    if world_retry_count < MAX_WORLD_RETRIES:
                        yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "AI返回为空")
                        continue
                    else:
                        # 达到最大重试次数，使用默认值
                        logger.error("❌ 世界观重新生成多次返回空响应")
                        world_data = {
                            "time_period": "AI多次返回为空，请稍后重试",
                            "location": "AI多次返回为空，请稍后重试",
                            "atmosphere": "AI多次返回为空，请稍后重试",
                            "rules": "AI多次返回为空，请稍后重试"
                        }
                        world_generation_success = True
                        break
                
                # 解析结果 - 使用统一的JSON清洗方法
                yield await tracker.parsing("解析AI返回结果...")
                
                try:
                    logger.info(f"🔍 开始清洗JSON，原始长度: {len(accumulated_text)}")
                    cleaned_text = user_ai_service._clean_json_response(accumulated_text)
                    logger.info(f"✅ JSON清洗完成，清洗后长度: {len(cleaned_text)}")
                    
                    world_data = json.loads(cleaned_text)
                    logger.info(f"✅ 世界观重新生成JSON解析成功（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）")
                    world_generation_success = True
                            
                except json.JSONDecodeError as e:
                    logger.error(f"❌ 世界构建JSON解析失败（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）: {e}")
                    logger.error(f"   原始内容长度: {len(accumulated_text)}")
                    logger.error(f"   原始内容预览: {accumulated_text[:200]}")
                    world_retry_count += 1
                    if world_retry_count < MAX_WORLD_RETRIES:
                        yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "JSON解析失败")
                        continue
                    else:
                        # 达到最大重试次数，使用默认值
                        world_data = {
                            "time_period": "AI返回格式错误，请重试",
                            "location": "AI返回格式错误，请重试",
                            "atmosphere": "AI返回格式错误，请重试",
                            "rules": "AI返回格式错误，请重试"
                        }
                        world_generation_success = True
                        
            except Exception as e:
                logger.error(f"❌ 世界观重新生成异常（尝试{world_retry_count+1}/{MAX_WORLD_RETRIES}）: {type(e).__name__}: {e}")
                world_retry_count += 1
                if world_retry_count < MAX_WORLD_RETRIES:
                    yield await tracker.retry(world_retry_count, MAX_WORLD_RETRIES, "生成异常")
                    continue
                else:
                    # 最后一次重试仍失败，抛出异常
                    logger.error(f"   accumulated_text 长度: {len(accumulated_text) if 'accumulated_text' in locals() else 'N/A'}")
                    raise
        
        # 不保存到数据库，仅返回生成结果供用户预览
        yield await tracker.saving("生成完成，等待用户确认...", 0.5)
        
        yield await tracker.complete()
        
        # 发送最终结果（不包含project_id，表示未保存）
        yield await tracker.result({
            "time_period": world_data.get("time_period"),
            "location": world_data.get("location"),
            "atmosphere": world_data.get("atmosphere"),
            "rules": world_data.get("rules")
        })
        
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("世界观重新生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界观重新生成事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"世界观重新生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界观重新生成事务已回滚（异常）")
        yield await tracker.error(f"生成失败: {str(e)}")


@router.post("/world-building/{project_id}/regenerate", summary="流式重新生成世界观")
async def regenerate_world_building_stream(
    project_id: str,
    request: Request,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式重新生成世界观，避免超时
    前端使用EventSource接收实时进度和结果
    """
    # 从中间件注入user_id到data中
    if hasattr(request.state, 'user_id'):
        data['user_id'] = request.state.user_id
    return create_sse_response(world_building_regenerate_generator(project_id, data, db, user_ai_service))
