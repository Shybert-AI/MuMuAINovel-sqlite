"""提示词模板管理 API"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from datetime import datetime
import json
import hashlib

from app.database import get_db
from app.models.prompt_template import PromptTemplate
from app.schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTemplateResponse,
    PromptTemplateListResponse,
    PromptTemplateCategoryResponse,
    PromptTemplateExport,
    PromptTemplateExportItem,
    PromptTemplateImportResult,
    PromptTemplatePreviewRequest
)
from app.services.prompt_service import PromptService
from app.logger import get_logger

logger = get_logger(__name__)

def calculate_content_hash(content: str) -> str:
    """计算模板内容的SHA256哈希值"""
    return hashlib.sha256(content.strip().encode('utf-8')).hexdigest()[:16]

router = APIRouter(prefix="/prompt-templates", tags=["提示词模板管理"])


@router.get("", response_model=PromptTemplateListResponse)
async def get_all_templates(
    request: Request,
    category: Optional[str] = Query(None, description="按分类筛选"),
    is_active: Optional[bool] = Query(None, description="按启用状态筛选"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户所有提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    query = select(PromptTemplate).where(PromptTemplate.user_id == user_id)
    
    if category:
        query = query.where(PromptTemplate.category == category)
    if is_active is not None:
        query = query.where(PromptTemplate.is_active == is_active)
    
    query = query.order_by(PromptTemplate.category, PromptTemplate.template_key)
    
    result = await db.execute(query)
    templates = result.scalars().all()
    
    # 获取所有分类
    categories_result = await db.execute(
        select(PromptTemplate.category)
        .where(PromptTemplate.user_id == user_id)
        .distinct()
    )
    categories = [c for c in categories_result.scalars().all() if c]
    
    return PromptTemplateListResponse(
        templates=templates,
        total=len(templates),
        categories=sorted(categories)
    )


@router.get("/categories", response_model=List[PromptTemplateCategoryResponse])
async def get_templates_by_category(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    按分类获取提示词模板（合并用户自定义和系统默认）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 1. 查询用户自定义模板
    result = await db.execute(
        select(PromptTemplate)
        .where(PromptTemplate.user_id == user_id)
        .order_by(PromptTemplate.category, PromptTemplate.template_key)
    )
    user_templates = result.scalars().all()
    
    # 2. 获取所有系统默认模板
    system_templates = PromptService.get_all_system_templates()
    
    # 3. 构建用户自定义模板的键集合
    user_template_keys = {t.template_key for t in user_templates}
    
    # 4. 合并模板：用户自定义的 + 未自定义的系统默认
    all_templates = []
    current_time = datetime.now()
    
    # 添加用户自定义的模板
    for user_template in user_templates:
        user_template.is_system_default = False  # 标记为已自定义
        all_templates.append(user_template)
    
    # 添加未自定义的系统默认模板
    for sys_template in system_templates:
        if sys_template['template_key'] not in user_template_keys:
            # 这个系统模板用户还没有自定义，创建临时对象
            template_obj = PromptTemplate(
                id=sys_template['template_key'],  # 使用template_key作为临时ID
                user_id=user_id,
                template_key=sys_template['template_key'],
                template_name=sys_template['template_name'],
                template_content=sys_template['content'],
                description=sys_template['description'],
                category=sys_template['category'],
                parameters=json.dumps(sys_template['parameters']),
                is_active=True,
                is_system_default=True,
                created_at=current_time,
                updated_at=current_time
            )
            all_templates.append(template_obj)
    
    # 5. 按分类分组
    category_dict = {}
    for template in all_templates:
        cat = template.category or "未分类"
        if cat not in category_dict:
            category_dict[cat] = []
        category_dict[cat].append(template)
    
    # 6. 构建响应
    response = []
    for category, temps in sorted(category_dict.items()):
        # 按template_key排序，确保顺序一致
        temps.sort(key=lambda t: t.template_key)
        response.append(PromptTemplateCategoryResponse(
            category=category,
            count=len(temps),
            templates=temps
        ))
    
    return response


@router.get("/system-defaults")
async def get_system_defaults(
    request: Request
):
    """
    获取所有系统默认提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 从PromptService获取所有系统默认模板
    system_templates = PromptService.get_all_system_templates()
    
    return {
        "templates": system_templates,
        "total": len(system_templates)
    }


