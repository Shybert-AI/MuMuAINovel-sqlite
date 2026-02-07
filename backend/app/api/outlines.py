"""大纲管理API"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, AsyncGenerator, Dict, Any
import json

from app.database import get_db
from app.api.common import verify_project_access
from app.models.outline import Outline
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.schemas.outline import (
    OutlineCreate,
    OutlineUpdate,
    OutlineResponse,
    OutlineListResponse,
    OutlineGenerateRequest,
    OutlineExpansionRequest,
    OutlineExpansionResponse,
    BatchOutlineExpansionRequest,
    BatchOutlineExpansionResponse,
    CreateChaptersFromPlansRequest,
    CreateChaptersFromPlansResponse,
    CharacterPredictionRequest,
    PredictedCharacter,
    CharacterPredictionResponse,
    OrganizationPredictionRequest,
    PredictedOrganization,
    OrganizationPredictionResponse
)
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service, PromptService
from app.services.memory_service import memory_service
from app.services.plot_expansion_service import PlotExpansionService
from app.services.foreshadow_service import foreshadow_service
from app.services.memory_service import memory_service
from app.logger import get_logger
from app.api.settings import get_user_ai_service
from app.utils.sse_response import SSEResponse, create_sse_response, WizardProgressTracker

router = APIRouter(prefix="/outlines", tags=["大纲管理"])
logger = get_logger(__name__)


def _build_chapters_brief(outlines: List[Outline], max_recent: int = 20) -> str:
    """构建章节概览字符串"""
    target = outlines[-max_recent:] if len(outlines) > max_recent else outlines
    return "\n".join([f"第{o.order_index}章《{o.title}》" for o in target])


def _build_characters_info(characters: List[Character]) -> str:
    """构建角色信息字符串"""
    return "\n".join([
        f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): "
        f"{char.personality[:100] if char.personality else '暂无描述'}"
        for char in characters
    ])


async def _get_existing_organizations(project_id: str, db: AsyncSession) -> List[dict]:
    """获取项目现有组织列表"""
    from app.models.relationship import Organization
    
    organizations_result = await db.execute(
        select(Character, Organization)
        .join(Organization, Character.id == Organization.character_id)
        .where(
            Character.project_id == project_id,
            Character.is_organization == True
        )
    )
    organizations_raw = organizations_result.all()
    return [
        {
            "id": org.id,
            "name": char.name,
            "organization_type": char.organization_type,
            "organization_purpose": char.organization_purpose,
            "power_level": org.power_level,
            "location": org.location,
            "motto": org.motto
        }
        for char, org in organizations_raw
    ]


@router.post("", response_model=OutlineResponse, summary="创建大纲")
async def create_outline(
    outline: OutlineCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """创建新的章节大纲（one-to-one模式会自动创建对应章节）"""
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    project = await verify_project_access(outline.project_id, user_id, db)
    
    # 创建大纲
    db_outline = Outline(**outline.model_dump())
    db.add(db_outline)
    await db.flush()  # 确保大纲有ID
    
    # 如果是one-to-one模式，自动创建对应的章节
    if project.outline_mode == 'one-to-one':
        chapter = Chapter(
            project_id=outline.project_id,
            title=db_outline.title,
            summary=db_outline.content,
            chapter_number=db_outline.order_index,
            sub_index=1,
            outline_id=None,  # one-to-one模式不关联outline_id
            status='pending',
            content=""
        )
        db.add(chapter)
        logger.info(f"一对一模式：为手动创建的大纲 {db_outline.title} (序号{db_outline.order_index}) 自动创建了对应章节")
    
    await db.commit()
    await db.refresh(db_outline)
    return db_outline


@router.get("", response_model=OutlineListResponse, summary="获取大纲列表")
async def get_outlines(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有大纲"""
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    # 获取总数
    count_result = await db.execute(
        select(func.count(Outline.id)).where(Outline.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取大纲列表
    result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.order_index)
    )
    outlines = result.scalars().all()
    
    return OutlineListResponse(total=total, items=outlines)


