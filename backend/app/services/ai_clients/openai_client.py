"""OpenAI 客户端 - 使用官方 OpenAI Python SDK"""
import json
from typing import Any, AsyncGenerator, Dict, Optional, Union

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall

from app.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)


class OpenAIClient(BaseAIClient):
    """OpenAI API 客户端 - 使用官方 OpenAI Python SDK"""

    def __init__(self, api_key: str, base_url: str, config=None):
        """初始化 OpenAI 客户端"""
        super().__init__(api_key, base_url, config)
        # 创建 OpenAI 客户端实例
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/" if not base_url.endswith("/") else base_url
        )
        logger.info(f"✅ 创建 OpenAI SDK 客户端: base_url={base_url}")

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头 - 使用 OpenAI SDK 不需要手动构建"""
        return {}

    def _build_payload(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """构建请求载荷 - 用于日志记录"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        
        # 记录流式请求的payload（调试用）
        if stream:
            logger.info(f"📤 OpenAI 流式请求 payload (model={model}, stream={stream}): {json.dumps(payload, ensure_ascii=False)[:500]}")
        
        return payload

    async def chat_completion(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        """聊天补全 - 使用 OpenAI SDK"""
        # DeepSeek 模型限制 max_tokens 为 8192
        if "deepseek" in model.lower() and max_tokens > 8192:
            logger.warning(f"⚠️  DeepSeek 模型 max_tokens 限制为 8192，将 {max_tokens} 调整为 8192")
            max_tokens = 8192
        
        # 记录请求
        logger.info(f"📤 OpenAI 请求: model={model}, messages={len(messages)}")
        
        try:
            # 调用 OpenAI SDK
            response: ChatCompletion = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                stream=False
            )
            
            # 记录响应
            logger.debug(f"📥 OpenAI 原始响应: {response}")
            
            choice = response.choices[0]
            message: ChatCompletionMessage = choice.message
            
            # 提取工具调用信息
            tool_calls = None
            if message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            
            return {
                "content": message.content or "",
                "tool_calls": tool_calls,
                "finish_reason": choice.finish_reason,
            }
            
        except Exception as e:
            logger.error(f"❌ OpenAI 请求失败: {type(e).__name__}: {str(e)}")
            raise

    async def chat_completion_stream(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式生成，支持工具调用 - 使用 OpenAI SDK
        
        Yields:
            Dict with keys:
            - content: str - 文本内容块
            - tool_calls: list - 工具调用列表（如果有）
            - done: bool - 是否结束
        """
        # DeepSeek 模型限制 max_tokens 为 8192
        if "deepseek" in model.lower() and max_tokens > 8192:
            logger.warning(f"⚠️  DeepSeek 模型 max_tokens 限制为 8192，将 {max_tokens} 调整为 8192")
            max_tokens = 8192
        
        logger.info(f"📤 OpenAI 流式请求: model={model}, base_url={self.base_url}, tools={len(tools) if tools else 0}")
        
        try:
            # 调用 OpenAI SDK 流式 API
            stream: AsyncStream[ChatCompletionChunk] = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                stream=True
            )
            
            tool_calls_buffer = {}  # 收集工具调用块
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                # 检查工具调用
                tc_list = delta.tool_calls
                if tc_list:
                    for tc in tc_list:
                        index = tc.index
                        if index not in tool_calls_buffer:
                            tool_calls_buffer[index] = {
                                "id": tc.id or "",
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name if tc.function else "",
                                    "arguments": tc.function.arguments if tc.function else ""
                                }
                            }
                        else:
                            existing = tool_calls_buffer[index]
                            # 合并 function.arguments
                            if tc.function and tc.function.arguments:
                                existing["function"]["arguments"] = (
                                    existing["function"].get("arguments", "") +
                                    tc.function.arguments
                                )
                
                # 检查文本内容
                content = delta.content
                if content:
                    yield {"content": content}
            
            # 流结束，检查是否有工具调用需要处理
            if tool_calls_buffer:
                yield {"tool_calls": list(tool_calls_buffer.values()), "done": True}
            yield {"done": True}
            
        except Exception as e:
            logger.error(f"❌ OpenAI 流式请求失败: {type(e).__name__}: {str(e)}")
            raise