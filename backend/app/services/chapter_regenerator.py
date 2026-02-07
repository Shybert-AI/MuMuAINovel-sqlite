"""章节重新生成服务"""
from typing import Dict, Any, AsyncGenerator, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service, PromptService
from app.models.chapter import Chapter
from app.models.memory import PlotAnalysis
from app.schemas.regeneration import ChapterRegenerateRequest, PreserveElementsConfig
from app.logger import get_logger
import difflib

logger = get_logger(__name__)


class ChapterRegenerator:
    """章节重新生成服务"""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
        logger.info("✅ ChapterRegenerator初始化成功")
    
    async def regenerate_with_feedback(
        self,
        chapter: Chapter,
        analysis: Optional[PlotAnalysis],
        regenerate_request: ChapterRegenerateRequest,
        project_context: Dict[str, Any],
        style_content: str = "",
        user_id: str = None,
        db: AsyncSession = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        根据反馈重新生成章节（流式）
        
        Args:
            chapter: 原始章节对象
            analysis: 分析结果（可选）
            regenerate_request: 重新生成请求参数
            project_context: 项目上下文（项目信息、角色、大纲等）
            style_content: 写作风格
            user_id: 用户ID（用于获取自定义提示词）
            db: 数据库会话（用于查询自定义提示词）
        
        Yields:
            包含类型和数据的字典: {'type': 'progress'/'chunk', 'data': ...}
        """
        try:
            logger.info(f"🔄 开始重新生成章节: 第{chapter.chapter_number}章")
            
            # 1. 构建修改指令
            yield {'type': 'progress', 'progress': 5, 'message': '正在构建修改指令...'}
            modification_instructions = self._build_modification_instructions(
                analysis=analysis,
                regenerate_request=regenerate_request
            )
            
            logger.info(f"📝 修改指令构建完成，长度: {len(modification_instructions)}字符")
            
            # 2. 构建完整提示词
            yield {'type': 'progress', 'progress': 10, 'message': '正在构建生成提示词...'}
            full_prompt = await self._build_regeneration_prompt(
                chapter=chapter,
                modification_instructions=modification_instructions,
                project_context=project_context,
                regenerate_request=regenerate_request,
                style_content=style_content,
                user_id=user_id,
                db=db
            )

            logger.info(f"🎯 提示词构建完成，开始AI生成")
            yield {'type': 'progress', 'progress': 15, 'message': '开始AI生成内容...'}
            
            # 3. 构建系统提示词（注入写作风格）
            system_prompt_with_style = None
            if style_content:
                system_prompt_with_style = f"""【🎨 写作风格要求 - 最高优先级】

{style_content}

⚠️ 请严格遵循上述写作风格要求进行重写，这是最重要的指令！
确保在整个章节重写过程中始终保持风格的一致性。"""
                logger.info(f"✅ 已将写作风格注入系统提示词（{len(style_content)}字符）")
            
            # 4. 流式生成新内容，同时跟踪进度
            target_word_count = regenerate_request.target_word_count
            accumulated_length = 0
            
            async for chunk in self.ai_service.generate_text_stream(
                prompt=full_prompt,
                system_prompt=system_prompt_with_style,
                temperature=0.7
            ):
                # 发送内容块
                yield {'type': 'chunk', 'content': chunk}
                
                # 更新累积字数并计算进度（15%-95%）
                accumulated_length += len(chunk)
                # 进度从15%开始，到95%结束，为后处理预留5%
                generation_progress = min(15 + (accumulated_length / target_word_count) * 80, 95)
                yield {'type': 'progress', 'progress': int(generation_progress), 'word_count': accumulated_length}
            
            logger.info(f"✅ 章节重新生成完成，共生成 {accumulated_length} 字")
            yield {'type': 'progress', 'progress': 100, 'message': '生成完成'}
            
        except Exception as e:
            logger.error(f"❌ 重新生成失败: {str(e)}", exc_info=True)
            raise
    
    def _build_modification_instructions(
        self,
        analysis: Optional[PlotAnalysis],
        regenerate_request: ChapterRegenerateRequest
    ) -> str:
        """构建修改指令"""
        
        instructions = []
        
        # 标题
        instructions.append("# 章节修改指令\n")
        
        # 1. 来自分析的建议
        if (analysis and 
            regenerate_request.selected_suggestion_indices and 
            analysis.suggestions):
            
            instructions.append("## 📋 需要改进的问题（来自AI分析）：\n")
            for idx in regenerate_request.selected_suggestion_indices:
                if 0 <= idx < len(analysis.suggestions):
                    suggestion = analysis.suggestions[idx]
                    instructions.append(f"{idx + 1}. {suggestion}")
            instructions.append("")
        
        # 2. 用户自定义指令
        if regenerate_request.custom_instructions:
            instructions.append("## ✍️ 用户自定义修改要求：\n")
            instructions.append(regenerate_request.custom_instructions)
            instructions.append("")
        
        # 3. 重点优化方向
        if regenerate_request.focus_areas:
            instructions.append("## 🎯 重点优化方向：\n")
            focus_map = {
                "pacing": "节奏把控 - 调整叙事速度，避免拖沓或过快",
                "emotion": "情感渲染 - 深化人物情感表达，增强感染力",
                "description": "场景描写 - 丰富环境细节，增强画面感",
                "dialogue": "对话质量 - 让对话更自然真实，推动剧情",
                "conflict": "冲突强度 - 强化矛盾冲突，提升戏剧张力"
            }
            
            for area in regenerate_request.focus_areas:
                if area in focus_map:
                    instructions.append(f"- {focus_map[area]}")
            instructions.append("")
        
        # 4. 保留要求
        if regenerate_request.preserve_elements:
            preserve = regenerate_request.preserve_elements
            instructions.append("## 🔒 必须保留的元素：\n")
            
            if preserve.preserve_structure:
                instructions.append("- 保持原章节的整体结构和情节框架")
            
            if preserve.preserve_dialogues:
                instructions.append("- 必须保留以下关键对话：")
                for dialogue in preserve.preserve_dialogues:
                    instructions.append(f"  * {dialogue}")
            
            if preserve.preserve_plot_points:
                instructions.append("- 必须保留以下关键情节点：")
                for plot in preserve.preserve_plot_points:
                    instructions.append(f"  * {plot}")
            
            if preserve.preserve_character_traits:
                instructions.append("- 保持所有角色的性格特征和行为模式一致")
            
            instructions.append("")
        
        return "\n".join(instructions)
    
    async def _build_regeneration_prompt(
        self,
        chapter: Chapter,
        modification_instructions: str,
        project_context: Dict[str, Any],
        regenerate_request: ChapterRegenerateRequest,
        style_content: str = "",
        user_id: str = None,
        db: AsyncSession = None
    ) -> str:
        """构建完整的重新生成提示词"""
        # 使用PromptService的get_chapter_regeneration_prompt方法
        # 该方法会处理自定义模板加载和完整提示词构建
        return await PromptService.get_chapter_regeneration_prompt(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            word_count=chapter.word_count,
            content=chapter.content,
            modification_instructions=modification_instructions,
            project_context=project_context,
            style_content=style_content,
            target_word_count=regenerate_request.target_word_count,
            user_id=user_id,
            db=db
        )
    
    def calculate_content_diff(
        self,
        original_content: str,
        new_content: str
    ) -> Dict[str, Any]:
        """
        计算两个版本的差异
        
        Returns:
            差异统计信息
        """
        # 基本统计
        diff_stats = {
            'original_length': len(original_content),
            'new_length': len(new_content),
            'length_change': len(new_content) - len(original_content),
            'length_change_percent': round((len(new_content) - len(original_content)) / len(original_content) * 100, 2) if len(original_content) > 0 else 0
        }
        
        # 计算相似度
        similarity = difflib.SequenceMatcher(None, original_content, new_content).ratio()
        diff_stats['similarity'] = round(similarity * 100, 2)
        diff_stats['difference'] = round((1 - similarity) * 100, 2)
        
        # 段落统计
        original_paragraphs = [p for p in original_content.split('\n\n') if p.strip()]
        new_paragraphs = [p for p in new_content.split('\n\n') if p.strip()]
        diff_stats['original_paragraph_count'] = len(original_paragraphs)
        diff_stats['new_paragraph_count'] = len(new_paragraphs)
        
        return diff_stats


# 全局实例
_regenerator_instance = None

def get_chapter_regenerator(ai_service: AIService) -> ChapterRegenerator:
    """获取章节重新生成器实例"""
    global _regenerator_instance
    if _regenerator_instance is None:
        _regenerator_instance = ChapterRegenerator(ai_service)
    return _regenerator_instance