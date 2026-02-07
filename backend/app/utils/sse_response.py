"""Server-Sent Events (SSE) 响应工具类"""
import json
import asyncio
from enum import Enum
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from dataclasses import dataclass
from fastapi.responses import StreamingResponse
from app.logger import get_logger

logger = get_logger(__name__)


class ProgressStage(Enum):
    """标准化进度阶段枚举"""
    # 初始化阶段 (0-5%)
    INIT = "init"
    # 加载数据阶段 (5-15%)
    LOADING = "loading"
    # 准备提示词阶段 (15-20%)
    PREPARING = "preparing"
    # AI生成阶段 (20-85%)
    GENERATING = "generating"
    # 解析数据阶段 (85-92%)
    PARSING = "parsing"
    # 保存数据阶段 (92-98%)
    SAVING = "saving"
    # 完成阶段 (100%)
    COMPLETE = "complete"


@dataclass
class StageConfig:
    """阶段配置"""
    start: int  # 起始进度
    end: int    # 结束进度
    default_message: str  # 默认消息


# 标准进度阶段配置
STAGE_CONFIGS: Dict[ProgressStage, StageConfig] = {
    ProgressStage.INIT: StageConfig(0, 5, "开始处理..."),
    ProgressStage.LOADING: StageConfig(5, 15, "加载数据中..."),
    ProgressStage.PREPARING: StageConfig(15, 20, "准备AI提示词..."),
    ProgressStage.GENERATING: StageConfig(20, 85, "AI生成中..."),
    ProgressStage.PARSING: StageConfig(85, 92, "解析数据..."),
    ProgressStage.SAVING: StageConfig(92, 98, "保存到数据库..."),
    ProgressStage.COMPLETE: StageConfig(100, 100, "完成!"),
}


