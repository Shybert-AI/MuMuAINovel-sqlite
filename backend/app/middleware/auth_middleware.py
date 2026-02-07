"""
认证中间件 - 从 Cookie 中提取用户信息并注入到 request.state
支持来自其他实例的代理请求（提示词工坊功能）
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.user_manager import user_manager
from app.logger import get_logger

logger = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件"""
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求，从 Cookie 或 Header 中提取用户 ID 并注入到 request.state
        
        对于提示词工坊相关的代理请求（带有 X-Instance-ID Header），
        从 Header 中读取用户标识而不是 Cookie。
        """
        # 检查是否为来自其他实例的代理请求（提示词工坊）
        instance_id = request.headers.get("X-Instance-ID")
        is_workshop_path = request.url.path.startswith("/api/prompt-workshop")
        
        if instance_id and is_workshop_path:
            # 来自其他实例的代理请求
            header_user_id = request.headers.get("X-User-ID")
            
            request.state.is_proxy_request = True
            request.state.proxy_instance_id = instance_id
            
            if header_user_id:
                # 有用户标识，使用代理的用户信息
                request.state.user_id = header_user_id  # 这是 "instance:user_id" 格式
                request.state.user = None  # 代理请求没有实际的 User 对象
                request.state.is_admin = False
            else:
                # 没有用户标识，匿名访问
                request.state.user_id = None
                request.state.user = None
                request.state.is_admin = False
        else:
            # 本地请求或非工坊路径，使用 Cookie 认证
            request.state.is_proxy_request = False
            request.state.proxy_instance_id = None
            
            # 从 Cookie 中获取用户 ID
            user_id = request.cookies.get("user_id")
            
            if user_id:
                user = await user_manager.get_user(user_id)
                if user:
                    # 检查用户是否被禁用 (trust_level = -1)
                    if user.trust_level == -1:
                        logger.warning(f"禁用用户尝试访问: {user_id} ({user.username})")
                        # 清除用户状态，视为未登录
                        request.state.user_id = None
                        request.state.user = None
                        request.state.is_admin = False
                    else:
                        # 用户正常，注入状态
                        request.state.user_id = user_id
                        request.state.user = user
                        request.state.is_admin = user.is_admin
                else:
                    # 用户不存在，清除状态
                    request.state.user_id = None
                    request.state.user = None
                    request.state.is_admin = False
            else:
                # 未登录
                request.state.user_id = None
                request.state.user = None
                request.state.is_admin = False
        
        # 继续处理请求
        response = await call_next(request)
        return response