@router.get("/{template_key}", response_model=PromptTemplateResponse)
async def get_template(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定的提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    return template


@router.post("", response_model=PromptTemplateResponse)
async def create_or_update_template(
    data: PromptTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    创建或更新提示词模板（Upsert）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 查找现有模板
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == data.template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if template:
        # 更新现有模板
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(template, key, value)
        logger.info(f"用户 {user_id} 更新模板 {data.template_key}")
    else:
        # 创建新模板
        template = PromptTemplate(
            user_id=user_id,
            **data.model_dump()
        )
        db.add(template)
        logger.info(f"用户 {user_id} 创建模板 {data.template_key}")
    
    await db.commit()
    await db.refresh(template)
    
    return template


@router.put("/{template_key}", response_model=PromptTemplateResponse)
async def update_template(
    template_key: str,
    data: PromptTemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    更新提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    # 更新模板
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    await db.commit()
    await db.refresh(template)
    logger.info(f"用户 {user_id} 更新模板 {template_key}")
    
    return template


@router.delete("/{template_key}")
async def delete_template(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    删除自定义提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    await db.delete(template)
    await db.commit()
    logger.info(f"用户 {user_id} 删除模板 {template_key}")
    
    return {"message": "模板已删除", "template_key": template_key}


@router.post("/{template_key}/reset")
async def reset_to_default(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    重置为系统默认模板（删除用户自定义版本）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 验证系统默认模板是否存在
    system_template = PromptService.get_system_template_info(template_key)
    if not system_template:
        raise HTTPException(status_code=404, detail=f"系统默认模板 {template_key} 不存在")
    
    # 查找并删除用户的自定义模板
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if template:
        await db.delete(template)
        await db.commit()
        logger.info(f"用户 {user_id} 删除自定义模板 {template_key}，恢复为系统默认")
        return {"message": "已重置为系统默认", "template_key": template_key}
    else:
        # 用户本来就没有自定义，已经是系统默认状态
        logger.info(f"用户 {user_id} 的模板 {template_key} 本来就是系统默认")
        return {"message": "已是系统默认状态", "template_key": template_key}


@router.post("/export", response_model=PromptTemplateExport)
async def export_templates(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    导出所有提示词模板（包括用户自定义和系统默认）
    - 用户自定义的提示词标记为 is_customized=true
    - 系统默认的提示词标记为 is_customized=false
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 1. 查询用户自定义模板
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user_id)
    )
    user_templates = result.scalars().all()
    
    # 2. 获取所有系统默认模板
    system_templates = PromptService.get_all_system_templates()
    
    # 3. 构建用户自定义模板的键集合
    user_template_keys = {t.template_key for t in user_templates}
    
    # 4. 准备导出数据
    export_items = []
    customized_count = 0
    system_default_count = 0
    
    # 添加用户自定义的模板
    for user_template in user_templates:
        # 获取对应的系统模板用于计算哈希
        system_template = next(
            (t for t in system_templates if t["template_key"] == user_template.template_key),
            None
        )
        system_hash = calculate_content_hash(system_template["content"]) if system_template else None
        
        export_items.append(PromptTemplateExportItem(
            template_key=user_template.template_key,
            template_name=user_template.template_name,
            template_content=user_template.template_content,
            description=user_template.description,
            category=user_template.category,
            parameters=user_template.parameters,
            is_active=user_template.is_active,
            is_customized=True,
            system_content_hash=system_hash
        ))
        customized_count += 1
    
    # 添加未自定义的系统默认模板
    for sys_template in system_templates:
        if sys_template['template_key'] not in user_template_keys:
            export_items.append(PromptTemplateExportItem(
                template_key=sys_template['template_key'],
                template_name=sys_template['template_name'],
                template_content=sys_template['content'],
                description=sys_template['description'],
                category=sys_template['category'],
                parameters=json.dumps(sys_template['parameters']),
                is_active=True,
                is_customized=False,
                system_content_hash=calculate_content_hash(sys_template['content'])
            ))
            system_default_count += 1
    
    statistics = {
        "total": len(export_items),
        "customized": customized_count,
        "system_default": system_default_count
    }
    
    logger.info(f"用户 {user_id} 导出了 {statistics['total']} 个模板 "
                f"(自定义: {statistics['customized']}, 系统默认: {statistics['system_default']})")
    
    return PromptTemplateExport(
        templates=export_items,
        export_time=datetime.now(),
        version="2.0",
        statistics=statistics
    )


@router.post("/import", response_model=PromptTemplateImportResult)
async def import_templates(
    data: PromptTemplateExport,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    智能导入提示词模板
    - 如果导入的是系统默认且内容未修改 → 删除自定义记录（使用系统默认）
    - 如果导入的是系统默认但内容已修改 → 创建自定义记录
    - 如果导入的是用户自定义 → 创建/更新自定义记录
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 获取所有系统默认模板用于比对
    system_templates = PromptService.get_all_system_templates()
    system_template_dict = {t["template_key"]: t for t in system_templates}
    
    # 统计信息
    kept_system_default = 0  # 保持系统默认
    created_or_updated = 0   # 创建或更新自定义
    converted_to_custom = 0  # 从系统默认转为自定义
    converted_templates = []  # 被转换的模板列表
    
    for template_data in data.templates:
        template_key = template_data.template_key
        is_customized = template_data.is_customized
        imported_content = template_data.template_content.strip()
        
        # 查找当前用户是否已有该模板的自定义版本
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.user_id == user_id,
                PromptTemplate.template_key == template_key
            )
        )
        existing = result.scalar_one_or_none()
        
        # 获取系统默认模板
        system_template = system_template_dict.get(template_key)
        
        if not is_customized:
            # 导入的标记为系统默认
            if system_template:
                system_content = system_template["content"].strip()
                
                # 比对内容是否与系统默认一致
                if imported_content == system_content:
                    # 内容一致，删除自定义记录（如果有）
                    if existing:
                        await db.delete(existing)
                        logger.info(f"用户 {user_id} 的模板 {template_key} 恢复为系统默认（删除自定义）")
                    kept_system_default += 1
                else:
                    # 内容不一致，用户修改过，创建/更新为自定义
                    if existing:
                        # 更新现有自定义
                        existing.template_name = template_data.template_name
                        existing.template_content = template_data.template_content
                        existing.description = template_data.description
                        existing.category = template_data.category
                        existing.parameters = template_data.parameters
                        existing.is_active = template_data.is_active
                    else:
                        # 创建新自定义
                        new_template = PromptTemplate(
                            user_id=user_id,
                            template_key=template_data.template_key,
                            template_name=template_data.template_name,
                            template_content=template_data.template_content,
                            description=template_data.description,
                            category=template_data.category,
                            parameters=template_data.parameters,
                            is_active=template_data.is_active
                        )
                        db.add(new_template)
                    
                    converted_to_custom += 1
                    converted_templates.append({
                        "template_key": template_key,
                        "template_name": template_data.template_name,
                        "reason": "内容与系统默认不一致，已转为自定义"
                    })
                    logger.info(f"用户 {user_id} 的模板 {template_key} 内容已修改，转为自定义")
            else:
                # 系统中不存在该模板，作为自定义导入
                if existing:
                    existing.template_name = template_data.template_name
                    existing.template_content = template_data.template_content
                    existing.description = template_data.description
                    existing.category = template_data.category
                    existing.parameters = template_data.parameters
                    existing.is_active = template_data.is_active
                else:
                    new_template = PromptTemplate(
                        user_id=user_id,
                        template_key=template_data.template_key,
                        template_name=template_data.template_name,
                        template_content=template_data.template_content,
                        description=template_data.description,
                        category=template_data.category,
                        parameters=template_data.parameters,
                        is_active=template_data.is_active
                    )
                    db.add(new_template)
                created_or_updated += 1
        else:
            # 导入的标记为用户自定义，直接创建/更新
            if existing:
                existing.template_name = template_data.template_name
                existing.template_content = template_data.template_content
                existing.description = template_data.description
                existing.category = template_data.category
                existing.parameters = template_data.parameters
                existing.is_active = template_data.is_active
            else:
                new_template = PromptTemplate(
                    user_id=user_id,
                    template_key=template_data.template_key,
                    template_name=template_data.template_name,
                    template_content=template_data.template_content,
                    description=template_data.description,
                    category=template_data.category,
                    parameters=template_data.parameters,
                    is_active=template_data.is_active
                )
                db.add(new_template)
            created_or_updated += 1
    
    await db.commit()
    
    statistics = {
        "total": len(data.templates),
        "kept_system_default": kept_system_default,
        "created_or_updated": created_or_updated,
        "converted_to_custom": converted_to_custom
    }
    
    logger.info(f"用户 {user_id} 导入完成: {statistics}")
    
    return PromptTemplateImportResult(
        message="导入成功",
        statistics=statistics,
        converted_templates=converted_templates
    )


@router.post("/{template_key}/preview")
async def preview_template(
    template_key: str,
    data: PromptTemplatePreviewRequest,
    request: Request
):
    """
    预览提示词模板（渲染变量）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    try:
        # 使用PromptService的format_prompt方法
        rendered = PromptService.format_prompt(
            data.template_content,
            **data.parameters
        )
        
        return {
            "success": True,
            "rendered_content": rendered,
            "parameters_used": list(data.parameters.keys())
        }
    except KeyError as e:
        return {
            "success": False,
            "error": f"缺少必需的参数: {str(e)}",
            "rendered_content": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"渲染失败: {str(e)}",
            "rendered_content": None
        }