class WizardProgressTracker:
    """
    向导进度追踪器 - 标准化管理SSE进度推送
    
    使用示例:
        tracker = WizardProgressTracker("世界观")
        yield await tracker.start()
        yield await tracker.loading("加载项目信息")
        yield await tracker.preparing()
        async for chunk in ai_stream:
            yield await tracker.generating_chunk(chunk, len(accumulated))
        yield await tracker.parsing()
        yield await tracker.saving("保存世界观数据")
        yield await tracker.complete()
    """
    
    def __init__(self, task_name: str = "任务"):
        """
        初始化进度追踪器
        
        Args:
            task_name: 任务名称，用于消息前缀
        """
        self.task_name = task_name
        self.current_stage = ProgressStage.INIT
        self.current_progress = 0
        self._last_generating_progress = 20  # 生成阶段的最后进度值
    
    def _get_stage_progress(
        self,
        stage: ProgressStage,
        sub_progress: float = 0.0
    ) -> int:
        """
        计算阶段内的进度值
        
        Args:
            stage: 当前阶段
            sub_progress: 阶段内子进度 (0.0-1.0)
        
        Returns:
            总进度值 (0-100)
        """
        config = STAGE_CONFIGS[stage]
        if sub_progress <= 0:
            return config.start
        if sub_progress >= 1:
            return config.end
        return config.start + int((config.end - config.start) * sub_progress)
    
    async def start(self, message: str = None) -> str:
        """开始阶段"""
        self.current_stage = ProgressStage.INIT
        self.current_progress = 0
        msg = message or f"开始生成{self.task_name}..."
        return await SSEResponse.send_progress(msg, 0, "processing")
    
    async def loading(self, message: str = None, sub_progress: float = 0.5) -> str:
        """加载数据阶段"""
        self.current_stage = ProgressStage.LOADING
        progress = self._get_stage_progress(ProgressStage.LOADING, sub_progress)
        self.current_progress = progress
        msg = message or STAGE_CONFIGS[ProgressStage.LOADING].default_message
        return await SSEResponse.send_progress(msg, progress, "processing")
    
    async def preparing(self, message: str = None) -> str:
        """准备提示词阶段"""
        self.current_stage = ProgressStage.PREPARING
        progress = self._get_stage_progress(ProgressStage.PREPARING, 0.5)
        self.current_progress = progress
        msg = message or STAGE_CONFIGS[ProgressStage.PREPARING].default_message
        return await SSEResponse.send_progress(msg, progress, "processing")
    
    async def generating(
        self,
        current_chars: int = 0,
        estimated_total: int = 5000,
        message: str = None,
        retry_count: int = 0,
        max_retries: int = 3
    ) -> str:
        """
        AI生成阶段进度更新
        
        Args:
            current_chars: 当前已生成字符数
            estimated_total: 预估总字符数
            message: 自定义消息
            retry_count: 当前重试次数
            max_retries: 最大重试次数
        """
        self.current_stage = ProgressStage.GENERATING
        
        # 计算生成进度 (0.0-1.0)
        sub_progress = min(current_chars / max(estimated_total, 1), 1.0)
        progress = self._get_stage_progress(ProgressStage.GENERATING, sub_progress)
        
        # 确保进度单调递增
        if progress < self._last_generating_progress:
            progress = self._last_generating_progress
        else:
            self._last_generating_progress = progress
        
        self.current_progress = progress
        
        # 构建消息
        retry_suffix = f" (重试 {retry_count}/{max_retries})" if retry_count > 0 else ""
        if message:
            msg = f"{message}{retry_suffix}"
        else:
            msg = f"生成{self.task_name}中... ({current_chars}字符){retry_suffix}"
        
        return await SSEResponse.send_progress(msg, progress, "processing")
    
    async def generating_chunk(self, chunk: str) -> str:
        """发送生成的内容块"""
        return await SSEResponse.send_chunk(chunk)
    
    async def parsing(self, message: str = None, sub_progress: float = 0.5) -> str:
        """解析数据阶段"""
        self.current_stage = ProgressStage.PARSING
        progress = self._get_stage_progress(ProgressStage.PARSING, sub_progress)
        self.current_progress = progress
        msg = message or f"解析{self.task_name}数据..."
        return await SSEResponse.send_progress(msg, progress, "processing")
    
    async def saving(self, message: str = None, sub_progress: float = 0.5) -> str:
        """保存数据阶段"""
        self.current_stage = ProgressStage.SAVING
        progress = self._get_stage_progress(ProgressStage.SAVING, sub_progress)
        self.current_progress = progress
        msg = message or f"保存{self.task_name}到数据库..."
        return await SSEResponse.send_progress(msg, progress, "processing")
    
    async def complete(self, message: str = None) -> str:
        """完成阶段"""
        self.current_stage = ProgressStage.COMPLETE
        self.current_progress = 100
        msg = message or f"{self.task_name}生成完成!"
        return await SSEResponse.send_progress(msg, 100, "success")
    
    async def warning(self, message: str) -> str:
        """发送警告消息（保持当前进度）"""
        return await SSEResponse.send_progress(
            f"⚠️ {message}",
            self.current_progress,
            "warning"
        )
    
    async def retry(self, retry_count: int, max_retries: int, reason: str = "准备重试") -> str:
        """发送重试消息"""
        return await SSEResponse.send_progress(
            f"⚠️ {reason}... ({retry_count}/{max_retries})",
            self.current_progress,
            "warning"
        )
    
    async def error(self, error_message: str, code: int = 500) -> str:
        """发送错误消息"""
        return await SSEResponse.send_error(error_message, code)
    
    async def result(self, data: Dict[str, Any]) -> str:
        """发送结果数据"""
        return await SSEResponse.send_result(data)
    
    async def done(self) -> str:
        """发送完成信号"""
        return await SSEResponse.send_done()
    
    async def heartbeat(self) -> str:
        """发送心跳"""
        return await SSEResponse.send_heartbeat()
    
    def reset_generating_progress(self):
        """重置生成阶段进度（用于重试时）"""
        self._last_generating_progress = 20


