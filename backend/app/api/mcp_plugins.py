"""MCP插件管理API

重构后使用统一的MCPClientFacade门面来管理所有MCP操作。
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Query, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, update
from typing import List, Optional
from datetime import datetime

from app.database import get_db, get_engine
from app.models.mcp_plugin import MCPPlugin
from app.schemas.mcp_plugin import (
    MCPPluginCreate,
    MCPPluginSimpleCreate,
    MCPPluginUpdate,
    MCPPluginResponse,
    MCPToolCall,
    MCPTestResult
)
import json
from app.user_manager import User
from app.mcp import mcp_client, MCPPluginConfig, PluginStatus
from app.services.mcp_test_service import mcp_test_service
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/plugins", tags=["MCP插件管理"])


def require_login(request: Request) -> User:
    """依赖：要求用户已登录"""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="需要登录")
    return request.state.user


async def _register_plugin_background(
    user_id: str,
    plugin_name: str,
    plugin_type: str,
    server_url: str,
    headers: Optional[dict],
    config: Optional[dict]
):
    """
    后台任务：注册MCP插件并更新数据库状态

    在独立的任务中执行MCP连接，避免阻塞请求处理
    """
    try:
        logger.info(f"后台注册MCP插件: {plugin_name}")

        if plugin_type in ["http", "streamable_http", "sse"] and server_url:
            success = await mcp_client.register(MCPPluginConfig(
                user_id=user_id,
                plugin_name=plugin_name,
                url=server_url,
                plugin_type=plugin_type,
                headers=headers,
                timeout=config.get('timeout', 60.0) if config else 60.0
            ))
        else:
            success = False

        # 更新数据库状态
        engine = await get_engine(user_id)
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with AsyncSessionLocal() as db:
            stmt = (
                update(MCPPlugin)
                .where(MCPPlugin.user_id == user_id, MCPPlugin.plugin_name == plugin_name)
                .values(
                    status="active" if success else "error",
                    last_error=None if success else "连接失败"
                )
            )
            await db.execute(stmt)
            await db.commit()

        if success:
            logger.info(f"后台注册MCP插件成功: {plugin_name}")
        else:
            logger.warning(f"后台注册MCP插件失败: {plugin_name}")

    except Exception as e:
        logger.error(f"后台注册MCP插件异常: {plugin_name}, 错误: {e}")
        try:
            engine = await get_engine(user_id)
            AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with AsyncSessionLocal() as db:
                stmt = (
                    update(MCPPlugin)
                    .where(MCPPlugin.user_id == user_id, MCPPlugin.plugin_name == plugin_name)
                    .values(status="error", last_error=str(e))
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as db_error:
            logger.error(f"更新插件状态失败: {db_error}")


async def _unregister_plugin_safe(user_id: str, plugin_name: str):
    """安全地在后台注销MCP插件"""
    try:
        await mcp_client.unregister(user_id, plugin_name)
        logger.info(f"后台注销MCP插件成功: {plugin_name}")
    except Exception as e:
        logger.warning(f"后台注销MCP插件出错: {plugin_name}, 错误: {e}")


async def _register_plugin_to_facade(plugin: MCPPlugin, user_id: str) -> bool:
    """
    将插件注册到统一门面
    
    Args:
        plugin: 插件对象
        user_id: 用户ID
        
    Returns:
        是否注册成功
    """
    if plugin.plugin_type in ["http", "streamable_http", "sse"] and plugin.server_url:
        return await mcp_client.register(MCPPluginConfig(
            user_id=user_id,
            plugin_name=plugin.plugin_name,
            url=plugin.server_url,
            plugin_type=plugin.plugin_type,
            headers=plugin.headers,
            timeout=plugin.config.get('timeout', 60.0) if plugin.config else 60.0
        ))
    else:
        logger.warning(f"暂不支持的插件类型: {plugin.plugin_type}")
        return False


@router.get("", response_model=List[MCPPluginResponse])
async def list_plugins(
    enabled_only: bool = Query(False, description="只返回启用的插件"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的所有MCP插件
    """
    query = select(MCPPlugin).where(MCPPlugin.user_id == user.user_id)
    
    if enabled_only:
        query = query.where(MCPPlugin.enabled == True)
    
    if category:
        query = query.where(MCPPlugin.category == category)
    
    query = query.order_by(MCPPlugin.sort_order, MCPPlugin.created_at)
    
    result = await db.execute(query)
    plugins = result.scalars().all()
    
    logger.info(f"用户 {user.user_id} 查询插件列表，共 {len(plugins)} 个")
    return plugins


@router.post("", response_model=MCPPluginResponse)
async def create_plugin(
    data: MCPPluginCreate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    创建新的MCP插件
    """
    # 检查插件名是否已存在
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.user_id == user.user_id,
            MCPPlugin.plugin_name == data.plugin_name
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"插件名已存在: {data.plugin_name}")
    
    # 创建插件数据
    plugin_data = data.model_dump()
    
    # 如果没有提供display_name，使用plugin_name作为默认值
    if not plugin_data.get("display_name"):
        plugin_data["display_name"] = plugin_data["plugin_name"]
    
    # 创建插件
    plugin = MCPPlugin(
        user_id=user.user_id,
        **plugin_data
    )
    
    db.add(plugin)
    await db.commit()
    await db.refresh(plugin)
    
    # 如果启用，注册到统一门面
    if plugin.enabled:
        success = await _register_plugin_to_facade(plugin, user.user_id)
        if success:
            plugin.status = "active"
        else:
            plugin.status = "error"
            plugin.last_error = "加载失败"
        await db.commit()
        await db.refresh(plugin)
    
    logger.info(f"用户 {user.user_id} 创建插件: {plugin.plugin_name}")
    return plugin


@router.post("/simple", response_model=MCPPluginResponse)
async def create_plugin_simple(
    data: MCPPluginSimpleCreate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    通过标准MCP配置JSON创建或更新插件（简化版）
    
    接受格式：
    {
      "config_json": '{"mcpServers": {"exa": {"type": "http", "url": "...", "headers": {}}}}',
      "category": "search"
    }
    
    自动从mcpServers中提取插件名称（取第一个键）
    如果插件已存在，则更新；否则创建新插件
    """
    try:
        # 解析配置JSON
        config = json.loads(data.config_json)
        
        # 验证格式
        if "mcpServers" not in config:
            raise HTTPException(status_code=400, detail="配置JSON必须包含mcpServers字段")
        
        servers = config["mcpServers"]
        if not servers or len(servers) == 0:
            raise HTTPException(status_code=400, detail="mcpServers不能为空")
        
        # 自动提取第一个插件名称
        plugin_name = list(servers.keys())[0]
        server_config = servers[plugin_name]
        
        logger.info(f"从配置中提取插件名称: {plugin_name}")
        
        # 提取配置
        server_type = server_config.get("type", "http")
        
        if server_type not in ["http", "stdio", "streamable_http", "sse"]:
            raise HTTPException(status_code=400, detail=f"不支持的服务器类型: {server_type}")
        
        # 检查插件名是否已存在
        result = await db.execute(
            select(MCPPlugin).where(
                MCPPlugin.user_id == user.user_id,
                MCPPlugin.plugin_name == plugin_name
            )
        )
        existing = result.scalar_one_or_none()
        
        # 构建插件数据
        plugin_data = {
            "plugin_name": plugin_name,
            "display_name": plugin_name, 
            "plugin_type": server_type,
            "enabled": data.enabled,
            "category": data.category,
            "sort_order": 0
        }
        
        if server_type in ["http", "streamable_http", "sse"]:
            plugin_data["server_url"] = server_config.get("url")
            plugin_data["headers"] = server_config.get("headers", {})
            
            if not plugin_data["server_url"]:
                raise HTTPException(status_code=400, detail=f"{server_type}类型插件必须提供url字段")
        
        elif server_type == "stdio":
            plugin_data["command"] = server_config.get("command")
            plugin_data["args"] = server_config.get("args", [])
            plugin_data["env"] = server_config.get("env", {})
            
            if not plugin_data["command"]:
                raise HTTPException(status_code=400, detail="Stdio类型插件必须提供command字段")
        
        if existing:
            # 更新现有插件
            logger.info(f"插件 {plugin_name} 已存在，执行更新操作")
            
            # 保存旧状态
            old_enabled = existing.enabled
            old_plugin_name = existing.plugin_name
            
            # 更新字段
            for key, value in plugin_data.items():
                setattr(existing, key, value)

            # 设置为pending状态，等待后台连接
            if plugin_data.get("enabled"):
                existing.status = "pending"

            plugin = existing
            await db.commit()
            await db.refresh(plugin)

            # 后台执行MCP操作（不阻塞请求）
            if old_enabled:
                # 注销旧插件（使用create_task在后台执行）
                asyncio.create_task(_unregister_plugin_safe(user.user_id, old_plugin_name))

            if plugin.enabled:
                # 后台注册新插件
                asyncio.create_task(_register_plugin_background(
                    user_id=user.user_id,
                    plugin_name=plugin.plugin_name,
                    plugin_type=plugin.plugin_type,
                    server_url=plugin.server_url,
                    headers=plugin.headers,
                    config=plugin.config
                ))

            logger.info(f"用户 {user.user_id} 更新插件: {plugin_name}")
        else:
            # 创建新插件
            plugin = MCPPlugin(
                user_id=user.user_id,
                **plugin_data
            )

            # 设置为pending状态，等待后台连接
            if plugin_data.get("enabled"):
                plugin.status = "pending"

            db.add(plugin)
            await db.commit()
            await db.refresh(plugin)

            # 后台执行MCP注册（不阻塞请求）
            if plugin.enabled:
                asyncio.create_task(_register_plugin_background(
                    user_id=user.user_id,
                    plugin_name=plugin.plugin_name,
                    plugin_type=plugin.plugin_type,
                    server_url=plugin.server_url,
                    headers=plugin.headers,
                    config=plugin.config
                ))

            logger.info(f"用户 {user.user_id} 通过简化配置创建插件: {plugin_name}")
        
        return plugin
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"配置JSON格式错误: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建插件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建插件失败: {str(e)}")


