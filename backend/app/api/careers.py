
"""职业管理API"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import json
from typing import AsyncGenerator

from app.database import get_db
from app.utils.sse_response import SSEResponse, create_sse_response, WizardProgressTracker
from app.models.career import Career, CharacterCareer
from app.models.character import Character
from app.models.project import Project
from app.schemas.career import (
    CareerCreate,
    CareerUpdate,
    CareerResponse,
    CareerListResponse,
    CareerGenerateRequest,
    CharacterCareerResponse,
    CharacterCareerDetail,
    SetMainCareerRequest,
    AddSubCareerRequest,
    UpdateCareerStageRequest,
    CareerStage
)
from app.services.ai_service import AIService
from app.logger import get_logger
from app.api.settings import get_user_ai_service
from app.api.common import verify_project_access

router = APIRouter(prefix="/careers", tags=["职业管理"])
logger = get_logger(__name__)


@router.get("", response_model=CareerListResponse, summary="获取职业列表")
async def get_careers(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有职业"""
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    # 获取总数
    count_result = await db.execute(
        select(func.count(Career.id)).where(Career.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取职业列表
    result = await db.execute(
        select(Career)
        .where(Career.project_id == project_id)
        .order_by(Career.type, Career.created_at.desc())
    )
    careers = result.scalars().all()
    
    # 分类返回
    main_careers = []
    sub_careers = []
    
    for career in careers:
        # 解析JSON字段
        stages = json.loads(career.stages) if career.stages else []
        attribute_bonuses = json.loads(career.attribute_bonuses) if career.attribute_bonuses else None
        
        career_dict = {
            "id": career.id,
            "project_id": career.project_id,
            "name": career.name,
            "type": career.type,
            "description": career.description,
            "category": career.category,
            "stages": stages,
            "max_stage": career.max_stage,
            "requirements": career.requirements,
            "special_abilities": career.special_abilities,
            "worldview_rules": career.worldview_rules,
            "attribute_bonuses": attribute_bonuses,
            "source": career.source,
            "created_at": career.created_at,
            "updated_at": career.updated_at
        }
        
        if career.type == "main":
            main_careers.append(career_dict)
        else:
            sub_careers.append(career_dict)
    
    return CareerListResponse(
        total=total,
        main_careers=main_careers,
        sub_careers=sub_careers
    )


@router.post("", response_model=CareerResponse, summary="创建职业")
async def create_career(
    career_data: CareerCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """手动创建职业"""
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(career_data.project_id, user_id, db)
    
    try:
        # 转换stages为JSON字符串
        stages_json = json.dumps([stage.model_dump() for stage in career_data.stages], ensure_ascii=False)
        attribute_bonuses_json = json.dumps(career_data.attribute_bonuses, ensure_ascii=False) if career_data.attribute_bonuses else None
        
        # 创建职业
        career = Career(
            project_id=career_data.project_id,
            name=career_data.name,
            type=career_data.type,
            description=career_data.description,
            category=career_data.category,
            stages=stages_json,
            max_stage=career_data.max_stage,
            requirements=career_data.requirements,
            special_abilities=career_data.special_abilities,
            worldview_rules=career_data.worldview_rules,
            attribute_bonuses=attribute_bonuses_json,
            source=career_data.source
        )
        db.add(career)
        await db.commit()
        await db.refresh(career)
        
        logger.info(f"✅ 创建职业成功：{career.name} (ID: {career.id}, 类型: {career.type})")
        
        return CareerResponse(
            id=career.id,
            project_id=career.project_id,
            name=career.name,
            type=career.type,
            description=career.description,
            category=career.category,
            stages=career_data.stages,
            max_stage=career.max_stage,
            requirements=career.requirements,
            special_abilities=career.special_abilities,
            worldview_rules=career.worldview_rules,
            attribute_bonuses=career_data.attribute_bonuses,
            source=career.source,
            created_at=career.created_at,
            updated_at=career.updated_at
        )
        
    except Exception as e:
        logger.error(f"创建职业失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建职业失败: {str(e)}")


@router.get("/generate-system", summary="AI生成新职业（增量式，流式）")
async def generate_career_system(
    project_id: str,
    main_career_count: int = 3,
    sub_career_count: int = 6,
    enable_mcp: bool = False,
    http_request: Request = None,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用AI生成新职业（增量式，基于已有职业补充，支持SSE流式进度显示）
    
    通过Server-Sent Events返回实时进度信息
    """
    async def generate() -> AsyncGenerator[str, None]:
        tracker = WizardProgressTracker("职业体系")
        try:
            # 验证用户权限和项目是否存在
            user_id = getattr(http_request.state, 'user_id', None)
            project = await verify_project_access(project_id, user_id, db)
            
            yield await tracker.start()
            
            # 获取已有职业列表
            yield await tracker.loading("分析已有职业...", 0.3)
            
            existing_careers_result = await db.execute(
                select(Career).where(Career.project_id == project_id)
            )
            existing_careers = existing_careers_result.scalars().all()
            
            # 构建已有职业摘要
            existing_main_careers = []
            existing_sub_careers = []
            for career in existing_careers:
                career_summary = f"- {career.name}（{career.category or '未分类'}，{career.max_stage}阶）"
                if career.description:
                    career_summary += f": {career.description[:50]}"
                
                if career.type == "main":
                    existing_main_careers.append(career_summary)
                else:
                    existing_sub_careers.append(career_summary)
            
            existing_careers_text = ""
            if existing_main_careers:
                existing_careers_text += f"\n已有主职业（{len(existing_main_careers)}个）：\n" + "\n".join(existing_main_careers)
            if existing_sub_careers:
                existing_careers_text += f"\n\n已有副职业（{len(existing_sub_careers)}个）：\n" + "\n".join(existing_sub_careers)
            
            if not existing_careers_text:
                existing_careers_text = "\n当前还没有任何职业，这是第一次创建职业体系。"
            
            # 构建项目上下文
            yield await tracker.loading("分析项目世界观...", 0.6)
            
            project_context = f"""
项目信息：
- 书名：{project.title}
- 类型：{project.genre or '未设定'}
- 主题：{project.theme or '未设定'}
- 时间背景：{project.world_time_period or '未设定'}
- 地理位置：{project.world_location or '未设定'}
- 氛围基调：{project.world_atmosphere or '未设定'}
- 世界规则：{project.world_rules or '未设定'}
"""
            
            user_requirements = f"""
已有职业情况：{existing_careers_text}

生成要求（增量式）：
- 本次新增主职业：{main_career_count}个
- 本次新增副职业：{sub_career_count}个
- ⚠️ 重要：请生成与已有职业**不重复**的新职业，形成互补体系
- 新职业应填补已有职业体系的空缺，丰富职业多样性
- 主职业必须严格符合世界观规则，体现核心能力体系
- 副职业可以更加自由灵活，包含生产、辅助、特殊类型
"""
            
            yield await tracker.preparing("构建AI提示词...")
            
            # 构建提示词
            prompt = f"""{project_context}

{user_requirements}

请为这个小说项目生成新的补充职业（增量式）。要求：
1. **仔细分析已有职业**，避免生成重复或相似的职业
2. **填补职业体系的空缺**，让职业体系更加完善和多样化
3. 如果已有职业较少，可以生成核心基础职业
4. 如果已有职业较多，可以生成特色化、专精化的职业

返回JSON格式，结构如下：

{{
  "main_careers": [
    {{
      "name": "职业名称",
      "description": "职业描述",
      "category": "职业分类（如：战斗系、法术系等）",
      "stages": [
        {{"level": 1, "name": "阶段名称", "description": "阶段描述"}},
        {{"level": 2, "name": "阶段名称", "description": "阶段描述"}},
        ...
      ],
      "max_stage": 10,
      "requirements": "职业要求",
      "special_abilities": "特殊能力",
      "worldview_rules": "世界观规则关联",
      "attribute_bonuses": {{"strength": "+10%", "intelligence": "+5%"}}
    }}
  ],
  "sub_careers": [
    {{
      "name": "副职业名称",
      "description": "职业描述",
      "category": "生产系/辅助系/特殊系",
      "stages": [...],
      "max_stage": 5,
      "requirements": "职业要求",
      "special_abilities": "特殊能力"
    }}
  ]
}}

注意事项：
1. **避免重复**：生成的职业名称和定位不能与已有职业重复
2. **互补性**：新职业应与已有职业形成互补，丰富职业体系
3. 主职业的阶段设定要详细，体现明确的成长路径
4. 阶段名称要符合世界观特色
5. 副职业可以相对简化，但要有独特性
6. 所有职业都要符合项目的整体世界观设定
7. 只返回纯JSON，不要添加任何解释文字
"""
            
            yield await tracker.generating(0, max(3000, len(prompt) * 8), "调用AI生成新职业...")
            logger.info(f"🎯 开始为项目 {project_id} 生成新职业（增量式，已有{len(existing_careers)}个职业）")
            
            try:
                # 使用流式生成替代非流式
                ai_response = ""
                chunk_count = 0
                estimated_total = max(3000, len(prompt) * 8)
                
                async for chunk in user_ai_service.generate_text_stream(prompt=prompt):
                    chunk_count += 1
                    ai_response += chunk
                    
                    # 发送内容块
                    yield await SSEResponse.send_chunk(chunk)
                    
                    # 平滑更新进度（避免过于频繁）
                    if chunk_count % 10 == 0:
                        yield await tracker.generating(len(ai_response), estimated_total)
                    
                    # 心跳
                    if chunk_count % 20 == 0:
                        yield await tracker.heartbeat()
                
            except Exception as ai_error:
                logger.error(f"❌ AI服务调用异常：{str(ai_error)}")
                yield await tracker.error(f"AI服务调用失败：{str(ai_error)}")
                return
            
            if not ai_response or not ai_response.strip():
                yield await tracker.error("AI服务返回空响应")
                return
            
            yield await tracker.parsing("解析AI响应...", 0.5)
            
            # 清洗并解析JSON
            try:
                cleaned_response = user_ai_service._clean_json_response(ai_response)
                career_data = json.loads(cleaned_response)
                logger.info(f"✅ 职业体系JSON解析成功")
            except json.JSONDecodeError as e:
                logger.error(f"❌ 职业体系JSON解析失败: {e}")
                logger.error(f"   原始响应预览: {ai_response[:200]}")
                yield await tracker.error(f"AI返回的内容无法解析为JSON：{str(e)}")
                return
            
            yield await tracker.saving("保存主职业到数据库...", 0.3)
            
            # 保存主职业
            main_careers_created = []
            for idx, career_info in enumerate(career_data.get("main_careers", [])):
                try:
                    stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                    attribute_bonuses = career_info.get("attribute_bonuses")
                    attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                    
                    career = Career(
                        project_id=project_id,
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
            
            yield await tracker.saving("保存副职业到数据库...", 0.6)
            
            # 保存副职业
            sub_careers_created = []
            for idx, career_info in enumerate(career_data.get("sub_careers", [])):
                try:
                    stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                    attribute_bonuses = career_info.get("attribute_bonuses")
                    attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                    
                    career = Career(
                        project_id=project_id,
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
            
            await db.commit()
            
            total_main = len(existing_main_careers) + len(main_careers_created)
            total_sub = len(existing_sub_careers) + len(sub_careers_created)
            
            logger.info(f"🎉 新职业生成完成：新增主职业{len(main_careers_created)}个，新增副职业{len(sub_careers_created)}个")
            logger.info(f"   职业体系总数：主职业{total_main}个，副职业{total_sub}个")
            
            yield await tracker.complete(f"新职业生成完成！（主职业{total_main}个，副职业{total_sub}个）")
            
            # 发送结果数据
            yield await tracker.result({
                "main_careers_count": len(main_careers_created),
                "sub_careers_count": len(sub_careers_created),
                "main_careers": main_careers_created,
                "sub_careers": sub_careers_created
            })
            
            yield await tracker.done()
            
        except HTTPException as he:
            logger.error(f"HTTP异常: {he.detail}")
            yield await tracker.error(he.detail, he.status_code)
        except Exception as e:
            logger.error(f"生成职业体系失败: {str(e)}")
            yield await tracker.error(f"生成新职业失败: {str(e)}")
    
    return create_sse_response(generate())


@router.put("/{career_id}", response_model=CareerResponse, summary="更新职业")
async def update_career(
    career_id: str,
    career_update: CareerUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新职业信息"""
    result = await db.execute(
        select(Career).where(Career.id == career_id)
    )
    career = result.scalar_one_or_none()
    
    if not career:
        raise HTTPException(status_code=404, detail="职业不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(career.project_id, user_id, db)
    
    # 更新字段
    update_data = career_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == "stages" and value is not None:
            # 转换为JSON字符串
            # model_dump() 已经将嵌套模型转换为字典，所以 value 中的元素已经是 dict
            stages_list = [
                stage if isinstance(stage, dict) else stage.model_dump()
                for stage in value
            ]
            setattr(career, field, json.dumps(stages_list, ensure_ascii=False))
        elif field == "attribute_bonuses" and value is not None:
            # 转换为JSON字符串
            setattr(career, field, json.dumps(value, ensure_ascii=False))
        else:
            setattr(career, field, value)
    
    await db.commit()
    await db.refresh(career)
    
    logger.info(f"✅ 更新职业成功：{career.name} (ID: {career_id})")
    
    # 解析JSON返回
    stages = json.loads(career.stages) if career.stages else []
    attribute_bonuses = json.loads(career.attribute_bonuses) if career.attribute_bonuses else None
    
    return CareerResponse(
        id=career.id,
        project_id=career.project_id,
        name=career.name,
        type=career.type,
        description=career.description,
        category=career.category,
        stages=stages,
        max_stage=career.max_stage,
        requirements=career.requirements,
        special_abilities=career.special_abilities,
        worldview_rules=career.worldview_rules,
        attribute_bonuses=attribute_bonuses,
        source=career.source,
        created_at=career.created_at,
        updated_at=career.updated_at
    )


@router.delete("/{career_id}", summary="删除职业")
async def delete_career(
    career_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除职业"""
    result = await db.execute(
        select(Career).where(Career.id == career_id)
    )
    career = result.scalar_one_or_none()
    
    if not career:
        raise HTTPException(status_code=404, detail="职业不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(career.project_id, user_id, db)
    
    # 检查是否有角色使用该职业
    char_career_result = await db.execute(
        select(func.count(CharacterCareer.id)).where(CharacterCareer.career_id == career_id)
    )
    usage_count = char_career_result.scalar_one()
    
    if usage_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该职业被{usage_count}个角色使用，无法删除。请先移除角色的职业关联。"
        )
    
    await db.delete(career)
    await db.commit()
    
    logger.info(f"✅ 删除职业成功：{career.name} (ID: {career_id})")
    
    return {"message": "职业删除成功"}


@router.get("/{career_id}", response_model=CareerResponse, summary="获取职业详情")
async def get_career(
    career_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取职业详情"""
    result = await db.execute(
        select(Career).where(Career.id == career_id)
    )
    career = result.scalar_one_or_none()
    
    if not career:
        raise HTTPException(status_code=404, detail="职业不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(career.project_id, user_id, db)
    
    # 解析JSON字段
    stages = json.loads(career.stages) if career.stages else []
    attribute_bonuses = json.loads(career.attribute_bonuses) if career.attribute_bonuses else None
    
    return CareerResponse(
        id=career.id,
        project_id=career.project_id,
        name=career.name,
        type=career.type,
        description=career.description,
        category=career.category,
        stages=stages,
        max_stage=career.max_stage,
        requirements=career.requirements,
        special_abilities=career.special_abilities,
        worldview_rules=career.worldview_rules,
        attribute_bonuses=attribute_bonuses,
        source=career.source,
        created_at=career.created_at,
        updated_at=career.updated_at
    )


# ===== 角色职业关联API =====

@router.get("/character/{character_id}/careers", response_model=CharacterCareerResponse, summary="获取角色的职业信息")
async def get_character_careers(
    character_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取角色的所有职业信息（主职业和副职业）"""
    # 验证角色存在
    char_result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = char_result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 获取角色的所有职业关联
    result = await db.execute(
        select(CharacterCareer, Career)
        .join(Career, CharacterCareer.career_id == Career.id)
        .where(CharacterCareer.character_id == character_id)
        .order_by(CharacterCareer.career_type.desc())  # main排在前
    )
    career_relations = result.all()
    
    main_career = None
    sub_careers = []
    
    for char_career, career in career_relations:
        # 解析职业的阶段信息
        stages = json.loads(career.stages) if career.stages else []
        
        # 找到当前阶段信息
        stage_name = "未知阶段"
        stage_description = None
        for stage in stages:
            if stage.get("level") == char_career.current_stage:
                stage_name = stage.get("name", f"第{char_career.current_stage}阶段")
                stage_description = stage.get("description")
                break
        
        career_detail = CharacterCareerDetail(
            id=char_career.id,
            character_id=char_career.character_id,
            career_id=char_career.career_id,
            career_name=career.name,
            career_type=char_career.career_type,
            current_stage=char_career.current_stage,
            stage_name=stage_name,
            stage_description=stage_description,
            stage_progress=char_career.stage_progress,
            max_stage=career.max_stage,
            started_at=char_career.started_at,
            reached_current_stage_at=char_career.reached_current_stage_at,
            notes=char_career.notes,
            created_at=char_career.created_at,
            updated_at=char_career.updated_at
        )
        
        if char_career.career_type == "main":
            main_career = career_detail
        else:
            sub_careers.append(career_detail)
    
    return CharacterCareerResponse(
        main_career=main_career,
        sub_careers=sub_careers
    )


@router.post("/character/{character_id}/careers/main", summary="设置角色主职业")
async def set_main_career(
    character_id: str,
    career_request: SetMainCareerRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """设置或更换角色的主职业"""
    # 验证角色存在
    char_result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = char_result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 验证职业存在且为主职业类型
    career_result = await db.execute(
        select(Career).where(
            Career.id == career_request.career_id,
            Career.project_id == character.project_id
        )
    )
    career = career_result.scalar_one_or_none()
    
    if not career:
        raise HTTPException(status_code=404, detail="职业不存在")
    
    if career.type != "main":
        raise HTTPException(status_code=400, detail="该职业不是主职业类型，无法设置为主职业")
    
    # 验证阶段有效性
    if career_request.current_stage > career.max_stage:
        raise HTTPException(
            status_code=400,
            detail=f"阶段超出范围，该职业最大阶段为{career.max_stage}"
        )
    
    # 检查是否已有主职业
    existing_main = await db.execute(
        select(CharacterCareer).where(
            CharacterCareer.character_id == character_id,
            CharacterCareer.career_type == "main"
        )
    )
    current_main = existing_main.scalar_one_or_none()
    
    if current_main:
        # 删除旧的主职业
        await db.delete(current_main)
        logger.info(f"  移除旧主职业关联: {current_main.career_id}")
    
    # 创建新的主职业关联
    char_career = CharacterCareer(
        character_id=character_id,
        career_id=career_request.career_id,
        career_type="main",
        current_stage=career_request.current_stage,
        stage_progress=0,
        started_at=career_request.started_at,
        reached_current_stage_at=career_request.started_at
    )
    db.add(char_career)
    await db.commit()
    
    logger.info(f"✅ 设置主职业成功：角色{character.name} -> {career.name}（第{career_request.current_stage}阶段）")
    
    return {"message": "主职业设置成功", "career_name": career.name}


@router.post("/character/{character_id}/careers/sub", summary="添加角色副职业")
async def add_sub_career(
    character_id: str,
    career_request: AddSubCareerRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """为角色添加副职业"""
    # 验证角色存在
    char_result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = char_result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 验证职业存在且为副职业类型
    career_result = await db.execute(
        select(Career).where(
            Career.id == career_request.career_id,
            Career.project_id == character.project_id
        )
    )
    career = career_result.scalar_one_or_none()
    
    if not career:
        raise HTTPException(status_code=404, detail="职业不存在")
    
    if career.type != "sub":
        raise HTTPException(status_code=400, detail="该职业不是副职业类型，无法添加为副职业")
    
    # 验证阶段有效性
    if career_request.current_stage > career.max_stage:
        raise HTTPException(
            status_code=400,
            detail=f"阶段超出范围，该职业最大阶段为{career.max_stage}"
        )
    
    # 检查是否已存在
    existing_check = await db.execute(
        select(CharacterCareer).where(
            CharacterCareer.character_id == character_id,
            CharacterCareer.career_id == career_request.career_id
        )
    )
    if existing_check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该角色已拥有此副职业")
    
    # 检查副职业数量限制（可选，这里设置为最多5个）
    sub_count_result = await db.execute(
        select(func.count(CharacterCareer.id)).where(
            CharacterCareer.character_id == character_id,
            CharacterCareer.career_type == "sub"
        )
    )
    sub_count = sub_count_result.scalar_one()
    
    if sub_count >= 5:
        raise HTTPException(status_code=400, detail="副职业数量已达上限（最多5个）")
    
    # 创建副职业关联
    char_career = CharacterCareer(
        character_id=character_id,
        career_id=career_request.career_id,
        career_type="sub",
        current_stage=career_request.current_stage,
        stage_progress=0,
        started_at=career_request.started_at,
        reached_current_stage_at=career_request.started_at
    )
    db.add(char_career)
    await db.commit()
    
    logger.info(f"✅ 添加副职业成功：角色{character.name} -> {career.name}（第{career_request.current_stage}阶段）")
    
    return {"message": "副职业添加成功", "career_name": career.name}


@router.put("/character/{character_id}/careers/{career_id}/stage", summary="更新职业阶段")
async def update_career_stage(
    character_id: str,
    career_id: str,
    stage_request: UpdateCareerStageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新角色在某个职业的阶段"""
    # 验证角色职业关联存在
    result = await db.execute(
        select(CharacterCareer, Career, Character)
        .join(Career, CharacterCareer.career_id == Career.id)
        .join(Character, CharacterCareer.character_id == Character.id)
        .where(
            CharacterCareer.character_id == character_id,
            CharacterCareer.career_id == career_id
        )
    )
    relation_data = result.one_or_none()
    
    if not relation_data:
        raise HTTPException(status_code=404, detail="角色职业关联不存在")
    
    char_career, career, character = relation_data
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 验证新阶段有效性
    if stage_request.current_stage > career.max_stage:
        raise HTTPException(
            status_code=400,
            detail=f"阶段超出范围，该职业最大阶段为{career.max_stage}"
        )
    
    # 验证阶段递增规则（不能倒退，除非降级）
    if stage_request.current_stage < char_career.current_stage:
        logger.warning(f"⚠️ 角色{character.name}的职业{career.name}阶段降低：{char_career.current_stage} -> {stage_request.current_stage}")
    
    # 更新阶段信息
    char_career.current_stage = stage_request.current_stage
    char_career.stage_progress = stage_request.stage_progress
    if stage_request.reached_current_stage_at:
        char_career.reached_current_stage_at = stage_request.reached_current_stage_at
    if stage_request.notes is not None:
        char_career.notes = stage_request.notes
    
    await db.commit()
    
    logger.info(f"✅ 更新职业阶段成功：{character.name}的{career.name} -> 第{stage_request.current_stage}阶段")
    
    return {
        "message": "职业阶段更新成功",
        "career_name": career.name,
        "new_stage": stage_request.current_stage
    }


@router.delete("/character/{character_id}/careers/{career_id}", summary="删除角色副职业")
async def remove_sub_career(
    character_id: str,
    career_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除角色的副职业"""
    # 验证角色职业关联存在
    result = await db.execute(
        select(CharacterCareer, Character)
        .join(Character, CharacterCareer.character_id == Character.id)
        .where(
            CharacterCareer.character_id == character_id,
            CharacterCareer.career_id == career_id
        )
    )
    relation_data = result.one_or_none()
    
    if not relation_data:
        raise HTTPException(status_code=404, detail="角色职业关联不存在")
    
    char_career, character = relation_data
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 不允许删除主职业
    if char_career.career_type == "main":
        raise HTTPException(status_code=400, detail="无法删除主职业，只能更换")
    
    await db.delete(char_career)
    await db.commit()
    
    logger.info(f"✅ 删除副职业成功：角色{character.name}移除职业{career_id}")
    
    return {"message": "副职业删除成功"}
