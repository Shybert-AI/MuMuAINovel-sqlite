"""MCP客户端统一门面 - 所有MCP操作的唯一入口

本模块提供统一的MCP（Model Context Protocol）客户端接口，
整合了连接管理、工具操作、格式转换、缓存和指标收集等功能。

使用示例:
    from app.mcp import mcp_client, MCPPluginConfig
    
    # 注册插件
    await mcp_client.register(MCPPluginConfig(
        user_id="user123",
        plugin_name="exa-search",
        url="http://localhost:8000/mcp"
    ))
    
    # 获取工具列表
    tools = await mcp_client.get_tools("user123", "exa-search")
    
    # 调用工具
    result = await mcp_client.call_tool("user123", "exa-search", "web_search", {"query": "..."})
    
    # 注册状态变更回调
    async def on_status_change(event):
        print(f"插件 {event['plugin_name']} 状态: {event['old_status']} -> {event['new_status']}")
    
    mcp_client.register_status_callback(on_status_change)
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import asyncio
import time
import json

from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from anyio import ClosedResourceError

from app.mcp.config import mcp_config
from app.logger import get_logger

logger = get_logger(__name__)


# ==================== 数据结构 ====================

class PluginStatus(str, Enum):
    """插件状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    ERROR = "error"


# 状态变更回调类型
StatusCallback = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class MCPPluginConfig:
    """MCP插件配置"""
    user_id: str
    plugin_name: str
    url: str
    plugin_type: str = "streamable_http"  # streamable_http, sse, http
    headers: Optional[Dict[str, str]] = None
    env: Optional[Dict[str, str]] = None
    timeout: float = 60.0


@dataclass
class SessionInfo:
    """会话信息"""
    session: ClientSession
    url: str
    plugin_type: str = "streamable_http"
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    status: str = "active"  # active, degraded, error
    _context_stack: List = field(default_factory=list)
    _expiry_warned: bool = False
    
    @property
    def error_rate(self) -> float:
        """计算错误率"""
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count


@dataclass
class ToolCacheEntry:
    """工具缓存条目"""
    tools: List[Dict[str, Any]]
    expire_time: datetime
    hit_count: int = 0


@dataclass
class ToolMetrics:
    """工具调用指标"""
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    last_call_time: Optional[datetime] = None
    
    @property
    def avg_duration_ms(self) -> float:
        """平均调用时间"""
        return self.total_duration_ms / self.total_calls if self.total_calls > 0 else 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        return self.success_calls / self.total_calls if self.total_calls > 0 else 0.0
    
    def record_success(self, duration_ms: float):
        """记录成功调用"""
        self.total_calls += 1
        self.success_calls += 1
        self.total_duration_ms += duration_ms
        self.last_call_time = datetime.now()
    
    def record_failure(self, duration_ms: float):
        """记录失败调用"""
        self.total_calls += 1
        self.failed_calls += 1
        self.total_duration_ms += duration_ms
        self.last_call_time = datetime.now()


class MCPError(Exception):
    """MCP操作异常"""
    pass


# ==================== 统一门面 ====================

class MCPClientFacade:
    """
    MCP客户端统一门面
    
    这是所有MCP操作的唯一入口，提供：
    1. 连接管理（注册、注销、测试）
    2. 工具操作（获取、调用、批量调用）
    3. 格式转换（MCP ↔ OpenAI Function Calling）
    4. 缓存和指标
    
    设计模式：
    - 单例模式：全局唯一实例
    - 门面模式：统一对外接口
    
    线程安全：
    - 使用asyncio.Lock保护会话操作
    - 使用用户级别的细粒度锁避免阻塞
    """
    
    _instance: Optional['MCPClientFacade'] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 会话管理
        self._sessions: Dict[str, SessionInfo] = {}
        self._session_lock = asyncio.Lock()
        self._user_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        
        # 工具缓存
        self._tool_cache: Dict[str, ToolCacheEntry] = {}
        self._cache_ttl = timedelta(minutes=mcp_config.TOOL_CACHE_TTL_MINUTES)
        
        # 调用指标
        self._metrics: Dict[str, ToolMetrics] = defaultdict(ToolMetrics)
        
        # 后台任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._tasks_started = False
        
        # 状态变更回调
        self._status_callbacks: List[StatusCallback] = []
        
        self._initialized = True
        logger.info("✅ MCPClientFacade 初始化完成")
    
    def _get_key(self, user_id: str, plugin_name: str) -> str:
        """生成会话键"""
        return f"{user_id}:{plugin_name}"
    
    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户专属锁（细粒度锁）"""
        async with self._locks_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]
    
    def _ensure_background_tasks(self):
        """确保后台任务已启动（延迟初始化）"""
        if not self._tasks_started:
            try:
                loop = asyncio.get_running_loop()
                if self._cleanup_task is None:
                    self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                    logger.info("✅ MCP后台清理任务已启动")
                
                if self._health_check_task is None:
                    self._health_check_task = asyncio.create_task(self._health_check_loop())
                    logger.info("✅ MCP健康检查任务已启动")
                
                self._tasks_started = True
            except RuntimeError:
                # 没有运行中的事件循环，稍后再试
                pass
    
    async def _cleanup_loop(self):
        """后台清理过期会话"""
        while True:
            try:
                await asyncio.sleep(mcp_config.CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务异常: {e}")
    
    async def _health_check_loop(self):
        """后台健康检查"""
        while True:
            try:
                await asyncio.sleep(mcp_config.HEALTH_CHECK_INTERVAL_SECONDS)
                await self._check_session_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查任务异常: {e}")
    
    async def _cleanup_expired_sessions(self):
        """清理过期的会话"""
        now = time.time()
        expired_keys = []
        
        async with self._session_lock:
            for key, session in list(self._sessions.items()):
                if now - session.last_access > mcp_config.CLIENT_TTL_SECONDS:
                    expired_keys.append(key)
        
        if expired_keys:
            logger.info(f"🧹 清理 {len(expired_keys)} 个过期的MCP会话")
            for key in expired_keys:
                user_id = key.split(':', 1)[0]
                user_lock = await self._get_user_lock(user_id)
                async with user_lock:
                    await self._close_session_unsafe(key)
    
    async def _check_session_health(self):
        """检查会话健康状态"""
        async with self._session_lock:
            for key, session in list(self._sessions.items()):
                # 检查错误率
                if session.request_count > mcp_config.MIN_REQUESTS_FOR_HEALTH_CHECK:
                    old_status = session.status
                    user_id, plugin_name = key.split(':', 1)
                    
                    if session.error_rate > mcp_config.ERROR_RATE_CRITICAL:
                        if session.status != "error":
                            session.status = "error"
                            logger.error(f"❌ 会话 {key} 错误率过高 ({session.error_rate:.1%})")
                            await self._emit_status_change(user_id, plugin_name, old_status, "error",
                                f"错误率过高: {session.error_rate:.1%}")
                    elif session.error_rate > mcp_config.ERROR_RATE_WARNING:
                        if session.status == "active":
                            session.status = "degraded"
                            logger.warning(f"⚠️ 会话 {key} 健康状况下降 ({session.error_rate:.1%})")
                            await self._emit_status_change(user_id, plugin_name, old_status, "degraded",
                                f"错误率较高: {session.error_rate:.1%}")
                    elif session.status == "degraded":
                        session.status = "active"
                        logger.info(f"✅ 会话 {key} 恢复正常")
                        await self._emit_status_change(user_id, plugin_name, old_status, "active", "恢复正常")
    
    # ==================== 连接管理 ====================
    
    async def register(self, config: MCPPluginConfig) -> bool:
        """
        注册MCP插件并建立连接
        
        Args:
            config: 插件配置
            
        Returns:
            是否注册成功
        """
        self._ensure_background_tasks()

        key = self._get_key(config.user_id, config.plugin_name)
        user_lock = await self._get_user_lock(config.user_id)

        async with user_lock:
            # 如果已存在，先关闭
            if key in self._sessions:
                await self._close_session_unsafe(key)

            try:
                logger.info(f"🔗 连接MCP服务器: {config.plugin_name} -> {config.url} (类型: {config.plugin_type})")

                # 根据类型选择客户端
                if config.plugin_type == "sse":
                    # SSE 客户端 - 返回 2 个值
                    stream_ctx = sse_client(
                        url=config.url,
                        headers=config.headers,
                        timeout=config.timeout
                    )
                    read, write = await stream_ctx.__aenter__()
                else:
                    # streamable_http 客户端（默认，也用于 http 类型）- 返回 3 个值
                    stream_ctx = streamablehttp_client(
                        url=config.url,
                        headers=config.headers,
                        timeout=config.timeout
                    )
                    read, write, _ = await stream_ctx.__aenter__()
                
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                
                now = time.time()
                info = SessionInfo(
                    session=session,
                    url=config.url,
                    plugin_type=config.plugin_type,
                    created_at=now,
                    last_access=now,
                    _context_stack=[('stream', stream_ctx), ('session', session)]
                )
                
                async with self._session_lock:
                    self._sessions[key] = info
                
                logger.info(f"✅ MCP会话建立成功: {key}")
                await self._emit_status_change(config.user_id, config.plugin_name, "inactive", "active", "连接成功")
                return True

            except ExceptionGroup as eg:
                # 处理 TaskGroup 的异常组，提取详细错误信息
                error_details = []
                for exc in eg.exceptions:
                    error_details.append(f"{type(exc).__name__}: {exc}")
                error_msg = "; ".join(error_details)
                logger.error(f"❌ MCP连接失败 {key}: TaskGroup异常 - {error_msg}")
                await self._emit_status_change(config.user_id, config.plugin_name, "inactive", "error", error_msg)
                return False

            except Exception as e:
                logger.error(f"❌ MCP连接失败 {key}: {type(e).__name__}: {e}")
                await self._emit_status_change(config.user_id, config.plugin_name, "inactive", "error", str(e))
                return False
    
    async def unregister(self, user_id: str, plugin_name: str):
        """
        注销MCP插件
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
        """
        key = self._get_key(user_id, plugin_name)
        user_lock = await self._get_user_lock(user_id)
        
        old_status = self._sessions.get(key, SessionInfo(session=None, url="")).status if key in self._sessions else "active"
        
        async with user_lock:
            await self._close_session_unsafe(key)
            self._invalidate_cache(key)
        
        await self._emit_status_change(user_id, plugin_name, old_status, "inactive", "已注销")
    
    async def _close_session_unsafe(self, key: str):
        """关闭会话（不加用户锁，需要调用者确保线程安全）"""
        async with self._session_lock:
            info = self._sessions.pop(key, None)
        
        if info:
            # 按LIFO顺序清理上下文
            for ctx_type, ctx in reversed(info._context_stack):
                try:
                    await ctx.__aexit__(None, None, None)
                except RuntimeError as e:
                    if "cancel scope" in str(e).lower() or "different task" in str(e).lower():
                        logger.debug(f"忽略{ctx_type}上下文清理的任务切换警告: {e}")
                    else:
                        logger.error(f"清理{ctx_type}上下文失败: {e}")
                except Exception as e:
                    logger.debug(f"清理{ctx_type}上下文: {e}")
            
            logger.info(f"🗑️ 关闭MCP会话: {key}")
    
    async def _get_session(self, user_id: str, plugin_name: str) -> ClientSession:
        """
        获取会话
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            
        Returns:
            ClientSession实例
            
        Raises:
            ValueError: 会话不存在
        """
        key = self._get_key(user_id, plugin_name)
        
        info = self._sessions.get(key)
        if not info:
            raise ValueError(f"MCP会话不存在: {plugin_name}，请先调用register()")
        
        if info.status == "error":
            logger.warning(f"⚠️ 会话 {key} 处于错误状态，可能需要重新注册")
        
        info.last_access = time.time()
        info.request_count += 1
        return info.session

    def is_registered(self, user_id: str, plugin_name: str) -> bool:
        """
        检查插件是否已注册（同步方法，仅检查内存状态）

        Args:
            user_id: 用户ID
            plugin_name: 插件名称

        Returns:
            是否已注册且状态正常
        """
        key = self._get_key(user_id, plugin_name)
        info = self._sessions.get(key)
        return info is not None and info.status != "error"

    def get_session_status(self, user_id: str, plugin_name: str) -> Optional[str]:
        """
        获取会话状态（同步方法）

        Args:
            user_id: 用户ID
            plugin_name: 插件名称

        Returns:
            会话状态，如果不存在返回 None
        """
        key = self._get_key(user_id, plugin_name)
        info = self._sessions.get(key)
        return info.status if info else None

    async def ensure_registered(
        self,
        user_id: str,
        plugin_name: str,
        url: str,
        plugin_type: str = "streamable_http",
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        确保插件已注册（如果未注册则自动注册）
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            url: 服务器URL
            plugin_type: 插件类型 (streamable_http, sse, http)
            headers: HTTP头
            
        Returns:
            是否成功
        """
        key = self._get_key(user_id, plugin_name)
        
        if key in self._sessions:
            info = self._sessions[key]
            # 检查URL和类型是否变化
            if info.url == url and info.plugin_type == plugin_type and info.status != "error":
                return True
        
        # 注册
        return await self.register(MCPPluginConfig(
            user_id=user_id,
            plugin_name=plugin_name,
            url=url,
            plugin_type=plugin_type,
            headers=headers
        ))
    
    async def test_connection(self, user_id: str, plugin_name: str) -> Dict[str, Any]:
        """
        测试连接
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            
        Returns:
            测试结果字典
        """
        start = time.time()
        
        try:
            session = await self._get_session(user_id, plugin_name)
            result = await session.list_tools()
            
            tools = [
                {"name": t.name, "description": t.description or ""}
                for t in result.tools
            ]
            
            return {
                "success": True,
                "message": "连接成功",
                "response_time_ms": round((time.time() - start) * 1000, 2),
                "tools_count": len(tools),
                "tools": tools
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "response_time_ms": round((time.time() - start) * 1000, 2),
                "error_type": type(e).__name__
            }
    
    # ==================== 工具操作 ====================
    
    async def get_tools(
        self, 
        user_id: str, 
        plugin_name: str,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取工具列表
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            use_cache: 是否使用缓存
            
        Returns:
            工具列表 [{"name": ..., "description": ..., "inputSchema": ...}]
        """
        cache_key = self._get_key(user_id, plugin_name)
        now = datetime.now()
        
        # 检查缓存
        if use_cache and cache_key in self._tool_cache:
            entry = self._tool_cache[cache_key]
            if now < entry.expire_time:
                entry.hit_count += 1
                logger.debug(f"🎯 工具缓存命中: {cache_key} (命中次数: {entry.hit_count})")
                return entry.tools
            else:
                del self._tool_cache[cache_key]
                logger.debug(f"⏰ 工具缓存过期: {cache_key}")
        
        # 从服务器获取
        session = await self._get_session(user_id, plugin_name)
        result = await session.list_tools()
        
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema
            }
            for t in result.tools
        ]
        
        # 更新缓存
        self._tool_cache[cache_key] = ToolCacheEntry(
            tools=tools,
            expire_time=now + self._cache_ttl
        )
        
        logger.info(f"获取到 {len(tools)} 个工具: {plugin_name}")
        return tools
    
    async def call_tool(
        self,
        user_id: str,
        plugin_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None,
        max_reconnect_attempts: int = 2
    ) -> Any:
        """
        调用单个工具
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            tool_name: 工具名称
            arguments: 工具参数
            timeout: 超时时间（秒）
            max_reconnect_attempts: 最大重连次数
            
        Returns:
            工具执行结果
        """
        tool_key = f"{plugin_name}.{tool_name}"
        start_time = time.time()
        actual_timeout = timeout or mcp_config.TOOL_CALL_TIMEOUT_SECONDS
        
        for attempt in range(max_reconnect_attempts + 1):
            try:
                session = await self._get_session(user_id, plugin_name)
                
                logger.info(f"调用工具: {tool_key}")
                logger.debug(f"  参数: {arguments}")
                
                # 带超时调用
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=actual_timeout
                )
                
                # 处理返回结果
                output = self._extract_tool_result(result)
                
                # 记录成功指标
                duration_ms = (time.time() - start_time) * 1000
                self._metrics[tool_key].record_success(duration_ms)
                
                logger.info(f"✅ 工具调用成功: {tool_key} ({duration_ms:.2f}ms)")
                return output
                
            except asyncio.TimeoutError:
                duration_ms = (time.time() - start_time) * 1000
                self._metrics[tool_key].record_failure(duration_ms)
                raise MCPError(f"工具调用超时（>{actual_timeout}秒）")
                
            except ClosedResourceError as e:
                # 连接已关闭，尝试重连
                if attempt < max_reconnect_attempts:
                    logger.warning(f"⚠️ MCP连接已关闭，尝试重连 (第{attempt + 1}/{max_reconnect_attempts}次)")
                    key = self._get_key(user_id, plugin_name)
                    
                    # 保存旧的会话信息用于重新注册
                    old_info = None
                    async with self._session_lock:
                        if key in self._sessions:
                            old_info = self._sessions[key]
                    
                    # 关闭旧会话
                    try:
                        await self._close_session_unsafe(key)
                    except Exception as close_err:
                        logger.debug(f"关闭旧会话时出错: {close_err}")
                    
                    # 使用旧的会话信息重新注册
                    url = old_info.url if old_info else ""
                    plugin_type = old_info.plugin_type if old_info else "streamable_http"
                    
                    if url:
                        success = await self.ensure_registered(
                            user_id, plugin_name, url, plugin_type
                        )
                        if success:
                            logger.info(f"✅ MCP会话重新建立成功: {key}")
                            await asyncio.sleep(0.5)
                            continue
                    
                    # 如果无法获取旧信息或重新注册失败，等待后重试
                    await asyncio.sleep(0.5)
                    continue
                else:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics[tool_key].record_failure(duration_ms)
                    raise MCPError(f"连接已关闭且重连失败 (尝试了{max_reconnect_attempts}次)")
            
            except ValueError as e:
                # 会话不存在，尝试重新注册
                if "MCP会话不存在" in str(e) and attempt < max_reconnect_attempts:
                    logger.warning(f"⚠️ MCP会话不存在，尝试重新注册 (第{attempt + 1}/{max_reconnect_attempts}次)")
                    
                    # 尝试获取会话信息用于重新注册
                    key = self._get_key(user_id, plugin_name)
                    old_info = None
                    async with self._session_lock:
                        if key in self._sessions:
                            old_info = self._sessions[key]
                    
                    url = old_info.url if old_info else ""
                    plugin_type = old_info.plugin_type if old_info else "streamable_http"
                    
                    if url:
                        success = await self.ensure_registered(
                            user_id, plugin_name, url, plugin_type
                        )
                        if success:
                            logger.info(f"✅ MCP会话重新注册成功: {key}")
                            await asyncio.sleep(0.5)
                            continue
                    
                    await asyncio.sleep(0.5)
                    continue
                else:
                    duration_ms = (time.time() - start_time) * 1000
                    self._metrics[tool_key].record_failure(duration_ms)
                    raise MCPError(f"会话不存在: {e}")
                    
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                self._metrics[tool_key].record_failure(duration_ms)
                
                # 更新会话错误计数
                key = self._get_key(user_id, plugin_name)
                if key in self._sessions:
                    session_info = self._sessions[key]
                    session_info.error_count += 1
                    
                    # 检查是否需要更新状态
                    if session_info.request_count >= mcp_config.MIN_REQUESTS_FOR_HEALTH_CHECK:
                        old_status = session_info.status
                        if session_info.error_rate > mcp_config.ERROR_RATE_CRITICAL and old_status != "error":
                            session_info.status = "error"
                            asyncio.create_task(self._emit_status_change(
                                user_id, plugin_name, old_status, "error", f"错误率过高: {session_info.error_rate:.1%}"
                            ))
                        elif session_info.error_rate > mcp_config.ERROR_RATE_WARNING and old_status == "active":
                            session_info.status = "degraded"
                            asyncio.create_task(self._emit_status_change(
                                user_id, plugin_name, old_status, "degraded", f"错误率较高: {session_info.error_rate:.1%}"
                            ))
                
                error_msg = str(e)
                error_type = type(e).__name__
                
                # 检查是否是 JSON 解析错误（MCP SDK 内部错误）
                if "parsing JSON" in error_msg.lower() or "json" in error_msg.lower():
                    logger.error(f"❌ 工具调用失败 (JSON解析错误): {tool_key}: {e}")
                    raise MCPError(f"MCP服务器响应格式错误，请检查服务器状态或稍后重试")
                
                logger.error(f"❌ 工具调用失败: {tool_key} [{error_type}]: {e}")
                raise MCPError(f"工具调用失败: {error_msg}")
        
        raise MCPError("工具调用失败: 未知错误")
    
    def _extract_tool_result(self, result) -> Any:
        """从MCP结果中提取实际内容"""
        if result.content:
            for content in result.content:
                if isinstance(content, types.TextContent):
                    return content.text
                elif isinstance(content, types.ImageContent):
                    return {
                        "type": "image",
                        "data": content.data,
                        "mimeType": content.mimeType
                    }
            return result.content[0] if result.content else None
        
        if hasattr(result, 'structuredContent') and result.structuredContent:
            return result.structuredContent
        
        return None
    
    async def batch_call_tools(
        self,
        user_id: str,
        tool_calls: List[Dict[str, Any]],
        max_concurrent: int = 2,
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        批量执行AI返回的工具调用
        
        Args:
            user_id: 用户ID
            tool_calls: AI返回的工具调用列表，格式：
                [{"id": "...", "function": {"name": "plugin_tool", "arguments": "{...}"}}]
            max_concurrent: 最大并发数
            timeout: 单个工具超时时间
            
        Returns:
            工具调用结果列表
        """
        if not tool_calls:
            return []
        
        logger.info(f"开始执行 {len(tool_calls)} 个工具调用 (最大并发={max_concurrent})")
        
        results = []
        
        for i in range(0, len(tool_calls), max_concurrent):
            batch = tool_calls[i:i+max_concurrent]
            batch_num = i // max_concurrent + 1
            total_batches = (len(tool_calls) + max_concurrent - 1) // max_concurrent
            
            logger.info(f"执行工具批次 {batch_num}/{total_batches}, 数量: {len(batch)}")
            
            tasks = [
                self._execute_single_tool_call(user_id, tc, timeout)
                for tc in batch
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                tc = batch[j]
                if isinstance(result, Exception):
                    results.append({
                        "tool_call_id": tc.get("id", f"call_{i+j}"),
                        "role": "tool",
                        "name": tc["function"]["name"],
                        "content": f"工具调用失败: {str(result)}",
                        "success": False,
                        "error": str(result)
                    })
                else:
                    results.append(result)
            
            # 批次间延迟，避免API限流
            if i + max_concurrent < len(tool_calls):
                await asyncio.sleep(0.3)
        
        return results
    
    async def _execute_single_tool_call(
        self, 
        user_id: str, 
        tool_call: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """执行单个工具调用"""
        tool_call_id = tool_call.get("id", "unknown")
        function_name = tool_call["function"]["name"]
        
        try:
            # 解析插件名和工具名
            plugin_name, tool_name = self.parse_function_name(function_name)
            
            # 解析参数
            arguments = tool_call["function"]["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            
            # 调用工具
            result = await self.call_tool(
                user_id=user_id,
                plugin_name=plugin_name,
                tool_name=tool_name,
                arguments=arguments,
                timeout=timeout
            )
            
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(result, ensure_ascii=False) if result else "",
                "success": True
            }
            
        except json.JSONDecodeError as e:
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": function_name,
                "content": f"参数JSON解析失败: {str(e)}",
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": function_name,
                "content": f"工具调用失败: {str(e)}",
                "success": False,
                "error": str(e)
            }
    
    # ==================== 格式转换 ====================
    
    def format_tools_for_openai(
        self, 
        tools: List[Dict[str, Any]], 
        plugin_name: str
    ) -> List[Dict[str, Any]]:
        """
        将MCP工具转换为OpenAI Function Calling格式
        
        Args:
            tools: MCP工具列表
            plugin_name: 插件名称（作为前缀）
            
        Returns:
            OpenAI格式的工具列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{plugin_name}_{tool['name']}",
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            for tool in tools
        ]
    
    def parse_function_name(self, function_name: str) -> tuple:
        """
        解析函数名为插件名和工具名
        
        支持两种格式：
        - "plugin_tool" (下划线分隔)
        - "plugin.tool" (点号分隔)
        
        Args:
            function_name: 工具名称
            
        Returns:
            (plugin_name, tool_name)
            
        Raises:
            ValueError: 格式无效
        """
        # 优先尝试用下划线分割
        if "_" in function_name:
            parts = function_name.split("_", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return (parts[0], parts[1])
        
        # 如果下划线分割失败，尝试用点号分割
        if "." in function_name:
            parts = function_name.split(".", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                logger.debug(f"🔧 工具名使用点号分隔: {function_name} -> plugin={parts[0]}, tool={parts[1]}")
                return (parts[0], parts[1])
        
        raise ValueError(f"无效的工具名称格式: {function_name}，应为 'plugin_tool' 或 'plugin.tool' 格式")
    
    def build_tool_context(
        self, 
        tool_results: List[Dict[str, Any]], 
        format: str = "markdown"
    ) -> str:
        """
        将工具结果格式化为上下文
        
        Args:
            tool_results: 工具调用结果列表
            format: 输出格式（markdown/json/plain）
            
        Returns:
            格式化的上下文字符串
        """
        if not tool_results:
            return ""
        
        if format == "markdown":
            return self._build_markdown_context(tool_results)
        elif format == "json":
            return json.dumps(tool_results, ensure_ascii=False, indent=2)
        else:
            return self._build_plain_context(tool_results)
    
    def _build_markdown_context(self, tool_results: List[Dict[str, Any]]) -> str:
        """构建Markdown格式的工具上下文"""
        lines = ["## 🔧 工具调用结果\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("name", "unknown")
            success = result.get("success", False)
            content = result.get("content", "")
            
            status_emoji = "✅" if success else "❌"
            lines.append(f"### {status_emoji} {i}. {tool_name}\n")
            
            if success:
                # 尝试美化JSON内容
                try:
                    content_obj = json.loads(content)
                    content = json.dumps(content_obj, ensure_ascii=False, indent=2)
                except:
                    pass
                lines.append(f"```json\n{content}\n```\n")
            else:
                lines.append(f"**错误**: {content}\n")
        
        return "\n".join(lines)
    
    def _build_plain_context(self, tool_results: List[Dict[str, Any]]) -> str:
        """构建纯文本格式的工具上下文"""
        lines = ["=== 工具调用结果 ===\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("name", "unknown")
            success = result.get("success", False)
            content = result.get("content", "")
            
            status = "成功" if success else "失败"
            lines.append(f"{i}. {tool_name} - {status}")
            lines.append(f"   结果: {content}\n")
        
        return "\n".join(lines)
    
    # ==================== 缓存和指标 ====================
    
    def _invalidate_cache(self, key: str):
        """使缓存失效"""
        if key in self._tool_cache:
            del self._tool_cache[key]
            logger.debug(f"🧹 已清理缓存: {key}")
    
    def clear_cache(
        self, 
        user_id: Optional[str] = None, 
        plugin_name: Optional[str] = None
    ):
        """
        清理缓存
        
        Args:
            user_id: 用户ID（可选）
            plugin_name: 插件名称（可选）
        """
        if user_id and plugin_name:
            key = self._get_key(user_id, plugin_name)
            self._invalidate_cache(key)
            logger.info(f"🧹 已清理缓存: {key}")
        elif user_id:
            keys = [k for k in self._tool_cache if k.startswith(f"{user_id}:")]
            for k in keys:
                del self._tool_cache[k]
            logger.info(f"🧹 已清理用户缓存: {user_id} ({len(keys)}个)")
        else:
            count = len(self._tool_cache)
            self._tool_cache.clear()
            logger.info(f"🧹 已清理所有缓存 ({count}个)")
    
    def get_metrics(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取调用指标
        
        Args:
            tool_name: 工具名称（可选）
            
        Returns:
            指标字典
        """
        if tool_name and tool_name in self._metrics:
            m = self._metrics[tool_name]
            return {
                tool_name: {
                    "total_calls": m.total_calls,
                    "success_calls": m.success_calls,
                    "failed_calls": m.failed_calls,
                    "success_rate": round(m.success_rate, 3),
                    "avg_duration_ms": round(m.avg_duration_ms, 2),
                    "last_call_time": m.last_call_time.isoformat() if m.last_call_time else None
                }
            }
        
        return {
            k: {
                "total_calls": m.total_calls,
                "success_calls": m.success_calls,
                "failed_calls": m.failed_calls,
                "success_rate": round(m.success_rate, 3),
                "avg_duration_ms": round(m.avg_duration_ms, 2),
                "last_call_time": m.last_call_time.isoformat() if m.last_call_time else None
            }
            for k, m in self._metrics.items()
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "total_entries": len(self._tool_cache),
            "total_hits": sum(e.hit_count for e in self._tool_cache.values()),
            "cache_ttl_minutes": self._cache_ttl.total_seconds() / 60,
            "entries": [
                {
                    "key": k,
                    "tools_count": len(e.tools),
                    "hit_count": e.hit_count,
                    "expire_time": e.expire_time.isoformat()
                }
                for k, e in self._tool_cache.items()
            ]
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        return {
            "total_sessions": len(self._sessions),
            "sessions": [
                {
                    "key": k,
                    "url": s.url,
                    "status": s.status,
                    "request_count": s.request_count,
                    "error_count": s.error_count,
                    "error_rate": round(s.error_rate, 3),
                    "created_at": datetime.fromtimestamp(s.created_at).isoformat(),
                    "last_access": datetime.fromtimestamp(s.last_access).isoformat()
                }
                for k, s in self._sessions.items()
            ]
        }
    
    # ==================== 状态回调 ====================
    
    def register_status_callback(self, callback: StatusCallback):
        """注册状态变更回调"""
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)
            logger.info(f"✅ 已注册状态变更回调: {callback.__name__ if hasattr(callback, '__name__') else 'anonymous'}")
    
    def unregister_status_callback(self, callback: StatusCallback):
        """注销状态变更回调"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    async def _emit_status_change(
        self,
        user_id: str,
        plugin_name: str,
        old_status: str,
        new_status: str,
        reason: str = ""
    ):
        """触发状态变更事件"""
        if old_status == new_status:
            return
        
        event = {
            "user_id": user_id,
            "plugin_name": plugin_name,
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"📢 状态变更: {plugin_name} [{old_status} -> {new_status}] {reason}")
        
        for callback in self._status_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"状态回调执行失败: {e}")
    
    # ==================== 生命周期 ====================
    
    async def cleanup(self):
        """清理所有资源"""
        # 停止后台任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        async with self._session_lock:
            keys = list(self._sessions.keys())
        
        for key in keys:
            await self._close_session_unsafe(key)
        
        # 清理缓存
        self._tool_cache.clear()
        
        self._tasks_started = False
        logger.info("✅ MCPClientFacade 资源已清理")


# ==================== 全局单例 ====================

mcp_client = MCPClientFacade()