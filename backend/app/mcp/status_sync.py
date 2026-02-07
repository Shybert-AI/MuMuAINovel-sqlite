"""MCP插件状态同步服务

将内存中的会话状态变更同步到数据库，确保状态一致性。
"""

import asyncio
from typing import Dict, Any
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.mcp_plugin import MCPPlugin
from app.logger import get_logger

logger = get_logger(__name__)

# 状态同步队列
_sync_queue: asyncio.Queue = None
_sync_task: asyncio.Task = None


async def _sync_worker():
    """后台状态同步工作线程"""
    global _sync_queue

    while True:
        try:
            event = await _sync_queue.get()
            if event is None:  # 停止信号
                break

            await _do_sync_status(event)
            _sync_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"状态同步工作线程异常: {e}")


async def _do_sync_status(event: Dict[str, Any]):
    """实际执行状态同步"""
    user_id = event["user_id"]
    plugin_name = event["plugin_name"]
    new_status = event["new_status"]
    reason = event.get("reason", "")

    try:
        from app.database import get_engine

        engine = await get_engine(user_id)
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with AsyncSessionLocal() as db:
            stmt = (
                update(MCPPlugin)
                .where(MCPPlugin.user_id == user_id, MCPPlugin.plugin_name == plugin_name)
                .values(status=new_status, last_error=reason if new_status == "error" else None)
            )
            await db.execute(stmt)
            await db.commit()

            logger.debug(f"✅ 状态已同步到数据库: {plugin_name} -> {new_status}")

    except Exception as e:
        logger.error(f"❌ 状态同步失败: {plugin_name}, 错误: {e}")


async def sync_status_to_db(event: Dict[str, Any]):
    """
    状态变更回调 - 将事件加入队列异步同步到数据库

    使用队列异步处理，避免在请求处理过程中阻塞或产生数据库连接冲突
    """
    global _sync_queue, _sync_task

    # 延迟初始化队列和工作线程
    if _sync_queue is None:
        _sync_queue = asyncio.Queue()

    if _sync_task is None or _sync_task.done():
        _sync_task = asyncio.create_task(_sync_worker())
        logger.info("✅ MCP状态同步工作线程已启动")

    # 将事件加入队列（非阻塞）
    try:
        _sync_queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning(f"状态同步队列已满，丢弃事件: {event['plugin_name']}")


def register_status_sync():
    """注册状态同步回调到MCP客户端"""
    from app.mcp import mcp_client
    mcp_client.register_status_callback(sync_status_to_db)
    logger.info("✅ MCP状态同步服务已注册")