@router.get("/project/{project_id}", response_model=OutlineListResponse, summary="获取项目的所有大纲")
async def get_project_outlines(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有大纲（路径参数版本，兼容旧API）"""
    return await get_outlines(project_id, request, db)


@router.get("/{outline_id}", response_model=OutlineResponse, summary="获取大纲详情")
async def get_outline(
    outline_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取大纲详情"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(outline.project_id, user_id, db)
    
    return outline


@router.put("/{outline_id}", response_model=OutlineResponse, summary="更新大纲")
async def update_outline(
    outline_id: str,
    outline_update: OutlineUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新大纲信息并同步更新structure字段和关联章节"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    project = await verify_project_access(outline.project_id, user_id, db)
    
    # 更新字段
    update_data = outline_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(outline, field, value)
    
    # 如果修改了content或title，同步更新structure字段
    if 'content' in update_data or 'title' in update_data:
        try:
            # 尝试解析现有的structure
            if outline.structure:
                structure_data = json.loads(outline.structure)
            else:
                structure_data = {}
            
            # 更新structure中的对应字段
            if 'title' in update_data:
                structure_data['title'] = outline.title
            if 'content' in update_data:
                structure_data['summary'] = outline.content
                structure_data['content'] = outline.content
            
            # 保存更新后的structure
            outline.structure = json.dumps(structure_data, ensure_ascii=False)
            logger.info(f"同步更新大纲 {outline_id} 的structure字段")
        except json.JSONDecodeError:
            logger.warning(f"大纲 {outline_id} 的structure字段格式错误，跳过更新")
    
    # 🔧 传统模式（one-to-one）：同步更新关联章节的标题
    if 'title' in update_data and project.outline_mode == 'one-to-one':
        try:
            # 查找对应的章节（通过chapter_number匹配order_index）
            chapter_result = await db.execute(
                select(Chapter).where(
                    Chapter.project_id == outline.project_id,
                    Chapter.chapter_number == outline.order_index
                )
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if chapter:
                # 同步更新章节标题
                chapter.title = outline.title
                logger.info(f"一对一模式：同步更新章节 {chapter.id} 的标题为 '{outline.title}'")
            else:
                logger.debug(f"一对一模式：未找到对应的章节（chapter_number={outline.order_index}）")
        except Exception as e:
            logger.error(f"同步更新章节标题失败: {str(e)}")
            # 不阻断大纲更新流程，仅记录错误
    
    await db.commit()
    await db.refresh(outline)
    return outline


@router.delete("/{outline_id}", summary="删除大纲")
async def delete_outline(
    outline_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除大纲，同时删除该大纲对应的所有章节和相关的伏笔数据"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    project = await verify_project_access(outline.project_id, user_id, db)
    
    project_id = outline.project_id
    deleted_order = outline.order_index
    
    # 获取要删除的章节并计算总字数
    deleted_word_count = 0
    deleted_foreshadow_count = 0
    if project.outline_mode == 'one-to-one':
        # one-to-one模式：通过chapter_number获取对应章节
        chapters_result = await db.execute(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == outline.order_index
            )
        )
        chapters_to_delete = chapters_result.scalars().all()
        deleted_word_count = sum(ch.word_count or 0 for ch in chapters_to_delete)
        
        # 🔮 清理章节相关的伏笔数据和向量记忆
        for chapter in chapters_to_delete:
            try:
                # 清理向量数据库中的记忆数据
                await memory_service.delete_chapter_memories(
                    user_id=user_id,
                    project_id=project_id,
                    chapter_id=chapter.id
                )
                logger.info(f"✅ 已清理章节 {chapter.id[:8]} 的向量记忆数据")
            except Exception as e:
                logger.warning(f"⚠️ 清理章节 {chapter.id[:8]} 向量记忆失败: {str(e)}")
            
            try:
                # 清理伏笔数据（分析来源的伏笔）
                foreshadow_result = await foreshadow_service.delete_chapter_foreshadows(
                    db=db,
                    project_id=project_id,
                    chapter_id=chapter.id,
                    only_analysis_source=True
                )
                deleted_foreshadow_count += foreshadow_result.get('deleted_count', 0)
                if foreshadow_result.get('deleted_count', 0) > 0:
                    logger.info(f"🔮 已清理章节 {chapter.id[:8]} 的 {foreshadow_result['deleted_count']} 个伏笔数据")
            except Exception as e:
                logger.warning(f"⚠️ 清理章节 {chapter.id[:8]} 伏笔数据失败: {str(e)}")
        
        # 删除章节
        delete_result = await db.execute(
            delete(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == outline.order_index
            )
        )
        deleted_chapters_count = delete_result.rowcount
        logger.info(f"一对一模式：删除大纲 {outline_id}（序号{outline.order_index}），同时删除了第{outline.order_index}章（{deleted_chapters_count}个章节，{deleted_word_count}字，{deleted_foreshadow_count}个伏笔）")
    else:
        # one-to-many模式：通过outline_id获取关联章节
        chapters_result = await db.execute(
            select(Chapter).where(Chapter.outline_id == outline_id)
        )
        chapters_to_delete = chapters_result.scalars().all()
        deleted_word_count = sum(ch.word_count or 0 for ch in chapters_to_delete)
        
        # 🔮 清理章节相关的伏笔数据和向量记忆
        for chapter in chapters_to_delete:
            try:
                # 清理向量数据库中的记忆数据
                await memory_service.delete_chapter_memories(
                    user_id=user_id,
                    project_id=project_id,
                    chapter_id=chapter.id
                )
                logger.info(f"✅ 已清理章节 {chapter.id[:8]} 的向量记忆数据")
            except Exception as e:
                logger.warning(f"⚠️ 清理章节 {chapter.id[:8]} 向量记忆失败: {str(e)}")
            
            try:
                # 清理伏笔数据（分析来源的伏笔）
                foreshadow_result = await foreshadow_service.delete_chapter_foreshadows(
                    db=db,
                    project_id=project_id,
                    chapter_id=chapter.id,
                    only_analysis_source=True
                )
                deleted_foreshadow_count += foreshadow_result.get('deleted_count', 0)
                if foreshadow_result.get('deleted_count', 0) > 0:
                    logger.info(f"🔮 已清理章节 {chapter.id[:8]} 的 {foreshadow_result['deleted_count']} 个伏笔数据")
            except Exception as e:
                logger.warning(f"⚠️ 清理章节 {chapter.id[:8]} 伏笔数据失败: {str(e)}")
        
        # 删除章节
        delete_result = await db.execute(
            delete(Chapter).where(Chapter.outline_id == outline_id)
        )
        deleted_chapters_count = delete_result.rowcount
        logger.info(f"一对多模式：删除大纲 {outline_id}，同时删除了 {deleted_chapters_count} 个关联章节（{deleted_word_count}字，{deleted_foreshadow_count}个伏笔）")
    
    # 更新项目字数
    if deleted_word_count > 0:
        project.current_words = max(0, project.current_words - deleted_word_count)
        logger.info(f"更新项目字数：减少 {deleted_word_count} 字")
    
    # 删除大纲
    await db.delete(outline)
    
    # 重新排序后续的大纲（序号-1）
    result = await db.execute(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.order_index > deleted_order
        )
    )
    subsequent_outlines = result.scalars().all()
    
    for o in subsequent_outlines:
        o.order_index -= 1
    
    # 如果是one-to-one模式，还需要重新排序后续章节的chapter_number
    if project.outline_mode == 'one-to-one':
        chapters_result = await db.execute(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number > deleted_order
            ).order_by(Chapter.chapter_number)
        )
        subsequent_chapters = chapters_result.scalars().all()
        
        for ch in subsequent_chapters:
            ch.chapter_number -= 1
        
        logger.info(f"一对一模式：重新排序了 {len(subsequent_chapters)} 个后续章节")
    
    await db.commit()
    
    return {
        "message": "大纲删除成功",
        "deleted_chapters": deleted_chapters_count,
        "deleted_foreshadows": deleted_foreshadow_count
    }



@router.post("/predict-characters", summary="预测续写所需角色")
async def predict_characters(
    request_data: CharacterPredictionRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    预测续写大纲时可能需要的新角色
    
    用于角色确认机制的第一步：在生成大纲前预测角色需求
    """
    # 验证用户权限
    user_id = getattr(http_request.state, 'user_id', None)
    project = await verify_project_access(request_data.project_id, user_id, db)
    
    try:
        # 获取现有大纲
        existing_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == request_data.project_id)
            .order_by(Outline.order_index)
        )
        existing_outlines = existing_result.scalars().all()
        
        if not existing_outlines:
            return CharacterPredictionResponse(
                needs_new_characters=False,
                reason="项目尚无大纲，无法预测角色需求",
                character_count=0,
                predicted_characters=[]
            )
        
        # 获取现有角色
        characters_result = await db.execute(
            select(Character).where(Character.project_id == request_data.project_id)
        )
        characters = characters_result.scalars().all()
        
        # 构建已有章节概览
        all_chapters_brief = _build_chapters_brief(existing_outlines)
        
        # 调用自动角色服务进行预测
        from app.services.auto_character_service import get_auto_character_service
        
        auto_char_service = get_auto_character_service(user_ai_service)
        
        # 使用预测模式（不创建角色，仅分析）
        last_chapter_number = existing_outlines[-1].order_index
        auto_result = await auto_char_service.analyze_and_create_characters(
            project_id=request_data.project_id,
            outline_content="",  # 预测模式不需要大纲内容
            existing_characters=list(characters),
            db=db,
            user_id=user_id,
            enable_mcp=request_data.enable_mcp,
            all_chapters_brief=all_chapters_brief,
            start_chapter=last_chapter_number + 1,
            chapter_count=request_data.chapter_count,
            plot_stage=request_data.plot_stage,
            story_direction=request_data.story_direction,
            preview_only=True  # 新增参数：仅预测不创建
        )
        
        # 构建预测响应
        predicted_characters = []
        for char_data in auto_result.get("predicted_characters", []):
            predicted_characters.append(PredictedCharacter(
                name=char_data.get("name"),
                role_description=char_data.get("role_description", ""),
                suggested_role_type=char_data.get("suggested_role_type", "supporting"),
                importance=char_data.get("importance", "medium"),
                appearance_chapter=char_data.get("appearance_chapter", last_chapter_number + 1),
                key_abilities=char_data.get("key_abilities", []),
                plot_function=char_data.get("plot_function", ""),
                relationship_suggestions=char_data.get("relationship_suggestions", [])
            ))
        
        return CharacterPredictionResponse(
            needs_new_characters=auto_result.get("needs_new_characters", False),
            reason=auto_result.get("reason", ""),
            character_count=len(predicted_characters),
            predicted_characters=predicted_characters
        )
        
    except Exception as e:
        logger.error(f"角色预测失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"角色预测失败: {str(e)}")


@router.post("/predict-organizations", summary="预测续写所需组织")
async def predict_organizations(
    request_data: OrganizationPredictionRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    预测续写大纲时可能需要的新组织
    
    用于组织确认机制的第一步：在生成大纲前预测组织需求
    """
    from app.models.relationship import Organization
    
    # 验证用户权限
    user_id = getattr(http_request.state, 'user_id', None)
    project = await verify_project_access(request_data.project_id, user_id, db)
    
    try:
        # 获取现有大纲
        existing_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == request_data.project_id)
            .order_by(Outline.order_index)
        )
        existing_outlines = existing_result.scalars().all()
        
        if not existing_outlines:
            return OrganizationPredictionResponse(
                needs_new_organizations=False,
                reason="项目尚无大纲，无法预测组织需求",
                organization_count=0,
                predicted_organizations=[]
            )
        
        # 获取现有角色
        characters_result = await db.execute(
            select(Character).where(Character.project_id == request_data.project_id)
        )
        characters = characters_result.scalars().all()
        
        # 获取现有组织
        existing_organizations = await _get_existing_organizations(request_data.project_id, db)
        
        # 构建已有章节概览
        all_chapters_brief = _build_chapters_brief(existing_outlines)
        
        # 调用自动组织服务进行预测
        from app.services.auto_organization_service import get_auto_organization_service
        
        auto_org_service = get_auto_organization_service(user_ai_service)
        
        # 使用预测模式（不创建组织，仅分析）
        last_chapter_number = existing_outlines[-1].order_index
        auto_result = await auto_org_service.analyze_and_create_organizations(
            project_id=request_data.project_id,
            outline_content="",  # 预测模式不需要大纲内容
            existing_characters=list(characters),
            existing_organizations=existing_organizations,
            db=db,
            user_id=user_id,
            enable_mcp=request_data.enable_mcp,
            all_chapters_brief=all_chapters_brief,
            start_chapter=last_chapter_number + 1,
            chapter_count=request_data.chapter_count,
            plot_stage=request_data.plot_stage,
            story_direction=request_data.story_direction,
            preview_only=True  # 仅预测不创建
        )
        
        # 构建预测响应
        predicted_organizations = []
        for org_data in auto_result.get("predicted_organizations", []):
            predicted_organizations.append(PredictedOrganization(
                name=org_data.get("name"),
                organization_description=org_data.get("organization_description", ""),
                organization_type=org_data.get("organization_type", "未知"),
                importance=org_data.get("importance", "medium"),
                appearance_chapter=org_data.get("appearance_chapter", last_chapter_number + 1),
                power_level=org_data.get("power_level", 50),
                plot_function=org_data.get("plot_function", ""),
                location=org_data.get("location"),
                motto=org_data.get("motto"),
                initial_members=org_data.get("initial_members", []),
                relationship_suggestions=org_data.get("relationship_suggestions", [])
            ))
        
        return OrganizationPredictionResponse(
            needs_new_organizations=auto_result.get("needs_new_organizations", False),
            reason=auto_result.get("reason", ""),
            organization_count=len(predicted_organizations),
            predicted_organizations=predicted_organizations
        )
        
    except Exception as e:
        logger.error(f"组织预测失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"组织预测失败: {str(e)}")



async def _generate_new_outline(
    request: OutlineGenerateRequest,
    project: Project,
    db: AsyncSession,
    user_ai_service: AIService,
    user_id: str
) -> OutlineListResponse:
    """全新生成大纲（MCP增强版）"""
    logger.info(f"全新生成大纲 - 项目: {project.id}, enable_mcp: {request.enable_mcp}")
    
    # 获取角色信息
    characters_result = await db.execute(
        select(Character).where(Character.project_id == project.id)
    )
    characters = characters_result.scalars().all()
    characters_info = _build_characters_info(characters)
    
    # 设置用户信息以启用MCP
    if user_id:
        user_ai_service.user_id = user_id
        user_ai_service.db_session = db
    
    # 使用提示词模板
    template = await PromptService.get_template("OUTLINE_CREATE", user_id, db)
    prompt = PromptService.format_prompt(
        template,
        title=project.title,
        theme=request.theme or project.theme or "未设定",
        genre=request.genre or project.genre or "通用",
        chapter_count=request.chapter_count,
        narrative_perspective=request.narrative_perspective,
        target_words=request.target_words,
        time_period=project.world_time_period or "未设定",
        location=project.world_location or "未设定",
        atmosphere=project.world_atmosphere or "未设定",
        rules=project.world_rules or "未设定",
        characters_info=characters_info or "暂无角色信息",
        requirements=request.requirements or "",
        mcp_references=""
    )
    
    # 调用AI流式生成大纲（带字数统计）
    accumulated_text = ""
    chunk_count = 0
    
    async for chunk in user_ai_service.generate_text_stream(
        prompt=prompt,
        provider=request.provider,
        model=request.model,
        auto_mcp=request.enable_mcp
    ):
        chunk_count += 1
        accumulated_text += chunk
        
        # 这里是非SSE接口，不需要发送chunk
        # 如果未来需要转SSE，可以在这里yield
    
    ai_content = accumulated_text
    ai_response = {"content": ai_content}
    
    # 解析响应
    outline_data = _parse_ai_response(ai_content)
    
    # 全新生成模式：删除旧大纲和关联的所有章节
    logger.info(f"全新生成：删除项目 {project.id} 的旧大纲和章节（outline_mode: {project.outline_mode}）")
    
    # 清理伏笔数据
    try:
        await foreshadow_service.clear_project_foreshadows_for_reset(db, project.id)
    except Exception as e:
        logger.warning(f"清理伏笔数据失败（不影响主流程）: {str(e)}")

    from sqlalchemy import delete as sql_delete
    
    # 先获取所有旧章节并计算总字数
    old_chapters_result = await db.execute(
        select(Chapter).where(Chapter.project_id == project.id)
    )
    old_chapters = old_chapters_result.scalars().all()
    deleted_word_count = sum(ch.word_count or 0 for ch in old_chapters)
    
    # 删除所有旧章节（无论是一对一还是一对多模式）
    delete_result = await db.execute(
        sql_delete(Chapter).where(Chapter.project_id == project.id)
    )
    deleted_chapters_count = delete_result.rowcount
    logger.info(f"✅ 全新生成：删除了 {deleted_chapters_count} 个旧章节（{deleted_word_count}字）")
    
    # 更新项目字数
    if deleted_word_count > 0:
        project.current_words = max(0, project.current_words - deleted_word_count)
        logger.info(f"更新项目字数：减少 {deleted_word_count} 字")
    
    # 再删除所有旧大纲
    delete_outline_result = await db.execute(
        sql_delete(Outline).where(Outline.project_id == project.id)
    )
    deleted_outlines_count = delete_outline_result.rowcount
    logger.info(f"✅ 全新生成：删除了 {deleted_outlines_count} 个旧大纲")
    
    # 保存新大纲
    outlines = await _save_outlines(
        project.id, outline_data, db, start_index=1
    )
    
    # 记录历史
    history = GenerationHistory(
        project_id=project.id,
        prompt=prompt,
        generated_content=json.dumps(ai_response, ensure_ascii=False) if isinstance(ai_response, dict) else ai_response,
        model=request.model or "default"
    )
    db.add(history)
    
    await db.commit()
    
    for outline in outlines:
        await db.refresh(outline)
    
    logger.info(f"全新生成完成 - {len(outlines)} 章")
    return OutlineListResponse(total=len(outlines), items=outlines)


async def _build_smart_outline_context(
    latest_outlines: List[Outline],
    user_id: str,
    project_id: str
) -> dict:
    """
    智能构建大纲续写上下文（支持海量大纲场景）
    
    策略：
    1. 故事骨架：每50章采样1章（仅标题）
    2. 近期概要：最近20章（标题+简要）
    3. 最近详细：最近2章（完整内容）
    
    Args:
        latest_outlines: 所有已有大纲列表
        user_id: 用户ID
        project_id: 项目ID
        
    Returns:
        包含压缩后上下文的字典
    """
    total_count = len(latest_outlines)
    
    context = {
        'story_skeleton': '',      # 故事骨架（标题列表）
        'recent_summary': '',      # 近期概要（标题+内容前50字）
        'recent_detail': '',       # 最近详细（完整内容）
        'stats': {
            'total': total_count,
            'skeleton_samples': 0,
            'recent_summaries': 0,
            'recent_details': 0
        }
    }
    
    try:
        # 1. 故事骨架（每50章采样，仅标题）
        if total_count > 50:
            sample_interval = 50
            skeleton_indices = list(range(0, total_count, sample_interval))
            skeleton_titles = [
                f"第{latest_outlines[idx].order_index}章: {latest_outlines[idx].title}"
                for idx in skeleton_indices
            ]
            context['story_skeleton'] = "【故事骨架】\n" + "\n".join(skeleton_titles)
            context['stats']['skeleton_samples'] = len(skeleton_titles)
            logger.info(f"  ✅ 故事骨架：采样{len(skeleton_titles)}章标题")
        
        # 2. 近期概要（最近20章，标题+内容前50字）
        recent_summary_count = min(20, total_count)
        if recent_summary_count > 2:  # 排除最后2章（它们会完整展示）
            recent_for_summary = latest_outlines[-recent_summary_count:-2]
            recent_summaries = [
                f"第{o.order_index}章《{o.title}》: {o.content[:50]}..."
                for o in recent_for_summary
            ]
            context['recent_summary'] = "【近期大纲概要】\n" + "\n".join(recent_summaries)
            context['stats']['recent_summaries'] = len(recent_summaries)
            logger.info(f"  ✅ 近期概要：{len(recent_summaries)}章")
        
        # 3. 最近详细（最近2章，完整内容）
        recent_detail_count = min(2, total_count)
        recent_details = latest_outlines[-recent_detail_count:]
        detail_texts = [
            f"第{o.order_index}章《{o.title}》: {o.content}"
            for o in recent_details
        ]
        context['recent_detail'] = "【最近大纲详情】\n" + "\n".join(detail_texts)
        context['stats']['recent_details'] = len(detail_texts)
        logger.info(f"  ✅ 最近详细：{len(detail_texts)}章")
        
        # 计算总长度
        total_length = sum([
            len(context['story_skeleton']),
            len(context['recent_summary']),
            len(context['recent_detail'])
        ])
        context['stats']['total_length'] = total_length
        logger.info(f"📊 大纲上下文总长度: {total_length} 字符")
        
    except Exception as e:
        logger.error(f"❌ 构建智能大纲上下文失败: {str(e)}", exc_info=True)
    
    return context


async def _continue_outline(
    request: OutlineGenerateRequest,
    project: Project,
    existing_outlines: List[Outline],
    db: AsyncSession,
    user_ai_service: AIService,
    user_id: str
) -> OutlineListResponse:
    """续写大纲 - 分批生成，每批5章（记忆+MCP+自动角色引入增强版）"""
    logger.info(f"续写大纲 - 项目: {project.id}, 已有: {len(existing_outlines)} 章, enable_mcp: {request.enable_mcp}, enable_auto_characters: {request.enable_auto_characters}")
    
    # 分析已有大纲
    current_chapter_count = len(existing_outlines)
    last_chapter_number = existing_outlines[-1].order_index
    
    # 计算需要生成的总章数和批次
    total_chapters_to_generate = request.chapter_count
    batch_size = 5  # 每批生成5章
    total_batches = (total_chapters_to_generate + batch_size - 1) // batch_size
    
    logger.info(f"分批生成计划: 总共{total_chapters_to_generate}章，分{total_batches}批，每批{batch_size}章")
    
    # 获取角色信息（所有批次共用）
    characters_result = await db.execute(
        select(Character).where(Character.project_id == project.id)
    )
    characters = characters_result.scalars().all()
    characters_info = _build_characters_info(characters)
    
    # 情节阶段指导
    stage_instructions = {
        "development": "继续展开情节，深化角色关系，推进主线冲突",
        "climax": "进入故事高潮，矛盾激化，关键冲突爆发",
        "ending": "解决主要冲突，收束伏笔，给出结局"
    }
    stage_instruction = stage_instructions.get(request.plot_stage, "")
    
    # 🎭 【方案A】先角色后大纲：在生成大纲前预测并创建角色
    # 🔧 判断：如果confirmed_organizations存在，说明已经是组织确认阶段，跳过角色处理
    if request.enable_auto_characters and not request.confirmed_organizations:
        # 检查是否有用户确认的角色列表
        if request.confirmed_characters:
            # 直接使用用户确认的角色列表创建角色
            try:
                from app.services.auto_character_service import get_auto_character_service
                
                logger.info(f"🎭 【确认模式】用户提供了 {len(request.confirmed_characters)} 个确认的角色，直接创建")
                
                auto_char_service = get_auto_character_service(user_ai_service)
                
                # 🔧 去重检查：获取现有角色名称列表，避免重复创建
                existing_character_names = {char.name for char in characters}
                actually_created_count = 0
                
                for char_data in request.confirmed_characters:
                    try:
                        # 检查角色是否已存在
                        char_name = char_data.get("name") or char_data.get("character_name")
                        if char_name in existing_character_names:
                            logger.warning(f"⚠️ 角色 '{char_name}' 已存在，跳过创建")
                            continue
                        
                        # 生成角色详细信息
                        character_data = await auto_char_service._generate_character_details(
                            spec=char_data,
                            project=project,
                            existing_characters=list(characters),
                            db=db,
                            user_id=user_id,
                            enable_mcp=request.enable_mcp
                        )
                        
                        # 创建角色记录
                        character = await auto_char_service._create_character_record(
                            project_id=project.id,
                            character_data=character_data,
                            db=db
                        )
                        
                        # 建立关系
                        relationships_data = character_data.get("relationships") or character_data.get("relationships_array", [])
                        if relationships_data:
                            await auto_char_service._create_relationships(
                                new_character=character,
                                relationship_specs=relationships_data,
                                existing_characters=list(characters),
                                project_id=project.id,
                                db=db
                            )
                        
                        characters.append(character)
                        existing_character_names.add(character.name)  # 更新已存在的角色名称集合
                        actually_created_count += 1
                        logger.info(f"✅ 创建确认的角色: {character.name}")
                        
                    except Exception as e:
                        logger.error(f"创建确认的角色失败: {e}", exc_info=True)
                        continue
                
                # 提交角色到数据库
                if actually_created_count > 0:
                    await db.commit()
                    logger.info(f"✅ 【确认模式】实际创建了 {actually_created_count} 个新角色（跳过了 {len(request.confirmed_characters) - actually_created_count} 个已存在的角色）")
                else:
                    logger.info(f"ℹ️ 【确认模式】所有角色均已存在，无需创建")
                
                # 更新角色信息（供后续大纲生成使用）
                characters_info = _build_characters_info(characters)
                
            except Exception as e:
                logger.error(f"⚠️ 【确认模式】创建确认角色失败: {e}", exc_info=True)
        else:
            # 根据 require_character_confirmation 决定处理方式
            try:
                from app.services.auto_character_service import get_auto_character_service
                
                # 构建已有章节概览
                all_chapters_brief_for_analysis = _build_chapters_brief(existing_outlines)
                
                auto_char_service = get_auto_character_service(user_ai_service)
                
                if request.require_character_confirmation:
                    # 🔮 预测模式：仅预测角色，不自动创建，需要用户确认
                    logger.info(f"🔮 【预测模式】在生成大纲前预测是否需要新角色（需用户确认）")
                    
                    auto_result = await auto_char_service.analyze_and_create_characters(
                        project_id=project.id,
                        outline_content="",  # 预测模式不需要大纲内容
                        existing_characters=list(characters),
                        db=db,
                        user_id=user_id,
                        enable_mcp=request.enable_mcp,
                        all_chapters_brief=all_chapters_brief_for_analysis,
                        start_chapter=last_chapter_number + 1,
                        chapter_count=total_chapters_to_generate,
                        plot_stage=request.plot_stage,
                        story_direction=request.story_direction or "自然延续",
                        preview_only=True  # ✅ 仅预测不创建
                    )
                    
                    # 检查是否需要新角色
                    if auto_result.get("needs_new_characters") and auto_result.get("predicted_characters"):
                        predicted_count = len(auto_result["predicted_characters"])
                        logger.warning(
                            f"⚠️ 【预测模式】AI预测需要 {predicted_count} 个新角色，需要用户确认！"
                        )
                        
                        # 🚨 抛出特殊异常，包含预测的角色信息
                        raise HTTPException(
                            status_code=449,  # 449 Retry With
                            detail={
                                "code": "CHARACTER_CONFIRMATION_REQUIRED",
                                "message": "续写需要引入新角色，请先确认角色信息",
                                "predicted_characters": auto_result["predicted_characters"],
                                "reason": auto_result.get("reason", "剧情发展需要新角色"),
                                "chapter_range": f"第{last_chapter_number + 1}-{last_chapter_number + total_chapters_to_generate}章"
                            }
                        )
                    else:
                        logger.info(f"✅ 【预测模式】AI判断无需引入新角色，继续生成大纲")
                else:
                    # 🚀 直接创建模式：预测后自动创建，无需用户确认
                    logger.info(f"🚀 【直接创建模式】在生成大纲前预测并直接创建新角色（无需确认）")
                    
                    auto_result = await auto_char_service.analyze_and_create_characters(
                        project_id=project.id,
                        outline_content="",
                        existing_characters=list(characters),
                        db=db,
                        user_id=user_id,
                        enable_mcp=request.enable_mcp,
                        all_chapters_brief=all_chapters_brief_for_analysis,
                        start_chapter=last_chapter_number + 1,
                        chapter_count=total_chapters_to_generate,
                        plot_stage=request.plot_stage,
                        story_direction=request.story_direction or "自然延续",
                        preview_only=False  # ✅ 直接创建角色
                    )
                    
                    # 如果创建了新角色，更新角色列表
                    if auto_result.get("new_characters"):
                        new_count = len(auto_result["new_characters"])
                        logger.info(f"✅ 【直接创建模式】自动创建了 {new_count} 个新角色")
                        
                        # 提交角色到数据库
                        await db.commit()
                        
                        # 更新角色信息（供后续大纲生成使用）
                        characters.extend(auto_result["new_characters"])
                        characters_info = _build_characters_info(characters)
                    else:
                        logger.info(f"✅ 【直接创建模式】AI判断无需引入新角色，继续生成大纲")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"⚠️ 【方案A】预测性角色引入失败: {e}", exc_info=True)
                # 不阻断大纲生成流程
    
    # 🏛️ 【组织引入】在生成大纲前预测并创建组织
    if request.enable_auto_organizations:
        # 获取现有组织
        existing_organizations = await _get_existing_organizations(project.id, db)
        
        # 检查是否有用户确认的组织列表
        if request.confirmed_organizations:
            # 直接使用用户确认的组织列表创建组织
            try:
                from app.services.auto_organization_service import get_auto_organization_service
                
                logger.info(f"🏛️ 【确认模式】用户提供了 {len(request.confirmed_organizations)} 个确认的组织，直接创建")
                
                auto_org_service = get_auto_organization_service(user_ai_service)
                
                for org_data in request.confirmed_organizations:
                    try:
                        # 生成组织详细信息
                        organization_data = await auto_org_service._generate_organization_details(
                            spec=org_data,
                            project=project,
                            existing_characters=list(characters),
                            existing_organizations=existing_organizations,
                            db=db,
                            user_id=user_id,
                            enable_mcp=request.enable_mcp
                        )
                        
                        # 创建组织记录
                        org_character, organization = await auto_org_service._create_organization_record(
                            project_id=project.id,
                            organization_data=organization_data,
                            db=db
                        )
                        
                        # 建立成员关系
                        members_data = organization_data.get("initial_members", [])
                        if members_data:
                            await auto_org_service._create_member_relationships(
                                organization=organization,
                                member_specs=members_data,
                                existing_characters=list(characters),
                                project_id=project.id,
                                db=db
                            )
                        
                        # 更新角色列表（组织也是Character）
                        characters.append(org_character)
                        existing_organizations.append({
                            "id": organization.id,
                            "name": org_character.name,
                            "organization_type": org_character.organization_type,
                            "organization_purpose": org_character.organization_purpose,
                            "power_level": organization.power_level,
                            "location": organization.location,
                            "motto": organization.motto
                        })
                        logger.info(f"✅ 创建确认的组织: {org_character.name}")
                        
                    except Exception as e:
                        logger.error(f"创建确认的组织失败: {e}", exc_info=True)
                        continue
                
                # 提交组织到数据库
                await db.commit()
                
                # 更新角色信息（供后续大纲生成使用）
                characters_info = _build_characters_info(characters)
                
                logger.info(f"✅ 【确认模式】成功创建 {len(request.confirmed_organizations)} 个用户确认的组织")
                
            except Exception as e:
                logger.error(f"⚠️ 【确认模式】创建确认组织失败: {e}", exc_info=True)
        else:
            # 根据 require_organization_confirmation 决定处理方式
            try:
                from app.services.auto_organization_service import get_auto_organization_service
                
                # 构建已有章节概览
                all_chapters_brief_for_org_analysis = _build_chapters_brief(existing_outlines)
                
                auto_org_service = get_auto_organization_service(user_ai_service)
                
                if request.require_organization_confirmation:
                    # 🔮 预测模式：仅预测组织，不自动创建，需要用户确认
                    logger.info(f"🔮 【预测模式】在生成大纲前预测是否需要新组织（需用户确认）")
                    
                    auto_result = await auto_org_service.analyze_and_create_organizations(
                        project_id=project.id,
                        outline_content="",  # 预测模式不需要大纲内容
                        existing_characters=list(characters),
                        existing_organizations=existing_organizations,
                        db=db,
                        user_id=user_id,
                        enable_mcp=request.enable_mcp,
                        all_chapters_brief=all_chapters_brief_for_org_analysis,
                        start_chapter=last_chapter_number + 1,
                        chapter_count=total_chapters_to_generate,
                        plot_stage=request.plot_stage,
                        story_direction=request.story_direction or "自然延续",
                        preview_only=True  # ✅ 仅预测不创建
                    )
                    
                    # 检查是否需要新组织
                    if auto_result.get("needs_new_organizations") and auto_result.get("predicted_organizations"):
                        predicted_count = len(auto_result["predicted_organizations"])
                        logger.warning(
                            f"⚠️ 【预测模式】AI预测需要 {predicted_count} 个新组织，需要用户确认！"
                        )
                        
                        # 🚨 抛出特殊异常，包含预测的组织信息
                        raise HTTPException(
                            status_code=449,  # 449 Retry With
                            detail={
                                "code": "ORGANIZATION_CONFIRMATION_REQUIRED",
                                "message": "续写需要引入新组织，请先确认组织信息",
                                "predicted_organizations": auto_result["predicted_organizations"],
                                "reason": auto_result.get("reason", "剧情发展需要新组织"),
                                "chapter_range": f"第{last_chapter_number + 1}-{last_chapter_number + total_chapters_to_generate}章"
                            }
                        )
                    else:
                        logger.info(f"✅ 【预测模式】AI判断无需引入新组织，继续生成大纲")
                else:
                    # 🚀 直接创建模式：预测后自动创建，无需用户确认
                    logger.info(f"🚀 【直接创建模式】在生成大纲前预测并直接创建新组织（无需确认）")
                    
                    auto_result = await auto_org_service.analyze_and_create_organizations(
                        project_id=project.id,
                        outline_content="",
                        existing_characters=list(characters),
                        existing_organizations=existing_organizations,
                        db=db,
                        user_id=user_id,
                        enable_mcp=request.enable_mcp,
                        all_chapters_brief=all_chapters_brief_for_org_analysis,
                        start_chapter=last_chapter_number + 1,
                        chapter_count=total_chapters_to_generate,
                        plot_stage=request.plot_stage,
                        story_direction=request.story_direction or "自然延续",
                        preview_only=False  # ✅ 直接创建组织
                    )
                    
                    # 如果创建了新组织，更新角色列表
                    if auto_result.get("new_organizations"):
                        new_count = len(auto_result["new_organizations"])
                        logger.info(f"✅ 【直接创建模式】自动创建了 {new_count} 个新组织")
                        
                        # 提交组织到数据库
                        await db.commit()
                        
                        # 更新角色信息（供后续大纲生成使用）
                        for org_item in auto_result["new_organizations"]:
                            org_char = org_item.get("character")
                            if org_char:
                                characters.append(org_char)
                        characters_info = _build_characters_info(characters)
                    else:
                        logger.info(f"✅ 【直接创建模式】AI判断无需引入新组织，继续生成大纲")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"⚠️ 【组织引入】预测性组织引入失败: {e}", exc_info=True)
                # 不阻断大纲生成流程
    
    # 批量生成
    all_new_outlines = []
    current_start_chapter = last_chapter_number + 1
    
    for batch_num in range(total_batches):
        # 计算当前批次的章节数
        remaining_chapters = total_chapters_to_generate - len(all_new_outlines)
        current_batch_size = min(batch_size, remaining_chapters)
        
        logger.info(f"开始生成第{batch_num + 1}/{total_batches}批，章节范围: {current_start_chapter}-{current_start_chapter + current_batch_size - 1}")
        
        # 获取最新的大纲列表（包括之前批次生成的）
        latest_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == project.id)
            .order_by(Outline.order_index)
        )
        latest_outlines = latest_result.scalars().all()
        
        # 🚀 使用智能上下文构建（支持海量大纲）
        smart_context = await _build_smart_outline_context(
            latest_outlines=latest_outlines,
            user_id=user_id,
            project_id=project.id
        )
        
        # 组装上下文字符串
        all_chapters_brief = ""
        if smart_context['story_skeleton']:
            all_chapters_brief += smart_context['story_skeleton'] + "\n\n"
        if smart_context['recent_summary']:
            all_chapters_brief += smart_context['recent_summary'] + "\n\n"
        
        # 最近详细内容作为 recent_plot
        recent_plot = smart_context['recent_detail']
        
        # 日志统计
        stats = smart_context['stats']
        logger.info(f"📊 大纲上下文统计: 总数{stats['total']}, 骨架{stats['skeleton_samples']}, "
                   f"概要{stats['recent_summaries']}, 详细{stats['recent_details']}, "
                   f"长度{stats['total_length']}字符")
        
        # 🧠 构建记忆增强上下文（仅续写模式需要）
        memory_context = None
        try:
            logger.info(f"🧠 为第{batch_num + 1}批构建记忆上下文...")
            # 使用最近一章的大纲作为查询
            query_outline = latest_outlines[-1].content if latest_outlines else ""
            memory_context = await memory_service.build_context_for_generation(
                user_id=user_id,
                project_id=project.id,
                current_chapter=current_start_chapter,
                chapter_outline=query_outline,
                character_names=[c.name for c in characters] if characters else None
            )
            logger.info(f"✅ 记忆上下文构建完成: {memory_context['stats']}")
        except Exception as e:
            logger.warning(f"⚠️ 记忆上下文构建失败，继续不使用记忆: {str(e)}")
            memory_context = None
        
        # 设置用户信息以启用MCP
        if user_id:
            user_ai_service.user_id = user_id
            user_ai_service.db_session = db
        
        # 使用标准续写提示词模板（支持记忆+MCP增强+自定义）
        template = await PromptService.get_template("OUTLINE_CONTINUE", user_id, db)
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=request.theme or project.theme or "未设定",
            genre=request.genre or project.genre or "通用",
            narrative_perspective=request.narrative_perspective,
            chapter_count=current_batch_size,  # 当前批次的章节数
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            rules=project.world_rules or "未设定",
            characters_info=characters_info or "暂无角色信息",
            current_chapter_count=len(latest_outlines),
            all_chapters_brief=all_chapters_brief,
            recent_plot=recent_plot,
            plot_stage_instruction=stage_instruction,
            start_chapter=current_start_chapter,
            end_chapter=current_start_chapter + current_batch_size - 1,
            story_direction=request.story_direction or "自然延续",
            requirements=request.requirements or "",
            memory_context=memory_context,
            mcp_references=""
        )
        
        # 调用AI生成当前批次（带重试机制）
        logger.info(f"正在调用AI流式生成第{batch_num + 1}批...")
        
        max_retries = 2
        retry_count = 0
        outline_data = None
        
        while retry_count <= max_retries:
            accumulated_text = ""
            chunk_count = 0
            
            # 第一次使用原始prompt，重试时添加格式强调
            current_prompt = prompt if retry_count == 0 else (
                prompt + "\n\n【重要提醒】请确保返回完整的JSON数组，不要截断。每个章节对象必须包含完整的title、summary等字段。"
            )
            
            async for chunk in user_ai_service.generate_text_stream(
                prompt=current_prompt,
                provider=request.provider,
                model=request.model
            ):
                chunk_count += 1
                accumulated_text += chunk
                
                # 这里是非SSE接口，不需要发送chunk
            
            ai_content = accumulated_text
            ai_response = {"content": ai_content}
            
            # 解析响应
            try:
                outline_data = _parse_ai_response(ai_content, raise_on_error=True)
                break  # 解析成功，跳出循环
                
            except JSONParseError as e:
                retry_count += 1
                if retry_count > max_retries:
                    # 超过最大重试次数，使用fallback数据
                    logger.error(f"❌ 第{batch_num + 1}批解析失败，已达最大重试次数({max_retries})，使用fallback数据")
                    outline_data = _parse_ai_response(ai_content, raise_on_error=False)
                    break
                
                logger.warning(f"⚠️ 第{batch_num + 1}批JSON解析失败（第{retry_count}次），正在重试...")
        
        # 保存当前批次的大纲
        batch_outlines = await _save_outlines(
            project.id, outline_data, db, start_index=current_start_chapter
        )
        
        # 记录历史
        history = GenerationHistory(
            project_id=project.id,
            prompt=f"[批次{batch_num + 1}/{total_batches}] {str(prompt)[:500]}",
            generated_content=json.dumps(ai_response, ensure_ascii=False) if isinstance(ai_response, dict) else ai_response,
            model=request.model or "default"
        )
        db.add(history)
        
        # 提交当前批次
        await db.commit()
        
        for outline in batch_outlines:
            await db.refresh(outline)
        
        all_new_outlines.extend(batch_outlines)
        current_start_chapter += current_batch_size
        
        logger.info(f"第{batch_num + 1}批生成完成，本批生成{len(batch_outlines)}章")
                
    
    # 返回所有大纲（包括旧的和新的）
    final_result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project.id)
        .order_by(Outline.order_index)
    )
    all_outlines = final_result.scalars().all()
    
    logger.info(f"续写完成 - 共{total_batches}批，新增 {len(all_new_outlines)} 章，总计 {len(all_outlines)} 章")
    return OutlineListResponse(total=len(all_outlines), items=all_outlines)


class JSONParseError(Exception):
    """JSON解析失败异常，用于触发重试"""
    def __init__(self, message: str, original_content: str = ""):
        super().__init__(message)
        self.original_content = original_content


def _parse_ai_response(ai_response: str, raise_on_error: bool = False) -> list:
    """
    解析AI响应为章节数据列表（使用统一的JSON清洗方法）
    
    Args:
        ai_response: AI返回的原始文本
        raise_on_error: 如果为True，解析失败时抛出异常而不是返回fallback数据
        
    Returns:
        解析后的章节数据列表
        
    Raises:
        JSONParseError: 当raise_on_error=True且解析失败时抛出
    """
    try:
        # 使用统一的JSON清洗方法（从AIService导入）
        from app.services.ai_service import AIService
        ai_service_temp = AIService()
        cleaned_text = ai_service_temp._clean_json_response(ai_response)
        
        outline_data = json.loads(cleaned_text)
        
        # 确保是列表格式
        if not isinstance(outline_data, list):
            # 如果是对象，尝试提取chapters字段
            if isinstance(outline_data, dict):
                outline_data = outline_data.get("chapters", [outline_data])
            else:
                outline_data = [outline_data]
        
        # 验证解析结果是否有效（至少有一个有效章节）
        valid_chapters = [
            ch for ch in outline_data
            if isinstance(ch, dict) and (ch.get("title") or ch.get("summary") or ch.get("content"))
        ]
        
        if not valid_chapters:
            error_msg = "解析结果无效：未找到有效的章节数据"
            logger.error(f"❌ {error_msg}")
            if raise_on_error:
                raise JSONParseError(error_msg, ai_response)
            return [{
                "title": "AI生成的大纲",
                "content": ai_response[:1000],
                "summary": ai_response[:1000]
            }]
        
        logger.info(f"✅ 成功解析 {len(valid_chapters)} 个章节数据")
        return valid_chapters
        
    except json.JSONDecodeError as e:
        error_msg = f"JSON解析失败: {e}"
        logger.error(f"❌ AI响应解析失败: {e}")
        
        if raise_on_error:
            raise JSONParseError(error_msg, ai_response)
        
        # 返回一个包含原始内容的章节
        return [{
            "title": "AI生成的大纲",
            "content": ai_response[:1000],
            "summary": ai_response[:1000]
        }]
    except JSONParseError:
        # 重新抛出JSONParseError
        raise
    except Exception as e:
        error_msg = f"解析异常: {str(e)}"
        logger.error(f"❌ {error_msg}")
        
        if raise_on_error:
            raise JSONParseError(error_msg, ai_response)
        
        return [{
            "title": "解析异常的大纲",
            "content": "系统错误",
            "summary": "系统错误"
        }]


async def _save_outlines(
    project_id: str,
    outline_data: list,
    db: AsyncSession,
    start_index: int = 1
) -> List[Outline]:
    """
    保存大纲到数据库
    
    如果项目为one-to-one模式，同时自动创建对应的章节
    """
    # 获取项目信息以确定outline_mode
    project_result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    
    outlines = []
    
    for idx, chapter_data in enumerate(outline_data):
        order_idx = chapter_data.get("chapter_number", start_index + idx)
        title = chapter_data.get("title", f"第{order_idx}章")
        
        # 优先使用summary，其次content
        content = chapter_data.get("summary") or chapter_data.get("content", "")
        
        # 如果有额外信息，添加到内容中
        if "key_events" in chapter_data:
            content += f"\n\n关键事件：" + "、".join(chapter_data["key_events"])
        if "characters_involved" in chapter_data:
            content += f"\n涉及角色：" + "、".join(chapter_data["characters_involved"])
        
        # 创建大纲
        outline = Outline(
            project_id=project_id,
            title=title,
            content=content,
            structure=json.dumps(chapter_data, ensure_ascii=False),
            order_index=order_idx
        )
        db.add(outline)
        outlines.append(outline)
    
    # 如果是one-to-one模式，自动创建章节
    if project and project.outline_mode == 'one-to-one':
        await db.flush()  # 确保大纲有ID
        
        for outline in outlines:
            await db.refresh(outline)
            
            # 为每个大纲创建对应的章节
            chapter = Chapter(
                project_id=project_id,
                title=outline.title,
                summary=outline.content,
                chapter_number=outline.order_index,
                sub_index=1,
                outline_id=None,  # one-to-one模式不关联outline_id
                status='pending',
                content=""
            )
            db.add(chapter)
        
        logger.info(f"一对一模式：为{len(outlines)}个大纲自动创建了对应的章节")
    
    return outlines


async def new_outline_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """全新生成大纲SSE生成器（MCP增强版）"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("大纲")
    
    try:
        yield await tracker.start()
        
        project_id = data.get("project_id")
        # 确保chapter_count是整数（前端可能传字符串）
        chapter_count = int(data.get("chapter_count", 10))
        enable_mcp = data.get("enable_mcp", True)
        
        # 验证项目
        yield await tracker.loading("加载项目信息...", 0.3)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        yield await tracker.loading(f"准备生成{chapter_count}章大纲...", 0.6)
        
        # 获取角色信息
        characters_result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = characters_result.scalars().all()
        characters_info = _build_characters_info(characters)
        
        # 设置用户信息以启用MCP
        user_id_for_mcp = data.get("user_id")
        if user_id_for_mcp:
            user_ai_service.user_id = user_id_for_mcp
            user_ai_service.db_session = db
        
        # 使用提示词模板
        yield await tracker.preparing("准备AI提示词...")
        template = await PromptService.get_template("OUTLINE_CREATE", user_id_for_mcp, db)
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=data.get("theme") or project.theme or "未设定",
            genre=data.get("genre") or project.genre or "通用",
            chapter_count=chapter_count,
            narrative_perspective=data.get("narrative_perspective") or "第三人称",
            target_words=data.get("target_words") or project.target_words or 100000,
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            rules=project.world_rules or "未设定",
            characters_info=characters_info or "暂无角色信息",
            requirements=data.get("requirements") or "",
            mcp_references=""
        )
        
        # 添加调试日志
        model_param = data.get("model")
        provider_param = data.get("provider")
        logger.info(f"=== 大纲生成AI调用参数 ===")
        logger.info(f"  provider参数: {provider_param}")
        logger.info(f"  model参数: {model_param}")
        
        # ✅ 流式生成（带字数统计和进度）
        estimated_total = chapter_count * 1000
        accumulated_text = ""
        chunk_count = 0
        
        yield await tracker.generating(current_chars=0, estimated_total=estimated_total)
        
        async for chunk in user_ai_service.generate_text_stream(
            prompt=prompt,
            provider=provider_param,
            model=model_param
        ):
            chunk_count += 1
            accumulated_text += chunk
            
            # 发送内容块
            yield await tracker.generating_chunk(chunk)
            
            # 定期更新进度
            if chunk_count % 10 == 0:
                yield await tracker.generating(
                    current_chars=len(accumulated_text),
                    estimated_total=estimated_total
                )
            
            # 每20个块发送心跳
            if chunk_count % 20 == 0:
                yield await tracker.heartbeat()
        
        yield await tracker.parsing("解析大纲数据...")
        
        ai_content = accumulated_text
        ai_response = {"content": ai_content}
        
        # 解析响应（带重试机制）
        max_retries = 2
        retry_count = 0
        outline_data = None
        
        while retry_count <= max_retries:
            try:
                # 使用 raise_on_error=True，解析失败时抛出异常
                outline_data = _parse_ai_response(ai_content, raise_on_error=True)
                break  # 解析成功，跳出循环
                
            except JSONParseError as e:
                retry_count += 1
                if retry_count > max_retries:
                    # 超过最大重试次数，使用fallback数据
                    logger.error(f"❌ 大纲解析失败，已达最大重试次数({max_retries})，使用fallback数据")
                    yield await tracker.warning("解析失败，使用备用数据")
                    outline_data = _parse_ai_response(ai_content, raise_on_error=False)
                    break
                
                logger.warning(f"⚠️ JSON解析失败（第{retry_count}次），正在重试...")
                yield await tracker.retry(retry_count, max_retries, "JSON解析失败")
                
                # 重试时重置生成进度
                tracker.reset_generating_progress()
                
                # 重新调用AI生成
                accumulated_text = ""
                chunk_count = 0
                
                # 在prompt中添加格式强调
                retry_prompt = prompt + "\n\n【重要提醒】请确保返回完整的JSON数组，不要截断。每个章节对象必须包含完整的title、summary等字段。"
                
                async for chunk in user_ai_service.generate_text_stream(
                    prompt=retry_prompt,
                    provider=provider_param,
                    model=model_param
                ):
                    chunk_count += 1
                    accumulated_text += chunk
                    
                    # 发送内容块
                    yield await tracker.generating_chunk(chunk)
                    
                    # 每20个块发送心跳
                    if chunk_count % 20 == 0:
                        yield await tracker.heartbeat()
                
                ai_content = accumulated_text
                ai_response = {"content": ai_content}
                logger.info(f"🔄 重试生成完成，累计{len(ai_content)}字符")
        
        # 全新生成模式：删除旧大纲和关联的所有章节
        yield await tracker.saving("清理旧大纲、章节和伏笔...", 0.2)
        logger.info(f"全新生成：删除项目 {project_id} 的旧大纲和章节（outline_mode: {project.outline_mode}）")
        
        # 清理伏笔数据
        try:
            await foreshadow_service.clear_project_foreshadows_for_reset(db, project_id)
        except Exception as e:
            logger.warning(f"清理伏笔数据失败（不影响主流程）: {str(e)}")

        from sqlalchemy import delete as sql_delete
        
        # 先获取所有旧章节并计算总字数
        old_chapters_result = await db.execute(
            select(Chapter).where(Chapter.project_id == project_id)
        )
        old_chapters = old_chapters_result.scalars().all()
        deleted_word_count = sum(ch.word_count or 0 for ch in old_chapters)
        
        # 删除所有旧章节
        delete_chapters_result = await db.execute(
            sql_delete(Chapter).where(Chapter.project_id == project_id)
        )
        deleted_chapters_count = delete_chapters_result.rowcount
        logger.info(f"✅ 全新生成：删除了 {deleted_chapters_count} 个旧章节（{deleted_word_count}字）")
        
        # 更新项目字数
        if deleted_word_count > 0:
            project.current_words = max(0, project.current_words - deleted_word_count)
            logger.info(f"更新项目字数：减少 {deleted_word_count} 字")
        
        # 再删除所有旧大纲
        delete_outlines_result = await db.execute(
            sql_delete(Outline).where(Outline.project_id == project_id)
        )
        deleted_outlines_count = delete_outlines_result.rowcount
        logger.info(f"✅ 全新生成：删除了 {deleted_outlines_count} 个旧大纲")
        
        # 保存新大纲
        yield await tracker.saving("保存大纲到数据库...", 0.6)
        outlines = await _save_outlines(
            project_id, outline_data, db, start_index=1
        )
        
        # 记录历史
        history = GenerationHistory(
            project_id=project_id,
            prompt=prompt,
            generated_content=json.dumps(ai_response, ensure_ascii=False) if isinstance(ai_response, dict) else ai_response,
            model=data.get("model") or "default"
        )
        db.add(history)
        
        await db.commit()
        db_committed = True
        
        for outline in outlines:
            await db.refresh(outline)
        
        logger.info(f"全新生成完成 - {len(outlines)} 章")
        
        yield await tracker.complete()
        
        # 发送最终结果
        yield await tracker.result({
            "message": f"成功生成{len(outlines)}章大纲",
            "total_chapters": len(outlines),
            "outlines": [
                {
                    "id": outline.id,
                    "project_id": outline.project_id,
                    "title": outline.title,
                    "content": outline.content,
                    "order_index": outline.order_index,
                    "structure": outline.structure,
                    "created_at": outline.created_at.isoformat() if outline.created_at else None,
                    "updated_at": outline.updated_at.isoformat() if outline.updated_at else None
                } for outline in outlines
            ]
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


async def continue_outline_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService,
    user_id: str = "system"
) -> AsyncGenerator[str, None]:
    """大纲续写SSE生成器 - 分批生成，推送进度（记忆+MCP增强版）"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("大纲续写")
    
    try:
        # === 初始化阶段 ===
        yield await tracker.start("开始续写大纲...")
        
        project_id = data.get("project_id")
        # 确保chapter_count是整数（前端可能传字符串）
        total_chapters_to_generate = int(data.get("chapter_count", 5))
        
        # 验证项目
        yield await tracker.loading("加载项目信息...", 0.2)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        # 获取现有大纲
        yield await tracker.loading("分析已有大纲...", 0.5)
        existing_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == project_id)
            .order_by(Outline.order_index)
        )
        existing_outlines = existing_result.scalars().all()
        
        if not existing_outlines:
            yield await tracker.error("续写模式需要已有大纲，当前项目没有大纲", 400)
            return
        
        current_chapter_count = len(existing_outlines)
        last_chapter_number = existing_outlines[-1].order_index
        
        yield await tracker.loading(
            f"当前已有{str(current_chapter_count)}章，将续写{str(total_chapters_to_generate)}章",
            0.8
        )
        
        # 获取角色信息
        characters_result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = characters_result.scalars().all()
        characters_info = _build_characters_info(characters)

        # 分批配置
        batch_size = 5
        total_batches = (total_chapters_to_generate + batch_size - 1) // batch_size
        
        # 情节阶段指导
        stage_instructions = {
            "development": "继续展开情节，深化角色关系，推进主线冲突",
            "climax": "进入故事高潮，矛盾激化，关键冲突爆发",
            "ending": "解决主要冲突，收束伏笔，给出结局"
        }
        stage_instruction = stage_instructions.get(data.get("plot_stage", "development"), "")
        
        # 🎭 【方案A】先角色后大纲：在生成大纲前预测并创建角色
        enable_auto_characters = data.get("enable_auto_characters", True)
        confirmed_characters = data.get("confirmed_characters")
        confirmed_organizations = data.get("confirmed_organizations")
        
        # === 角色引入阶段 ===
        # 🔧 判断：如果confirmed_organizations存在，说明已经是组织确认阶段，跳过角色处理
        if enable_auto_characters and not confirmed_organizations:
            # 检查是否有用户确认的角色列表
            if confirmed_characters:
                # 直接使用用户确认的角色列表创建角色
                try:
                    yield await tracker.preparing(
                        f"🎭 【确认模式】创建 {len(confirmed_characters)} 个用户确认的角色..."
                    )
                    
                    from app.services.auto_character_service import get_auto_character_service
                    
                    logger.info(f"🎭 【确认模式】用户提供了 {len(confirmed_characters)} 个确认的角色，直接创建")
                    
                    auto_char_service = get_auto_character_service(user_ai_service)
                    
                    # 🔧 去重检查：获取现有角色名称列表，避免重复创建
                    existing_character_names = {char.name for char in characters}
                    actually_created_count = 0
                    
                    for idx, char_data in enumerate(confirmed_characters):
                        try:
                            # 角色进度：11-19% (分配8%给角色创建)
                            char_progress = 11 + int((idx / max(len(confirmed_characters), 1)) * 8)
                            
                            # 检查角色是否已存在
                            char_name = char_data.get("name") or char_data.get("character_name")
                            if char_name in existing_character_names:
                                logger.warning(f"⚠️ 角色 '{char_name}' 已存在，跳过创建")
                                yield await tracker.preparing(
                                    f"⏭️ [{idx+1}/{len(confirmed_characters)}] 角色 '{char_name}' 已存在，跳过"
                                )
                                continue
                            
                            # 生成角色详细信息
                            yield await tracker.preparing(
                                f"🤖 [{idx+1}/{len(confirmed_characters)}] AI生成角色详情：{char_name}..."
                            )
                            character_data = await auto_char_service._generate_character_details(
                                spec=char_data,
                                project=project,
                                existing_characters=list(characters),
                                db=db,
                                user_id=user_id,
                                enable_mcp=data.get("enable_mcp", True)
                            )
                            
                            # 创建角色记录
                            yield await tracker.preparing(
                                f"💾 [{idx+1}/{len(confirmed_characters)}] 保存角色：{char_name}..."
                            )
                            character = await auto_char_service._create_character_record(
                                project_id=project_id,
                                character_data=character_data,
                                db=db
                            )
                            
                            # 建立关系
                            relationships_data = character_data.get("relationships") or character_data.get("relationships_array", [])
                            if relationships_data:
                                yield await tracker.preparing(
                                    f"🔗 [{idx+1}/{len(confirmed_characters)}] 建立 {len(relationships_data)} 个关系：{char_name}..."
                                )
                                await auto_char_service._create_relationships(
                                    new_character=character,
                                    relationship_specs=relationships_data,
                                    existing_characters=list(characters),
                                    project_id=project_id,
                                    db=db
                                )
                            
                            characters.append(character)
                            existing_character_names.add(character.name)  # 更新已存在的角色名称集合
                            actually_created_count += 1
                            logger.info(f"✅ 创建确认的角色: {character.name}")
                            yield await tracker.preparing(
                                f"✅ [{idx+1}/{len(confirmed_characters)}] 角色创建成功：{character.name}"
                            )
                            
                        except Exception as e:
                            logger.error(f"创建确认的角色失败: {e}", exc_info=True)
                            yield await tracker.warning(
                                f"[{idx+1}/{len(confirmed_characters)}] 角色创建失败：{char_name}"
                            )
                            continue
                    
                    # 提交角色到数据库
                    if actually_created_count > 0:
                        await db.commit()
                        yield await tracker.preparing(
                            f"✅ 【确认模式】实际创建了 {actually_created_count} 个新角色（跳过 {len(confirmed_characters) - actually_created_count} 个已存在）"
                        )
                        logger.info(f"✅ 【确认模式】实际创建了 {actually_created_count} 个新角色（跳过了 {len(confirmed_characters) - actually_created_count} 个已存在的角色）")
                    else:
                        yield await tracker.preparing(
                            f"ℹ️ 【确认模式】所有角色均已存在，无需创建"
                        )
                        logger.info(f"ℹ️ 【确认模式】所有角色均已存在，无需创建")
                    
                except Exception as e:
                    logger.error(f"⚠️ 【确认模式】创建确认角色失败: {e}", exc_info=True)
                    yield await tracker.warning("角色创建失败，继续生成大纲")
            else:
                # 根据 require_character_confirmation 决定处理方式
                require_confirmation = data.get("require_character_confirmation", True)
                
                try:
                    from app.services.auto_character_service import get_auto_character_service
                    
                    # 构建已有章节概览
                    all_chapters_brief_for_analysis = _build_chapters_brief(existing_outlines)
                    
                    auto_char_service = get_auto_character_service(user_ai_service)
                    
                    if require_confirmation:
                        # 🔮 预测模式：仅预测角色，不自动创建，需要用户确认
                        yield await tracker.preparing("🔮 【预测模式】开始分析角色需求...")
                        logger.info(f"🔮 【预测模式】在生成大纲前预测是否需要新角色")
                        
                        # 进度消息不使用回调，因为在async generator中无法嵌套yield
                        auto_result = await auto_char_service.analyze_and_create_characters(
                            project_id=project_id,
                            outline_content="",  # 预测模式不需要大纲内容
                            existing_characters=list(characters),
                            db=db,
                            user_id=user_id,
                            enable_mcp=data.get("enable_mcp", True),
                            all_chapters_brief=all_chapters_brief_for_analysis,
                            start_chapter=last_chapter_number + 1,
                            chapter_count=total_chapters_to_generate,
                            plot_stage=data.get("plot_stage", "development"),
                            story_direction=data.get("story_direction", "自然延续"),
                            preview_only=True  # ✅ 仅预测不创建
                        )
                        
                        yield await tracker.preparing("✅ 【预测模式】角色需求分析完成")
                        
                        # 检查是否需要新角色
                        if auto_result.get("needs_new_characters") and auto_result.get("predicted_characters"):
                            predicted_count = len(auto_result["predicted_characters"])
                            logger.warning(
                                f"⚠️ 【预测模式】AI预测需要 {predicted_count} 个新角色，需要用户确认！"
                            )
                            
                            # 🚨 使用专用事件类型通知前端需要角色确认
                            yield await SSEResponse.send_event(
                                event="character_confirmation_required",
                                data={
                                    "message": "续写需要引入新角色，请先确认角色信息",
                                    "predicted_characters": auto_result["predicted_characters"],
                                    "reason": auto_result.get("reason", "剧情发展需要新角色"),
                                    "chapter_range": f"第{last_chapter_number + 1}-{last_chapter_number + total_chapters_to_generate}章"
                                }
                            )
                            return
                        else:
                            yield await tracker.preparing("✅ 【预测模式】无需引入新角色，继续生成大纲")
                            logger.info(f"✅ 【预测模式】AI判断无需引入新角色")
                    else:
                        # 🚀 直接创建模式：预测后自动创建，无需用户确认
                        yield await tracker.preparing("🚀 【直接创建模式】开始分析并创建角色...")
                        logger.info(f"🚀 【直接创建模式】在生成大纲前预测并直接创建新角色")
                        
                        # 使用队列桥接回调和generator
                        import asyncio
                        progress_queue = asyncio.Queue()
                        
                        async def char_progress_callback(message):
                            await progress_queue.put(message)
                        
                        # 启动服务任务
                        char_task = asyncio.create_task(
                            auto_char_service.analyze_and_create_characters(
                                project_id=project_id,
                                outline_content="",
                                existing_characters=list(characters),
                                db=db,
                                user_id=user_id,
                                enable_mcp=data.get("enable_mcp", True),
                                all_chapters_brief=all_chapters_brief_for_analysis,
                                start_chapter=last_chapter_number + 1,
                                chapter_count=total_chapters_to_generate,
                                plot_stage=data.get("plot_stage", "development"),
                                story_direction=data.get("story_direction", "自然延续"),
                                preview_only=False,
                                progress_callback=char_progress_callback
                            )
                        )
                        
                        # 在等待任务完成的同时，消费队列中的进度消息
                        char_progress_base = 14
                        while not char_task.done():
                            try:
                                message = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                                yield await tracker.preparing(message)
                            except asyncio.TimeoutError:
                                pass
                        
                        # 获取结果
                        auto_result = await char_task
                        
                        yield await tracker.preparing("✅ 【直接创建模式】角色分析和创建完成")
                        
                        # 如果创建了新角色，更新角色列表
                        if auto_result.get("new_characters"):
                            new_count = len(auto_result["new_characters"])
                            logger.info(f"✅ 【直接创建模式】自动创建了 {new_count} 个新角色")
                            
                            yield await tracker.preparing(
                                f"✅ 【直接创建模式】自动创建了 {new_count} 个新角色"
                            )
                            
                            # 提交角色到数据库
                            await db.commit()
                            
                            # 更新角色信息（供后续大纲生成使用）
                            characters.extend(auto_result["new_characters"])
                            characters_info = _build_characters_info(characters)
                        else:
                            yield await tracker.preparing("✅ 【直接创建模式】无需引入新角色，继续生成大纲")
                            logger.info(f"✅ 【直接创建模式】AI判断无需引入新角色")
                        
                except Exception as e:
                    logger.error(f"⚠️ 【方案A】预测性角色引入失败: {e}", exc_info=True)
                    yield await tracker.warning("角色预测失败，继续生成大纲")
                    # 不阻断大纲生成流程
        
        # === 组织引入阶段 ===
        # 🏛️ 【组织引入】在生成大纲前预测并创建组织
        enable_auto_organizations = data.get("enable_auto_organizations", True)
        # confirmed_organizations在上面已经获取了，这里注释掉避免重复
        # confirmed_organizations = data.get("confirmed_organizations")
        
        if enable_auto_organizations:
            # 获取现有组织
            existing_organizations = await _get_existing_organizations(project_id, db)
            
            # 检查是否有用户确认的组织列表
            if confirmed_organizations:
                # 直接使用用户确认的组织列表创建组织
                try:
                    yield await tracker.preparing(
                        f"🏛️ 【确认模式】创建 {len(confirmed_organizations)} 个用户确认的组织..."
                    )
                    
                    from app.services.auto_organization_service import get_auto_organization_service
                    
                    logger.info(f"🏛️ 【确认模式】用户提供了 {len(confirmed_organizations)} 个确认的组织，直接创建")
                    
                    auto_org_service = get_auto_organization_service(user_ai_service)
                    
                    created_org_count = 0
                    for idx, org_data in enumerate(confirmed_organizations):
                        org_name = org_data.get("name", f"组织{idx+1}")  # 提前定义，避免异常处理中未定义
                        try:
                            # 组织进度：21-29% (分配8%给组织创建)
                            org_progress = 21 + int((idx / max(len(confirmed_organizations), 1)) * 8)
                            
                            # 生成组织详细信息
                            yield await tracker.preparing(
                                f"🤖 [{idx+1}/{len(confirmed_organizations)}] AI生成组织详情：{org_name}..."
                            )
                            organization_data = await auto_org_service._generate_organization_details(
                                spec=org_data,
                                project=project,
                                existing_characters=list(characters),
                                existing_organizations=existing_organizations,
                                db=db,
                                user_id=user_id,
                                enable_mcp=data.get("enable_mcp", True)
                            )
                            
                            # 创建组织记录
                            yield await tracker.preparing(
                                f"💾 [{idx+1}/{len(confirmed_organizations)}] 保存组织：{org_name}..."
                            )
                            org_character, organization = await auto_org_service._create_organization_record(
                                project_id=project_id,
                                organization_data=organization_data,
                                db=db
                            )
                            
                            # 建立成员关系
                            members_data = organization_data.get("initial_members", [])
                            if members_data:
                                yield await tracker.preparing(
                                    f"🔗 [{idx+1}/{len(confirmed_organizations)}] 建立 {len(members_data)} 个成员关系：{org_name}..."
                                )
                                await auto_org_service._create_member_relationships(
                                    organization=organization,
                                    member_specs=members_data,
                                    existing_characters=list(characters),
                                    project_id=project_id,
                                    db=db
                                )
                            
                            # 更新角色列表（组织也是Character）
                            characters.append(org_character)
                            existing_organizations.append({
                                "id": organization.id,
                                "name": org_character.name,
                                "organization_type": org_character.organization_type,
                                "organization_purpose": org_character.organization_purpose,
                                "power_level": organization.power_level,
                                "location": organization.location,
                                "motto": organization.motto
                            })
                            created_org_count += 1
                            logger.info(f"✅ 创建确认的组织: {org_character.name}")
                            yield await tracker.preparing(
                                f"✅ [{idx+1}/{len(confirmed_organizations)}] 组织创建成功：{org_character.name}"
                            )
                            
                        except Exception as e:
                            logger.error(f"创建确认的组织失败: {e}", exc_info=True)
                            yield await tracker.warning(
                                f"[{idx+1}/{len(confirmed_organizations)}] 组织创建失败：{org_name}"
                            )
                            continue
                    
                    # 提交组织到数据库
                    await db.commit()
                    
                    yield await tracker.preparing(
                        f"✅ 【确认模式】成功创建 {created_org_count} 个组织"
                    )
                    logger.info(f"✅ 【确认模式】成功创建 {created_org_count} 个用户确认的组织")
                    
                except Exception as e:
                    logger.error(f"⚠️ 【确认模式】创建确认组织失败: {e}", exc_info=True)
                    yield await tracker.warning("组织创建失败，继续生成大纲")
            else:
                # 根据 require_organization_confirmation 决定处理方式
                require_org_confirmation = data.get("require_organization_confirmation", True)
                
                try:
                    from app.services.auto_organization_service import get_auto_organization_service
                    
                    # 构建已有章节概览
                    all_chapters_brief_for_org_analysis = _build_chapters_brief(existing_outlines)

                    auto_org_service = get_auto_organization_service(user_ai_service)
                    
                    if require_org_confirmation:
                        # 🔮 预测模式：仅预测组织，不自动创建，需要用户确认
                        yield await tracker.preparing("🔮 【预测模式】开始分析组织需求...")
                        logger.info(f"🔮 【预测模式】在生成大纲前预测是否需要新组织")
                        
                        auto_result = await auto_org_service.analyze_and_create_organizations(
                            project_id=project_id,
                            outline_content="",  # 预测模式不需要大纲内容
                            existing_characters=list(characters),
                            existing_organizations=existing_organizations,
                            db=db,
                            user_id=user_id,
                            enable_mcp=data.get("enable_mcp", True),
                            all_chapters_brief=all_chapters_brief_for_org_analysis,
                            start_chapter=last_chapter_number + 1,
                            chapter_count=total_chapters_to_generate,
                            plot_stage=data.get("plot_stage", "development"),
                            story_direction=data.get("story_direction", "自然延续"),
                            preview_only=True  # ✅ 仅预测不创建
                        )
                        
                        yield await tracker.preparing("✅ 【预测模式】组织需求分析完成")
                        
                        # 检查是否需要新组织
                        if auto_result.get("needs_new_organizations") and auto_result.get("predicted_organizations"):
                            predicted_count = len(auto_result["predicted_organizations"])
                            logger.warning(
                                f"⚠️ 【预测模式】AI预测需要 {predicted_count} 个新组织，需要用户确认！"
                            )
                            
                            # 🚨 使用专用事件类型通知前端需要组织确认
                            yield await SSEResponse.send_event(
                                event="organization_confirmation_required",
                                data={
                                    "message": "续写需要引入新组织，请先确认组织信息",
                                    "predicted_organizations": auto_result["predicted_organizations"],
                                    "reason": auto_result.get("reason", "剧情发展需要新组织"),
                                    "chapter_range": f"第{last_chapter_number + 1}-{last_chapter_number + total_chapters_to_generate}章"
                                }
                            )
                            return
                        else:
                            yield await tracker.preparing("✅ 【预测模式】无需引入新组织，继续生成大纲")
                            logger.info(f"✅ 【预测模式】AI判断无需引入新组织")
                    else:
                        # 🚀 直接创建模式：预测后自动创建，无需用户确认
                        yield await tracker.preparing("🚀 【直接创建模式】开始分析并创建组织...")
                        logger.info(f"🚀 【直接创建模式】在生成大纲前预测并直接创建新组织")
                        
                        # 使用队列桥接回调和generator
                        import asyncio
                        org_progress_queue = asyncio.Queue()
                        
                        async def org_progress_callback(message):
                            await org_progress_queue.put(message)
                        
                        # 启动服务任务
                        org_task = asyncio.create_task(
                            auto_org_service.analyze_and_create_organizations(
                                project_id=project_id,
                                outline_content="",
                                existing_characters=list(characters),
                                existing_organizations=existing_organizations,
                                db=db,
                                user_id=user_id,
                                enable_mcp=data.get("enable_mcp", True),
                                all_chapters_brief=all_chapters_brief_for_org_analysis,
                                start_chapter=last_chapter_number + 1,
                                chapter_count=total_chapters_to_generate,
                                plot_stage=data.get("plot_stage", "development"),
                                story_direction=data.get("story_direction", "自然延续"),
                                preview_only=False,
                                progress_callback=org_progress_callback
                            )
                        )
                        
                        # 在等待任务完成的同时，消费队列中的进度消息
                        org_progress_base = 24
                        while not org_task.done():
                            try:
                                message = await asyncio.wait_for(org_progress_queue.get(), timeout=0.1)
                                yield await tracker.preparing(message)
                            except asyncio.TimeoutError:
                                pass
                        
                        # 获取结果
                        auto_result = await org_task
                        
                        yield await tracker.preparing("✅ 【直接创建模式】组织分析和创建完成")
                        
                        # 如果创建了新组织，更新角色列表
                        if auto_result.get("new_organizations"):
                            new_count = len(auto_result["new_organizations"])
                            new_org_names = []
                            for org_item in auto_result["new_organizations"]:
                                org_char = org_item.get("character")
                                if org_char:
                                    new_org_names.append(org_char.name)
                            logger.info(f"✅ 【直接创建模式】自动创建了 {new_count} 个新组织")
                            
                            yield await tracker.preparing(
                                f"✅ 【直接创建模式】成功创建 {new_count} 个新组织：{', '.join(new_org_names[:3])}{'...' if new_count > 3 else ''}"
                            )
                            
                            # 提交组织到数据库
                            await db.commit()
                            
                            # 更新角色信息（供后续大纲生成使用）
                            for org_item in auto_result["new_organizations"]:
                                org_char = org_item.get("character")
                                if org_char:
                                    characters.append(org_char)
                            characters_info = _build_characters_info(characters)
                        else:
                            yield await tracker.preparing("✅ 【直接创建模式】无需引入新组织，继续生成大纲")
                            logger.info(f"✅ 【直接创建模式】AI判断无需引入新组织")
                        
                except Exception as e:
                    logger.error(f"⚠️ 【组织引入】预测性组织引入失败: {e}", exc_info=True)
                    yield await tracker.warning("组织预测失败，继续生成大纲")
                    # 不阻断大纲生成流程
        
        # === 批次生成阶段 ===
        all_new_outlines = []
        current_start_chapter = last_chapter_number + 1
        
        for batch_num in range(total_batches):
            # 计算当前批次的章节数
            remaining_chapters = int(total_chapters_to_generate) - len(all_new_outlines)
            current_batch_size = min(batch_size, remaining_chapters)
            
            # 每批使用的进度预估
            estimated_chars_per_batch = current_batch_size * 1000
            
            # 重置生成进度以便于每批独立计算
            tracker.reset_generating_progress()
            
            yield await tracker.generating(
                current_chars=0,
                estimated_total=estimated_chars_per_batch,
                message=f"📝 第{str(batch_num + 1)}/{str(total_batches)}批: 生成第{str(current_start_chapter)}-{str(current_start_chapter + current_batch_size - 1)}章"
            )
            
            # 获取最新的大纲列表（包括之前批次生成的）
            latest_result = await db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.order_index)
            )
            latest_outlines = latest_result.scalars().all()
            
            # 🚀 使用智能上下文构建（支持海量大纲）
            smart_context = await _build_smart_outline_context(
                latest_outlines=latest_outlines,
                user_id=user_id,
                project_id=project_id
            )
            
            # 组装上下文字符串
            all_chapters_brief = ""
            if smart_context['story_skeleton']:
                all_chapters_brief += smart_context['story_skeleton'] + "\n\n"
            if smart_context['recent_summary']:
                all_chapters_brief += smart_context['recent_summary'] + "\n\n"
            
            # 最近详细内容作为 recent_plot
            recent_plot = smart_context['recent_detail']
            
            # 日志统计
            stats = smart_context['stats']
            logger.info(f"📊 批次{batch_num + 1}大纲上下文: 总数{stats['total']}, "
                       f"骨架{stats['skeleton_samples']}, 概要{stats['recent_summaries']}, "
                       f"详细{stats['recent_details']}, 长度{stats['total_length']}字符")
            
            # 🧠 构建记忆增强上下文
            memory_context = None
            try:
                yield await tracker.generating(
                    current_chars=0,
                    estimated_total=estimated_chars_per_batch,
                    message="🧠 构建记忆上下文..."
                )
                query_outline = latest_outlines[-1].content if latest_outlines else ""
                memory_context = await memory_service.build_context_for_generation(
                    user_id=user_id,
                    project_id=project_id,
                    current_chapter=current_start_chapter,
                    chapter_outline=query_outline,
                    character_names=[c.name for c in characters] if characters else None
                )
                logger.info(f"✅ 记忆上下文: {memory_context['stats']}")
            except Exception as e:
                logger.warning(f"⚠️ 记忆上下文构建失败: {str(e)}")
                memory_context = None
            # 设置用户信息以启用MCP
            if user_id:
                user_ai_service.user_id = user_id
                user_ai_service.db_session = db
            
            yield await tracker.generating(
                current_chars=0,
                estimated_total=estimated_chars_per_batch,
                message=f"🤖 调用AI生成第{str(batch_num + 1)}批..."
            )
            
            # 使用标准续写提示词模板（支持记忆+MCP增强+自定义）
            template = await PromptService.get_template("OUTLINE_CONTINUE", user_id, db)
            prompt = PromptService.format_prompt(
                template,
                title=project.title,
                theme=data.get("theme") or project.theme or "未设定",
                genre=data.get("genre") or project.genre or "通用",
                narrative_perspective=data.get("narrative_perspective") or project.narrative_perspective or "第三人称",
                chapter_count=current_batch_size,
                time_period=project.world_time_period or "未设定",
                location=project.world_location or "未设定",
                atmosphere=project.world_atmosphere or "未设定",
                rules=project.world_rules or "未设定",
                characters_info=characters_info or "暂无角色信息",
                current_chapter_count=len(latest_outlines),
                all_chapters_brief=all_chapters_brief,
                recent_plot=recent_plot,
                plot_stage_instruction=stage_instruction,
                start_chapter=current_start_chapter,
                end_chapter=current_start_chapter + current_batch_size - 1,
                story_direction=data.get("story_direction", "自然延续"),
                requirements=data.get("requirements", ""),
                memory_context=memory_context,
                mcp_references=""
            )
            
            # 调用AI生成当前批次
            model_param = data.get("model")
            provider_param = data.get("provider")
            logger.info(f"=== 续写批次{batch_num + 1} AI调用参数 ===")
            logger.info(f"  provider参数: {provider_param}")
            logger.info(f"  model参数: {model_param}")
            
            # 流式生成并累积文本
            accumulated_text = ""
            chunk_count = 0
            
            async for chunk in user_ai_service.generate_text_stream(
                prompt=prompt,
                provider=provider_param,
                model=model_param
            ):
                chunk_count += 1
                accumulated_text += chunk
                
                # 发送内容块
                yield await tracker.generating_chunk(chunk)
                
                # 定期更新进度
                if chunk_count % 10 == 0:
                    yield await tracker.generating(
                        current_chars=len(accumulated_text),
                        estimated_total=estimated_chars_per_batch,
                        message=f"📝 第{str(batch_num + 1)}/{str(total_batches)}批生成中"
                    )
                
                # 每20个块发送心跳
                if chunk_count % 20 == 0:
                    yield await tracker.heartbeat()
            
            yield await tracker.parsing(f"✅ 第{str(batch_num + 1)}批AI生成完成，正在解析...")
            
            # 提取内容
            ai_content = accumulated_text
            ai_response = {"content": ai_content}
            
            # 解析响应（带重试机制）
            max_retries = 2
            retry_count = 0
            outline_data = None
            
            while retry_count <= max_retries:
                try:
                    # 使用 raise_on_error=True，解析失败时抛出异常
                    outline_data = _parse_ai_response(ai_content, raise_on_error=True)
                    break  # 解析成功，跳出循环
                    
                except JSONParseError as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        # 超过最大重试次数，使用fallback数据
                        logger.error(f"❌ 第{batch_num + 1}批解析失败，已达最大重试次数({max_retries})，使用fallback数据")
                        yield await tracker.warning(f"第{str(batch_num + 1)}批解析失败，使用备用数据")
                        outline_data = _parse_ai_response(ai_content, raise_on_error=False)
                        break
                    
                    logger.warning(f"⚠️ 第{batch_num + 1}批JSON解析失败（第{retry_count}次），正在重试...")
                    yield await tracker.retry(retry_count, max_retries, f"第{str(batch_num + 1)}批解析失败")
                    
                    # 重试时重置生成进度
                    tracker.reset_generating_progress()
                    
                    # 重新调用AI生成
                    accumulated_text = ""
                    chunk_count = 0
                    
                    # 在prompt中添加格式强调
                    retry_prompt = prompt + "\n\n【重要提醒】请确保返回完整的JSON数组，不要截断。每个章节对象必须包含完整的title、summary等字段。"
                    
                    async for chunk in user_ai_service.generate_text_stream(
                        prompt=retry_prompt,
                        provider=provider_param,
                        model=model_param
                    ):
                        chunk_count += 1
                        accumulated_text += chunk
                        
                        # 发送内容块
                        yield await tracker.generating_chunk(chunk)
                        
                        # 每20个块发送心跳
                        if chunk_count % 20 == 0:
                            yield await tracker.heartbeat()
                    
                    ai_content = accumulated_text
                    ai_response = {"content": ai_content}
                    logger.info(f"🔄 第{batch_num + 1}批重试生成完成，累计{len(ai_content)}字符")
            
            # 保存当前批次的大纲
            batch_outlines = await _save_outlines(
                project_id, outline_data, db, start_index=current_start_chapter
            )
            
            # 记录历史
            history = GenerationHistory(
                project_id=project_id,
                prompt=f"[续写批次{batch_num + 1}/{total_batches}] {str(prompt)[:500]}",
                generated_content=json.dumps(ai_response, ensure_ascii=False) if isinstance(ai_response, dict) else ai_response,
                model=data.get("model") or "default"
            )
            db.add(history)
            
            # 提交当前批次
            await db.commit()
            
            for outline in batch_outlines:
                await db.refresh(outline)
            
            all_new_outlines.extend(batch_outlines)
            current_start_chapter += current_batch_size
            
            yield await tracker.saving(
                f"💾 第{str(batch_num + 1)}批保存成功！本批生成{str(len(batch_outlines))}章，累计新增{str(len(all_new_outlines))}章",
                (batch_num + 1) / total_batches
            )
            
            logger.info(f"第{str(batch_num + 1)}批生成完成，本批生成{str(len(batch_outlines))}章")
        
        db_committed = True
        
        # 返回所有大纲（包括旧的和新的）
        final_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == project_id)
            .order_by(Outline.order_index)
        )
        all_outlines = final_result.scalars().all()
        
        yield await tracker.complete()
        
        # 发送最终结果
        yield await tracker.result({
            "message": f"续写完成！共{str(total_batches)}批，新增{str(len(all_new_outlines))}章，总计{str(len(all_outlines))}章",
            "total_batches": total_batches,
            "new_chapters": len(all_new_outlines),
            "total_chapters": len(all_outlines),
            "outlines": [
                {
                    "id": outline.id,
                    "project_id": outline.project_id,
                    "title": outline.title,
                    "content": outline.content,
                    "order_index": outline.order_index,
                    "structure": outline.structure,
                    "created_at": outline.created_at.isoformat() if outline.created_at else None,
                    "updated_at": outline.updated_at.isoformat() if outline.updated_at else None
                } for outline in all_outlines
            ]
        })
        
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("大纲续写生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲续写事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"大纲续写失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲续写事务已回滚（异常）")
        yield await tracker.error(f"续写失败: {str(e)}")


@router.post("/generate-stream", summary="AI生成/续写大纲(SSE流式)")
async def generate_outline_stream(
    data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成或续写小说大纲，实时推送批次进度
    
    支持模式：
    - auto: 自动判断（无大纲→新建，有大纲→续写）
    - new: 全新生成
    - continue: 续写模式
    
    请求体示例：
    {
        "project_id": "项目ID",
        "chapter_count": 5,  // 章节数
        "mode": "auto",  // auto/new/continue
        "theme": "故事主题",  // new模式必需
        "story_direction": "故事发展方向",  // continue模式可选
        "plot_stage": "development",  // continue模式：development/climax/ending
        "narrative_perspective": "第三人称",
        "requirements": "其他要求",
        "provider": "openai",  // 可选
        "model": "gpt-4"  // 可选
    }
    """
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    project = await verify_project_access(data.get("project_id"), user_id, db)
    
    # 判断模式
    mode = data.get("mode", "auto")
    
    # 获取现有大纲
    existing_result = await db.execute(
        select(Outline)
        .where(Outline.project_id == data.get("project_id"))
        .order_by(Outline.order_index)
    )
    existing_outlines = existing_result.scalars().all()
    
    # 自动判断模式
    if mode == "auto":
        mode = "continue" if existing_outlines else "new"
        logger.info(f"自动判断模式：{'续写' if existing_outlines else '新建'}")
    
    # 获取用户ID
    user_id = getattr(request.state, "user_id", "system")
    
    # 根据模式选择生成器
    if mode == "new":
        return create_sse_response(new_outline_generator(data, db, user_ai_service))
    elif mode == "continue":
        if not existing_outlines:
            raise HTTPException(
                status_code=400,
                detail="续写模式需要已有大纲，当前项目没有大纲"
            )
        return create_sse_response(continue_outline_generator(data, db, user_ai_service, user_id))
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的模式: {mode}"
        )


async def expand_outline_generator(
    outline_id: str,
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """单个大纲展开SSE生成器 - 实时推送进度（支持分批生成）"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("大纲展开")
    
    try:
        yield await tracker.start()
        
        target_chapter_count = int(data.get("target_chapter_count", 3))
        expansion_strategy = data.get("expansion_strategy", "balanced")
        enable_scene_analysis = data.get("enable_scene_analysis", True)
        auto_create_chapters = data.get("auto_create_chapters", False)
        batch_size = int(data.get("batch_size", 5))  # 支持自定义批次大小
        
        # 获取大纲
        yield await tracker.loading("加载大纲信息...", 0.3)
        result = await db.execute(
            select(Outline).where(Outline.id == outline_id)
        )
        outline = result.scalar_one_or_none()
        
        if not outline:
            yield await tracker.error("大纲不存在", 404)
            return
        
        # 获取项目信息
        yield await tracker.loading("加载项目信息...", 0.7)
        project_result = await db.execute(
            select(Project).where(Project.id == outline.project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        yield await tracker.preparing(
            f"准备展开《{outline.title}》为 {target_chapter_count} 章..."
        )
        
        # 创建展开服务实例
        expansion_service = PlotExpansionService(user_ai_service)
        
        # 分析大纲并生成章节规划（支持分批）
        if target_chapter_count > batch_size:
            yield await tracker.generating(
                current_chars=0,
                estimated_total=target_chapter_count * 500,
                message=f"🤖 AI分批生成章节规划（每批{batch_size}章）..."
            )
        else:
            yield await tracker.generating(
                current_chars=0,
                estimated_total=target_chapter_count * 500,
                message="🤖 AI分析大纲，生成章节规划..."
            )
        
        chapter_plans = await expansion_service.analyze_outline_for_chapters(
            outline=outline,
            project=project,
            db=db,
            target_chapter_count=target_chapter_count,
            expansion_strategy=expansion_strategy,
            enable_scene_analysis=enable_scene_analysis,
            provider=data.get("provider"),
            model=data.get("model"),
            batch_size=batch_size,
            progress_callback=None  # SSE中暂不支持嵌套回调
        )
        
        if not chapter_plans:
            yield await tracker.error("AI分析失败，未能生成章节规划", 500)
            return
        
        yield await tracker.parsing(
            f"✅ 规划生成完成！共 {len(chapter_plans)} 个章节"
        )
        
        # 根据配置决定是否创建章节记录
        created_chapters = None
        if auto_create_chapters:
            yield await tracker.saving("💾 创建章节记录...", 0.3)
            
            created_chapters = await expansion_service.create_chapters_from_plans(
                outline_id=outline_id,
                chapter_plans=chapter_plans,
                project_id=outline.project_id,
                db=db,
                start_chapter_number=None  # 自动计算章节序号
            )
            
            await db.commit()
            db_committed = True
            
            # 刷新章节数据
            for chapter in created_chapters:
                await db.refresh(chapter)
            
            yield await tracker.saving(
                f"✅ 成功创建 {len(created_chapters)} 个章节记录",
                0.8
            )
        
        yield await tracker.complete()
        
        # 构建响应数据
        result_data = {
            "outline_id": outline_id,
            "outline_title": outline.title,
            "target_chapter_count": target_chapter_count,
            "actual_chapter_count": len(chapter_plans),
            "expansion_strategy": expansion_strategy,
            "chapter_plans": chapter_plans,
            "created_chapters": [
                {
                    "id": ch.id,
                    "chapter_number": ch.chapter_number,
                    "title": ch.title,
                    "summary": ch.summary,
                    "outline_id": ch.outline_id,
                    "sub_index": ch.sub_index,
                    "status": ch.status
                }
                for ch in created_chapters
            ] if created_chapters else None
        }
        
        yield await tracker.result(result_data)
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("大纲展开生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲展开事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"大纲展开失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲展开事务已回滚（异常）")
        yield await tracker.error(f"展开失败: {str(e)}")


@router.post("/{outline_id}/create-single-chapter", summary="一对一创建章节(传统模式)")
async def create_single_chapter_from_outline(
    outline_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    传统模式：一个大纲对应创建一个章节
    
    适用场景：
    - 项目的outline_mode为'one-to-one'
    - 直接将大纲内容作为章节摘要
    - 不调用AI，不展开
    
    流程：
    1. 验证项目模式为one-to-one
    2. 检查该大纲是否已创建章节
    3. 创建章节记录（outline_id=NULL，chapter_number=outline.order_index）
    
    返回：创建的章节信息
    """
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    
    # 获取大纲
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证项目权限并获取项目信息
    project = await verify_project_access(outline.project_id, user_id, db)
    
    # 验证项目模式
    if project.outline_mode != 'one-to-one':
        raise HTTPException(
            status_code=400,
            detail=f"当前项目为{project.outline_mode}模式，不支持一对一创建。请使用展开功能。"
        )
    
    # 检查该大纲对应的章节是否已存在
    existing_chapter_result = await db.execute(
        select(Chapter).where(
            Chapter.project_id == outline.project_id,
            Chapter.chapter_number == outline.order_index,
            Chapter.sub_index == 1
        )
    )
    existing_chapter = existing_chapter_result.scalar_one_or_none()
    
    if existing_chapter:
        raise HTTPException(
            status_code=400,
            detail=f"第{outline.order_index}章已存在，不能重复创建"
        )
    
    try:
        # 创建章节（outline_id=NULL表示一对一模式）
        new_chapter = Chapter(
            project_id=outline.project_id,
            title=outline.title,
            summary=outline.content,  # 使用大纲内容作为摘要
            chapter_number=outline.order_index,
            sub_index=1,  # 一对一模式固定为1
            outline_id=None,  # 传统模式不关联outline_id
            status='pending'
        )
        
        db.add(new_chapter)
        await db.commit()
        await db.refresh(new_chapter)
        
        logger.info(f"一对一模式：为大纲 {outline.title} 创建章节 {new_chapter.chapter_number}")
        
        return {
            "message": "章节创建成功",
            "chapter": {
                "id": new_chapter.id,
                "project_id": new_chapter.project_id,
                "title": new_chapter.title,
                "summary": new_chapter.summary,
                "chapter_number": new_chapter.chapter_number,
                "sub_index": new_chapter.sub_index,
                "outline_id": new_chapter.outline_id,
                "status": new_chapter.status,
                "created_at": new_chapter.created_at.isoformat() if new_chapter.created_at else None
            }
        }
        
    except Exception as e:
        logger.error(f"一对一创建章节失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建章节失败: {str(e)}")


@router.post("/{outline_id}/expand-stream", summary="展开单个大纲为多章(SSE流式)")
async def expand_outline_to_chapters_stream(
    outline_id: str,
    data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式展开单个大纲，实时推送进度
    
    请求体示例：
    {
        "target_chapter_count": 3,  // 目标章节数
        "expansion_strategy": "balanced",  // balanced/climax/detail
        "auto_create_chapters": false,  // 是否自动创建章节
        "enable_scene_analysis": true,  // 是否启用场景分析
        "provider": "openai",  // 可选
        "model": "gpt-4"  // 可选
    }
    
    进度阶段：
    - 5% - 开始展开
    - 10% - 加载大纲信息
    - 15% - 加载项目信息
    - 20% - 准备展开参数
    - 30% - AI分析大纲（耗时）
    - 70% - 规划生成完成
    - 80% - 创建章节记录（如果auto_create_chapters=True）
    - 90% - 创建完成
    - 95% - 整理结果数据
    - 100% - 全部完成
    """
    # 获取大纲并验证权限
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(outline.project_id, user_id, db)
    
    return create_sse_response(expand_outline_generator(outline_id, data, db, user_ai_service))


@router.get("/{outline_id}/chapters", summary="获取大纲关联的章节")
async def get_outline_chapters(
    outline_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定大纲已展开的章节列表
    
    用于检查大纲是否已经展开过,如果有则返回章节信息
    """
    # 获取大纲
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(outline.project_id, user_id, db)
    
    # 查询该大纲关联的章节
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.outline_id == outline_id)
        .order_by(Chapter.sub_index)
    )
    chapters = chapters_result.scalars().all()
    
    # 如果有章节,解析展开规划
    expansion_plans = []
    if chapters:
        for chapter in chapters:
            plan_data = None
            if chapter.expansion_plan:
                try:
                    plan_data = json.loads(chapter.expansion_plan)
                except json.JSONDecodeError:
                    logger.warning(f"章节 {chapter.id} 的expansion_plan解析失败")
                    plan_data = None
            
            expansion_plans.append({
                "sub_index": chapter.sub_index,
                "title": chapter.title,
                "plot_summary": chapter.summary or "",
                "key_events": plan_data.get("key_events", []) if plan_data else [],
                "character_focus": plan_data.get("character_focus", []) if plan_data else [],
                "emotional_tone": plan_data.get("emotional_tone", "") if plan_data else "",
                "narrative_goal": plan_data.get("narrative_goal", "") if plan_data else "",
                "conflict_type": plan_data.get("conflict_type", "") if plan_data else "",
                "estimated_words": plan_data.get("estimated_words", 0) if plan_data else 0,
                "scenes": plan_data.get("scenes") if plan_data else None
            })
    
    return {
        "has_chapters": len(chapters) > 0,
        "outline_id": outline_id,
        "outline_title": outline.title,
        "chapter_count": len(chapters),
        "chapters": [
            {
                "id": ch.id,
                "chapter_number": ch.chapter_number,
                "title": ch.title,
                "summary": ch.summary,
                "sub_index": ch.sub_index,
                "status": ch.status,
                "word_count": ch.word_count
            }
            for ch in chapters
        ],
        "expansion_plans": expansion_plans if expansion_plans else None
    }


async def batch_expand_outlines_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """批量展开大纲SSE生成器 - 实时推送进度"""
    db_committed = False
    # 初始化标准进度追踪器
    tracker = WizardProgressTracker("批量大纲展开")
    
    try:
        yield await tracker.start()
        
        project_id = data.get("project_id")
        chapters_per_outline = int(data.get("chapters_per_outline", 3))
        expansion_strategy = data.get("expansion_strategy", "balanced")
        auto_create_chapters = data.get("auto_create_chapters", False)
        outline_ids = data.get("outline_ids")
        
        # 获取项目信息
        yield await tracker.loading("加载项目信息...", 0.5)
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            yield await tracker.error("项目不存在", 404)
            return
        
        # 获取要展开的大纲列表
        yield await tracker.loading("获取大纲列表...", 0.8)
        if outline_ids:
            outlines_result = await db.execute(
                select(Outline)
                .where(
                    Outline.project_id == project_id,
                    Outline.id.in_(outline_ids)
                )
                .order_by(Outline.order_index)
            )
        else:
            outlines_result = await db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.order_index)
            )
        
        outlines = outlines_result.scalars().all()
        
        if not outlines:
            yield await tracker.error("没有找到要展开的大纲", 404)
            return
        
        total_outlines = len(outlines)
        yield await tracker.preparing(
            f"共找到 {total_outlines} 个大纲，开始批量展开..."
        )
        
        # 创建展开服务实例
        expansion_service = PlotExpansionService(user_ai_service)
        
        expansion_results = []
        total_chapters_created = 0
        skipped_outlines = []
        
        for idx, outline in enumerate(outlines):
            try:
                # 计算当前子进度 (0.0-1.0)，用于generating阶段
                sub_progress = idx / max(total_outlines, 1)
                
                yield await tracker.generating(
                    current_chars=idx * chapters_per_outline * 500,
                    estimated_total=total_outlines * chapters_per_outline * 500,
                    message=f"📝 处理第 {idx + 1}/{total_outlines} 个大纲: {outline.title}"
                )
                
                # 检查大纲是否已经展开过
                existing_chapters_result = await db.execute(
                    select(Chapter)
                    .where(Chapter.outline_id == outline.id)
                    .limit(1)
                )
                existing_chapter = existing_chapters_result.scalar_one_or_none()
                
                if existing_chapter:
                    logger.info(f"大纲 {outline.title} (ID: {outline.id}) 已经展开过，跳过")
                    skipped_outlines.append({
                        "outline_id": outline.id,
                        "outline_title": outline.title,
                        "reason": "已展开"
                    })
                    yield await tracker.generating(
                        current_chars=(idx + 1) * chapters_per_outline * 500,
                        estimated_total=total_outlines * chapters_per_outline * 500,
                        message=f"⏭️ {outline.title} 已展开过，跳过"
                    )
                    continue
                
                # 分析大纲生成章节规划
                yield await tracker.generating(
                    current_chars=idx * chapters_per_outline * 500,
                    estimated_total=total_outlines * chapters_per_outline * 500,
                    message=f"🤖 AI分析大纲: {outline.title}"
                )
                
                chapter_plans = await expansion_service.analyze_outline_for_chapters(
                    outline=outline,
                    project=project,
                    db=db,
                    target_chapter_count=chapters_per_outline,
                    expansion_strategy=expansion_strategy,
                    enable_scene_analysis=data.get("enable_scene_analysis", True),
                    provider=data.get("provider"),
                    model=data.get("model")
                )
                
                yield await tracker.generating(
                    current_chars=(idx + 0.5) * chapters_per_outline * 500,
                    estimated_total=total_outlines * chapters_per_outline * 500,
                    message=f"✅ {outline.title} 规划生成完成 ({len(chapter_plans)} 章)"
                )
                
                created_chapters = None
                if auto_create_chapters:
                    # 创建章节记录
                    chapters = await expansion_service.create_chapters_from_plans(
                        outline_id=outline.id,
                        chapter_plans=chapter_plans,
                        project_id=outline.project_id,
                        db=db,
                        start_chapter_number=None  # 自动计算章节序号
                    )
                    created_chapters = [
                        {
                            "id": ch.id,
                            "chapter_number": ch.chapter_number,
                            "title": ch.title,
                            "summary": ch.summary,
                            "outline_id": ch.outline_id,
                            "sub_index": ch.sub_index,
                            "status": ch.status
                        }
                        for ch in chapters
                    ]
                    total_chapters_created += len(chapters)
                    
                    yield await tracker.generating(
                        current_chars=(idx + 1) * chapters_per_outline * 500,
                        estimated_total=total_outlines * chapters_per_outline * 500,
                        message=f"💾 {outline.title} 章节创建完成 ({len(chapters)} 章)"
                    )
                
                expansion_results.append({
                    "outline_id": outline.id,
                    "outline_title": outline.title,
                    "target_chapter_count": chapters_per_outline,
                    "actual_chapter_count": len(chapter_plans),
                    "expansion_strategy": expansion_strategy,
                    "chapter_plans": chapter_plans,
                    "created_chapters": created_chapters
                })
                
                logger.info(f"大纲 {outline.title} 展开完成，生成 {len(chapter_plans)} 个章节规划")
                
            except Exception as e:
                logger.error(f"展开大纲 {outline.id} 失败: {str(e)}", exc_info=True)
                yield await tracker.warning(
                    f"❌ {outline.title} 展开失败: {str(e)}"
                )
                expansion_results.append({
                    "outline_id": outline.id,
                    "outline_title": outline.title,
                    "target_chapter_count": chapters_per_outline,
                    "actual_chapter_count": 0,
                    "expansion_strategy": expansion_strategy,
                    "chapter_plans": [],
                    "created_chapters": None,
                    "error": str(e)
                })
        
        yield await tracker.parsing("整理结果数据...")
        
        db_committed = True
        
        logger.info(f"批量展开完成: {len(expansion_results)} 个大纲，跳过 {len(skipped_outlines)} 个，共生成 {total_chapters_created} 个章节")
        
        yield await tracker.complete()
        
        # 发送最终结果
        result_data = {
            "project_id": project_id,
            "total_outlines_expanded": len(expansion_results),
            "total_chapters_created": total_chapters_created,
            "skipped_count": len(skipped_outlines),
            "skipped_outlines": skipped_outlines,
            "expansion_results": [
                {
                    "outline_id": result["outline_id"],
                    "outline_title": result["outline_title"],
                    "target_chapter_count": result["target_chapter_count"],
                    "actual_chapter_count": result["actual_chapter_count"],
                    "expansion_strategy": result["expansion_strategy"],
                    "chapter_plans": result["chapter_plans"],
                    "created_chapters": result.get("created_chapters")
                }
                for result in expansion_results
            ]
        }
        
        yield await tracker.result(result_data)
        yield await tracker.done()
        
    except GeneratorExit:
        logger.warning("批量展开生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("批量展开事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"批量展开失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("批量展开事务已回滚（异常）")
        yield await SSEResponse.send_error(f"批量展开失败: {str(e)}")


@router.post("/batch-expand-stream", summary="批量展开大纲为多章(SSE流式)")
async def batch_expand_outlines_stream(
    data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式批量展开大纲，实时推送每个大纲的处理进度
    
    请求体示例：
    {
        "project_id": "项目ID",
        "outline_ids": ["大纲ID1", "大纲ID2"],  // 可选，不传则展开所有大纲
        "chapters_per_outline": 3,  // 每个大纲展开几章
        "expansion_strategy": "balanced",  // balanced/climax/detail
        "auto_create_chapters": false,  // 是否自动创建章节
        "enable_scene_analysis": true,  // 是否启用场景分析
        "provider": "openai",  // 可选
        "model": "gpt-4"  // 可选
    }
    """
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(data.get("project_id"), user_id, db)
    
    return create_sse_response(batch_expand_outlines_generator(data, db, user_ai_service))


@router.post("/{outline_id}/create-chapters-from-plans", response_model=CreateChaptersFromPlansResponse, summary="根据已有规划创建章节")
async def create_chapters_from_existing_plans(
    outline_id: str,
    plans_request: CreateChaptersFromPlansRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    根据前端缓存的章节规划直接创建章节记录，避免重复调用AI
    
    使用场景：
    1. 用户第一次调用 /outlines/{outline_id}/expand?auto_create_chapters=false 获取规划预览
    2. 前端展示规划给用户确认
    3. 用户确认后，前端调用此接口，传递缓存的规划数据，直接创建章节
    
    优势：
    - 避免重复的AI调用，节省Token和时间
    - 确保用户看到的预览和实际创建的章节完全一致
    - 提升用户体验
    
    参数：
    - outline_id: 要展开的大纲ID
    - plans_request: 包含之前AI生成的章节规划列表
    
    返回：
    - 创建的章节列表和统计信息
    """
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    
    # 获取大纲
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 验证项目权限
    await verify_project_access(outline.project_id, user_id, db)
    
    try:
        # 验证规划数据
        if not plans_request.chapter_plans:
            raise HTTPException(status_code=400, detail="章节规划列表不能为空")
        
        logger.info(f"根据已有规划为大纲 {outline_id} 创建 {len(plans_request.chapter_plans)} 个章节")
        
        # 创建展开服务实例
        expansion_service = PlotExpansionService(user_ai_service)
        
        # 将Pydantic模型转换为字典列表
        chapter_plans_dict = [plan.model_dump() for plan in plans_request.chapter_plans]
        
        # 直接使用传入的规划创建章节记录（不调用AI）
        created_chapters = await expansion_service.create_chapters_from_plans(
            outline_id=outline_id,
            chapter_plans=chapter_plans_dict,
            project_id=outline.project_id,
            db=db,
            start_chapter_number=None  # 自动计算章节序号
        )
        
        await db.commit()
        
        # 刷新章节数据
        for chapter in created_chapters:
            await db.refresh(chapter)
        
        logger.info(f"成功根据已有规划创建 {len(created_chapters)} 个章节记录")
        
        # 构建响应
        return CreateChaptersFromPlansResponse(
            outline_id=outline_id,
            outline_title=outline.title,
            chapters_created=len(created_chapters),
            created_chapters=[
                {
                    "id": ch.id,
                    "chapter_number": ch.chapter_number,
                    "title": ch.title,
                    "summary": ch.summary,
                    "outline_id": ch.outline_id,
                    "sub_index": ch.sub_index,
                    "status": ch.status
                }
                for ch in created_chapters
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"根据已有规划创建章节失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建章节失败: {str(e)}")