@router.get("/{plugin_id}", response_model=MCPPluginResponse)
async def get_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取插件详情
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    return plugin


@router.put("/{plugin_id}", response_model=MCPPluginResponse)
async def update_plugin(
    plugin_id: str,
    data: MCPPluginUpdate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    更新插件配置
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plugin, key, value)
    
    await db.commit()
    await db.refresh(plugin)
    
    # 如果插件已启用，重新注册
    if plugin.enabled:
        await mcp_client.unregister(user.user_id, plugin.plugin_name)
        await _register_plugin_to_facade(plugin, user.user_id)
    
    logger.info(f"用户 {user.user_id} 更新插件: {plugin.plugin_name}")
    return plugin


@router.delete("/{plugin_id}")
async def delete_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    删除插件
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    # 从统一门面注销
    await mcp_client.unregister(user.user_id, plugin.plugin_name)
    
    # 删除数据库记录
    await db.delete(plugin)
    await db.commit()
    
    logger.info(f"用户 {user.user_id} 删除插件: {plugin.plugin_name}")
    return {"message": "插件已删除", "plugin_name": plugin.plugin_name}


@router.post("/{plugin_id}/toggle", response_model=MCPPluginResponse)
async def toggle_plugin(
    plugin_id: str,
    enabled: bool = Query(..., description="启用或禁用"),
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    启用或禁用插件
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    # 保存插件信息用于后续MCP操作
    plugin_name = plugin.plugin_name
    plugin_type = plugin.plugin_type
    server_url = plugin.server_url
    headers = plugin.headers
    config = plugin.config
    
    # 先更新数据库状态
    plugin.enabled = enabled
    if not enabled:
        plugin.status = "inactive"
    
    await db.commit()
    await db.refresh(plugin)
    
    # 数据库操作完成后，再进行MCP操作
    if enabled:
        # 启用：注册到统一门面
        try:
            if plugin_type in ["http", "streamable_http", "sse"] and server_url:
                success = await mcp_client.register(MCPPluginConfig(
                    user_id=user.user_id,
                    plugin_name=plugin_name,
                    url=server_url,
                    plugin_type=plugin_type,
                    headers=headers,
                    timeout=config.get('timeout', 60.0) if config else 60.0
                ))
            else:
                success = False
            
            # 更新状态
            plugin.status = "active" if success else "error"
            plugin.last_error = None if success else "加载失败"
            await db.commit()
            await db.refresh(plugin)
        except Exception as e:
            logger.error(f"注册插件失败: {plugin_name}, 错误: {e}")
            plugin.status = "error"
            plugin.last_error = str(e)
            await db.commit()
            await db.refresh(plugin)
    else:
        # 禁用：从统一门面注销（不影响数据库状态）
        try:
            await mcp_client.unregister(user.user_id, plugin_name)
        except Exception as e:
            logger.warning(f"注销插件时出错（可忽略）: {plugin_name}, 错误: {e}")
    
    action = "启用" if enabled else "禁用"
    logger.info(f"用户 {user.user_id} {action}插件: {plugin_name}")
    return plugin


@router.post("/{plugin_id}/test", response_model=MCPTestResult)
async def test_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    测试插件连接并调用工具验证功能

    使用MCPTestService进行测试。
    如果插件会话尚未建立，会先在后台注册，需要再次调用测试。
    """

    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()

    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    if not plugin.enabled:
        return MCPTestResult(
            success=False,
            message="插件未启用",
            error="请先启用插件",
            suggestions=["点击开关按钮启用插件"]
        )

    # 检查会话是否已注册
    is_registered = mcp_client.is_registered(user.user_id, plugin.plugin_name)
    session_status = mcp_client.get_session_status(user.user_id, plugin.plugin_name)

    if not is_registered:
        # 会话不存在或状态异常，需要在后台注册
        logger.info(f"插件 {plugin.plugin_name} 会话不存在(状态: {session_status})，启动后台注册")

        # 更新数据库状态为pending
        plugin.status = "pending"
        plugin.last_error = None
        await db.commit()

        # 在后台注册插件
        asyncio.create_task(_register_plugin_background(
            user_id=user.user_id,
            plugin_name=plugin.plugin_name,
            plugin_type=plugin.plugin_type,
            server_url=plugin.server_url,
            headers=plugin.headers,
            config=plugin.config
        ))

        return MCPTestResult(
            success=False,
            message="正在建立连接...",
            error="插件会话正在初始化，请稍后重试",
            suggestions=[
                "插件正在连接MCP服务器",
                "请等待2-3秒后再次点击测试",
                "如果持续失败，请检查服务器地址是否正确"
            ]
        )

    # 会话已存在，直接执行测试
    try:
        test_result = await mcp_test_service.test_plugin_with_ai(plugin, user, db)

        # 更新插件状态
        if test_result.success:
            plugin.status = "active"
            plugin.last_error = None
        else:
            plugin.status = "error"
            plugin.last_error = test_result.error

        plugin.last_test_at = datetime.now()
        await db.commit()

        return test_result

    except Exception as e:
        logger.error(f"测试插件失败: {plugin.plugin_name}, 错误: {e}")
        plugin.status = "error"
        plugin.last_error = str(e)
        plugin.last_test_at = datetime.now()
        await db.commit()
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")


async def _ensure_plugin_registered(
    plugin: MCPPlugin,
    user_id: str
) -> bool:
    """
    确保插件已注册到统一门面
    
    Args:
        plugin: 插件对象
        user_id: 用户ID
        
    Returns:
        是否成功
        
    Raises:
        HTTPException: 注册失败
    """
    try:
        # 使用ensure_registered方法，它会检查是否已注册
        if plugin.plugin_type in ["http", "streamable_http", "sse"] and plugin.server_url:
            return await mcp_client.ensure_registered(
                user_id=user_id,
                plugin_name=plugin.plugin_name,
                url=plugin.server_url,
                plugin_type=plugin.plugin_type,
                headers=plugin.headers
            )
        return False
    except ValueError as e:
        logger.info(f"插件 {plugin.plugin_name} 未注册，自动注册中...")
        success = await _register_plugin_to_facade(plugin, user_id)
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"插件注册失败: {plugin.plugin_name}"
            )
        return True


@router.get("/{plugin_id}/status")
async def get_plugin_status(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """获取插件的实时状态（包括内存中的会话状态）"""
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    session_stats = mcp_client.get_session_stats()
    session_key = f"{user.user_id}:{plugin.plugin_name}"
    session_info = next((s for s in session_stats.get("sessions", []) if s["key"] == session_key), None)
    
    return {
        "plugin_id": plugin_id,
        "plugin_name": plugin.plugin_name,
        "db_status": plugin.status,
        "session_status": session_info["status"] if session_info else None,
        "is_registered": session_info is not None,
        "error_rate": session_info["error_rate"] if session_info else 0,
        "in_sync": (plugin.status == session_info["status"]) if session_info else (plugin.status == "inactive"),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/metrics")
async def get_metrics(
    tool_name: Optional[str] = Query(None, description="工具名称（可选，获取特定工具的指标）"),
    user: User = Depends(require_login)
):
    """
    获取MCP工具调用指标
    
    Query参数:
        - tool_name: 可选，指定工具名称获取特定工具的指标
        
    Returns:
        工具调用指标字典，包含：
        - total_calls: 总调用次数
        - success_calls: 成功调用次数
        - failed_calls: 失败调用次数
        - success_rate: 成功率
        - avg_duration_ms: 平均耗时（毫秒）
        - last_call_time: 最后调用时间
    """
    # 使用统一门面获取指标
    metrics = mcp_client.get_metrics(tool_name)
    
    return {
        "metrics": metrics,
        "tool_name": tool_name,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/cache/stats")
async def get_cache_stats(
    user: User = Depends(require_login)
):
    """
    获取工具缓存统计信息
    
    Returns:
        缓存统计信息，包含：
        - total_entries: 缓存条目总数
        - total_hits: 缓存总命中次数
        - cache_ttl_minutes: 缓存TTL（分钟）
        - entries: 各缓存条目详情
    """
    # 使用统一门面获取缓存统计
    stats = mcp_client.get_cache_stats()
    
    return {
        "cache_stats": stats,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/sessions/stats")
async def get_session_stats(
    user: User = Depends(require_login)
):
    """
    获取MCP会话统计信息
    
    Returns:
        会话统计信息，包含：
        - total_sessions: 会话总数
        - sessions: 各会话详情
    """
    # 使用统一门面获取会话统计
    stats = mcp_client.get_session_stats()
    
    return {
        "session_stats": stats,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/cache/clear")
async def clear_cache(
    user_id: Optional[str] = Query(None, description="用户ID（可选）"),
    plugin_name: Optional[str] = Query(None, description="插件名称（可选）"),
    user: User = Depends(require_login)
):
    """
    清理工具缓存
    
    Query参数:
        - user_id: 可选，清理特定用户的缓存
        - plugin_name: 可选，清理特定插件的缓存
        
    说明:
        - 不提供任何参数：清理所有缓存
        - 只提供user_id：清理该用户的所有缓存
        - 提供user_id和plugin_name：清理特定插件的缓存
    """
    # 非管理员只能清理自己的缓存
    if user_id and user_id != user.user_id:
        raise HTTPException(status_code=403, detail="无权清理其他用户的缓存")
    
    # 如果没有指定user_id，使用当前用户
    target_user_id = user_id or user.user_id
    
    # 使用统一门面清理缓存
    mcp_client.clear_cache(target_user_id, plugin_name)
    
    message = "已清理"
    if plugin_name:
        message += f"插件 {plugin_name} 的缓存"
    elif target_user_id:
        message += f"用户 {target_user_id} 的所有缓存"
    else:
        message += "所有缓存"
    
    logger.info(f"用户 {user.user_id} {message}")
    
    return {
        "success": True,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/{plugin_id}/tools")
async def get_plugin_tools(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取插件提供的工具列表
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    if not plugin.enabled:
        raise HTTPException(status_code=400, detail="插件未启用")
    
    try:
        # 确保插件已注册
        await _ensure_plugin_registered(plugin, user.user_id)
        
        # 使用统一门面获取工具列表
        tools = await mcp_client.get_tools(user.user_id, plugin.plugin_name)
        
        # 更新数据库中的工具缓存
        plugin.tools = tools
        await db.commit()
        
        return {
            "plugin_name": plugin.plugin_name,
            "tools": tools,
            "count": len(tools)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取工具列表失败: {plugin.plugin_name}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")


@router.post("/call")
async def call_mcp_tool(
    data: MCPToolCall,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    调用MCP工具
    """
    # 获取插件
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == data.plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    if not plugin.enabled:
        raise HTTPException(status_code=400, detail="插件未启用")
    
    try:
        # 确保插件已注册
        await _ensure_plugin_registered(plugin, user.user_id)
        
        # 使用统一门面调用工具
        tool_result = await mcp_client.call_tool(
            user_id=user.user_id,
            plugin_name=plugin.plugin_name,
            tool_name=data.tool_name,
            arguments=data.arguments
        )
        
        return {
            "success": True,
            "plugin_name": plugin.plugin_name,
            "tool_name": data.tool_name,
            "result": tool_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"调用工具失败: {plugin.plugin_name}.{data.tool_name}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"工具调用失败: {str(e)}")