class SSEResponse:
    """SSE响应构建器"""
    
    @staticmethod
    def format_sse(data: Dict[str, Any], event: Optional[str] = None) -> str:
        """
        格式化SSE消息
        
        Args:
            data: 要发送的数据字典
            event: 事件类型(可选)
            
        Returns:
            格式化后的SSE消息字符串
        """
        try:
            message = ""
            if event:
                message += f"event: {event}\n"
            message += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            return message
        except Exception as e:
            logger.error(f"❌ SSE格式化失败: {type(e).__name__}: {e}")
            logger.error(f"   data类型: {type(data)}")
            logger.error(f"   data内容: {str(data)[:500]}")
            # 返回错误消息而不是崩溃
            error_message = ""
            if event:
                error_message += f"event: {event}\n"
            error_message += f'data: {{"type": "error", "error": "SSE格式化失败: {str(e)}", "code": 500}}\n\n'
            return error_message
    
    @staticmethod
    async def send_progress(
        message: str,
        progress: int,
        status: str = "processing"
    ) -> str:
        """
        发送进度消息
        
        Args:
            message: 进度消息
            progress: 进度百分比(0-100)
            status: 状态(processing/success/error)
        """
        return SSEResponse.format_sse({
            "type": "progress",
            "message": message,
            "progress": progress,
            "status": status
        })
    
    @staticmethod
    async def send_chunk(content: str) -> str:
        """
        发送内容块(用于流式输出AI生成内容)
        
        Args:
            content: 内容块
        """
        return SSEResponse.format_sse({
            "type": "chunk",
            "content": content
        })
    
    @staticmethod
    async def send_result(data: Dict[str, Any]) -> str:
        """
        发送最终结果
        
        Args:
            data: 结果数据
        """
        return SSEResponse.format_sse({
            "type": "result",
            "data": data
        })
    
    @staticmethod
    async def send_event(event: str, data: Dict[str, Any]) -> str:
        """
        发送自定义事件类型的SSE消息
        
        Args:
            event: 事件类型名称
            data: 事件数据
        """
        return SSEResponse.format_sse(data, event=event)
    
    @staticmethod
    async def send_error(error: str, code: int = 500) -> str:
        """
        发送错误消息
        
        Args:
            error: 错误描述
            code: 错误码
        """
        return SSEResponse.format_sse({
            "type": "error",
            "error": error,
            "code": code
        })
    
    @staticmethod
    async def send_done() -> str:
        """发送完成消息"""
        return SSEResponse.format_sse({
            "type": "done"
        })
    
    @staticmethod
    async def send_heartbeat() -> str:
        """发送心跳消息(保持连接活跃)"""
        return ": heartbeat\n\n"


async def create_sse_generator(
    async_gen: AsyncGenerator[str, None],
    show_progress: bool = True
) -> AsyncGenerator[str, None]:
    """
    创建SSE生成器包装器
    
    Args:
        async_gen: 异步生成器
        show_progress: 是否显示进度
        
    Yields:
        格式化的SSE消息
    """
    try:
        if show_progress:
            yield await SSEResponse.send_progress("开始生成...", 0)
        
        # 累积内容用于进度计算
        accumulated_content = ""
        chunk_count = 0
        
        async for chunk in async_gen:
            chunk_count += 1
            accumulated_content += chunk
            
            # 发送内容块
            yield await SSEResponse.send_chunk(chunk)
            
            # 每10个块发送一次心跳
            if chunk_count % 10 == 0:
                yield await SSEResponse.send_heartbeat()
        
        if show_progress:
            yield await SSEResponse.send_progress("生成完成", 100, "success")
        
        # 发送完成信号
        yield await SSEResponse.send_done()
        
    except Exception as e:
        logger.error(f"SSE生成器错误: {str(e)}")
        yield await SSEResponse.send_error(str(e))


def create_sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """
    创建SSE StreamingResponse - 兼容HTTP/2协议
    
    Args:
        generator: SSE消息生成器
        
    Returns:
        StreamingResponse对象
    
    注意：
    - HTTP/2不支持Connection头，已移除
    - 明确指定charset=utf-8以确保编码正确
    - 添加CORS头以支持跨域请求
    """
    async def wrapper():
        """包装生成器以捕获StreamingResponse初始化时的GeneratorExit"""
        try:
            async for chunk in generator:
                yield chunk
        except GeneratorExit:
            # StreamingResponse在初始化时会进行类型检查，导致GeneratorExit
            # 这是正常行为，不需要记录警告
            pass
    
    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream; charset=utf-8",  # 明确指定charset
        headers={
            "Cache-Control": "no-cache, no-transform",  # 禁用缓存和转换
            # 移除 Connection: keep-alive (HTTP/2不兼容)
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
            "Access-Control-Allow-Origin": "*",  # CORS支持
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )