"""OpenAI Provider"""
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.logger import get_logger
from app.services.ai_clients.openai_client import OpenAIClient
from .base_provider import BaseAIProvider

logger = get_logger(__name__)


class OpenAIProvider(BaseAIProvider):
    """OpenAI 提供商"""

    def __init__(self, client: OpenAIClient):
        self.client = client

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 如果有工具，使用真正的流式工具调用
        if tools:
            logger.debug(f"🔧 OpenAIProvider: 有 {len(tools)} 个工具，使用流式处理")
            actual_tool_choice = tool_choice if tool_choice else "auto"
            
            tool_calls_buffer = []
            
            async for chunk in self.client.chat_completion_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=actual_tool_choice,
            ):
                # 检查是否有工具调用
                if chunk.get("tool_calls"):
                    tool_calls_buffer.extend(chunk["tool_calls"])
                    logger.debug(f"🔧 收到工具调用: {len(chunk['tool_calls'])} 个")
                
                # 检查是否结束
                if chunk.get("done"):
                    if tool_calls_buffer:
                        logger.info(f"🔧 流式结束，处理 {len(tool_calls_buffer)} 个工具调用")
                        from app.mcp import mcp_client
                        actual_user_id = user_id or ""
                        tool_results = await mcp_client.batch_call_tools(
                            user_id=actual_user_id,
                            tool_calls=tool_calls_buffer
                        )
                        # 将工具结果注入到上下文中
                        tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                        
                        # 构建最终提示词，要求AI基于工具结果回答
                        final_prompt = f"{prompt}\n\n{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"
                        final_messages = messages.copy()
                        final_messages.append({"role": "user", "content": final_prompt})
                        
                        # 递归调用生成最终结果
                        async for final_chunk in self._generate_with_tools(
                            final_messages, model, temperature, max_tokens, tools, user_id
                        ):
                            yield final_chunk
                    break
                
                # 输出文本内容
                if chunk.get("content"):
                    yield chunk["content"]
            return
        
        # 无工具时普通流式生成
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            # 确保只 yield 字符串内容，避免 yield 字典导致类型错误
            if isinstance(chunk, dict):
                if chunk.get("content"):
                    yield chunk["content"]
            else:
                yield chunk

    async def _generate_with_tools(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """辅助方法：带工具的流式生成（无tool_choice，AI自由决定）"""
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto",
        ):
            if chunk.get("tool_calls"):
                from app.mcp import mcp_client
                actual_user_id = user_id or ""
                tool_results = await mcp_client.batch_call_tools(
                    user_id=actual_user_id,
                    tool_calls=chunk["tool_calls"]
                )
                tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                
                # 再次调用获取最终回答
                messages.append({"role": "user", "content": f"{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"})
                
                async for final_chunk in self._generate_with_tools(
                    messages, model, temperature, max_tokens, tools, user_id
                ):
                    yield final_chunk
                break
            
            if chunk.get("done"):
                break
            
            if chunk.get("content"):
                yield chunk["content"]