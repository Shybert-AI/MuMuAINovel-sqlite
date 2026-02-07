"""MCP模块 - 统一的MCP客户端管理

本模块提供MCP（Model Context Protocol）客户端的统一管理接口。

推荐使用方式：
    from app.mcp import mcp_client, MCPPluginConfig
    
    # 注册插件
    await mcp_client.register(MCPPluginConfig(
        user_id="user123",
        plugin_name="exa-search",
        url="http://localhost:8000/mcp"
    ))
    
    # 获取工具
    tools = await mcp_client.get_tools("user123", "exa-search")
    
    # 调用工具
    result = await mcp_client.call_tool("user123", "exa-search", "web_search", {"query": "..."})
    
    # 注册状态变更回调
    from app.mcp.status_sync import register_status_sync
    register_status_sync()
"""

from .facade import mcp_client, MCPClientFacade, MCPPluginConfig, MCPError, PluginStatus
from .status_sync import register_status_sync

__all__ = [
    "mcp_client",
    "MCPClientFacade",
    "MCPPluginConfig",
    "MCPError",
    "PluginStatus",
    "register_status_sync",
]