"""职业生成服务"""
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from app.models.project import Project
from app.models.career import Career
from app.services.ai_service import AIService
from app.logger import get_logger

logger = get_logger(__name__)


class CareerService:
    """职业相关业务逻辑服务"""
    
    @staticmethod
    async def get_career_generation_prompt(
        project: Project,
        main_career_count: int = 2,
        sub_career_count: int = 6
    ) -> str:
        """
        构建职业体系生成的提示词
        
        Args:
            project: 项目对象
            main_career_count: 主职业数量
            sub_career_count: 副职业数量
            
        Returns:
            完整的提示词
        """
        project_context = f"""
项目信息：
- 书名：{project.title}
- 类型：{project.genre or '未设定'}
- 主题：{project.theme or '未设定'}
- 时间背景：{project.world_time_period or '未设定'}
- 地理位置：{project.world_location or '未设定'}
- 氛围基调：{project.world_atmosphere or '未设定'}
- 世界规则：{project.world_rules or '未设定'}
"""
        
        user_requirements = f"""
生成要求：
- 主职业数量：{main_career_count}个
- 副职业数量：{sub_career_count}个
- 主职业必须严格符合世界观规则，体现核心能力体系
- 副职业可以更加自由灵活，包含生产、辅助、特殊类型
"""
        
        prompt = f"""{project_context}

{user_requirements}

请为这个小说项目生成完整的职业体系。返回JSON格式，结构如下：

{{
  "main_careers": [
    {{
      "name": "职业名称",
      "description": "职业描述（100-200字）",
      "category": "职业分类（如：战斗系、法术系、体修系等）",
      "stages": [
        {{"level": 1, "name": "阶段名称", "description": "阶段描述"}},
        {{"level": 2, "name": "阶段名称", "description": "阶段描述"}},
        ...（共10个阶段）
      ],
      "max_stage": 10,
      "requirements": "职业要求（如：需要特定天赋、资质等）",
      "special_abilities": "特殊能力描述",
      "worldview_rules": "世界观规则关联（说明该职业如何融入世界观）",
      "attribute_bonuses": {{"strength": "+10%", "intelligence": "+5%"}}
    }}
  ],
  "sub_careers": [
    {{
      "name": "副职业名称",
      "description": "职业描述",
      "category": "生产系/辅助系/特殊系",
      "stages": [
        {{"level": 1, "name": "阶段名称", "description": "阶段描述"}},
        ...（5-8个阶段）
      ],
      "max_stage": 5,
      "requirements": "职业要求",
      "special_abilities": "特殊能力"
    }}
  ]
}}

重要注意事项：
1. 主职业的阶段设定要详细，体现明确的成长路径，阶段名称要有特色
2. 根据小说类型选择合适的职业：
   - 修仙类：剑修、体修、法修、符修等，阶段如：炼气、筑基、金丹、元婴...
   - 玄幻类：战士、法师、刺客等，阶段如：见习、初级、中级、高级...
   - 都市异能：异能者分类，阶段如：觉醒、初阶、中阶、高阶...
   - 科幻未来：基因战士、机甲师等，阶段如：E级、D级、C级、B级...
3. 副职业要有实用性和趣味性，如：炼丹师、炼器师、阵法师、驯兽师、医师等
4. 所有职业都要符合项目的整体世界观设定
5. 阶段描述要简洁明了，体现该阶段的核心特征
6. **只返回纯JSON对象，不要添加任何解释文字或markdown标记**
"""
        
        return prompt
    
    @staticmethod
    async def parse_and_save_careers(
        career_data: Dict[str, Any],
        project_id: str,
        db: AsyncSession
    ) -> Dict[str, List[str]]:
        """
        解析AI返回的职业数据并保存到数据库
        
        Args:
            career_data: AI返回的职业数据（已解析为dict）
            project_id: 项目ID
            db: 数据库会话
            
        Returns:
            {"main_careers": [...], "sub_careers": [...]} 创建的职业名称列表
        """
        result = {
            "main_careers": [],
            "sub_careers": []
        }
        
        # 保存主职业
        for idx, career_info in enumerate(career_data.get("main_careers", [])):
            try:
                stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                attribute_bonuses = career_info.get("attribute_bonuses")
                attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                
                career = Career(
                    project_id=project_id,
                    name=career_info.get("name", f"未命名主职业{idx+1}"),
                    type="main",
                    description=career_info.get("description"),
                    category=career_info.get("category"),
                    stages=stages_json,
                    max_stage=career_info.get("max_stage", 10),
                    requirements=career_info.get("requirements"),
                    special_abilities=career_info.get("special_abilities"),
                    worldview_rules=career_info.get("worldview_rules"),
                    attribute_bonuses=attribute_bonuses_json,
                    source="ai"
                )
                db.add(career)
                await db.flush()
                result["main_careers"].append(career.name)
                logger.info(f"  ✅ 创建主职业：{career.name}")
            except Exception as e:
                logger.error(f"  ❌ 创建主职业失败：{str(e)}")
                continue
        
        # 保存副职业
        for idx, career_info in enumerate(career_data.get("sub_careers", [])):
            try:
                stages_json = json.dumps(career_info.get("stages", []), ensure_ascii=False)
                attribute_bonuses = career_info.get("attribute_bonuses")
                attribute_bonuses_json = json.dumps(attribute_bonuses, ensure_ascii=False) if attribute_bonuses else None
                
                career = Career(
                    project_id=project_id,
                    name=career_info.get("name", f"未命名副职业{idx+1}"),
                    type="sub",
                    description=career_info.get("description"),
                    category=career_info.get("category"),
                    stages=stages_json,
                    max_stage=career_info.get("max_stage", 5),
                    requirements=career_info.get("requirements"),
                    special_abilities=career_info.get("special_abilities"),
                    worldview_rules=career_info.get("worldview_rules"),
                    attribute_bonuses=attribute_bonuses_json,
                    source="ai"
                )
                db.add(career)
                await db.flush()
                result["sub_careers"].append(career.name)
                logger.info(f"  ✅ 创建副职业：{career.name}")
            except Exception as e:
                logger.error(f"  ❌ 创建副职业失败：{str(e)}")
                continue
        
        await db.commit()
        
        return result
    
    @staticmethod
    async def get_project_careers_summary(project_id: str, db: AsyncSession) -> Dict[str, Any]:
        """
        获取项目职业体系摘要
        
        Args:
            project_id: 项目ID
            db: 数据库会话
            
        Returns:
            职业体系摘要信息
        """
        result = await db.execute(
            select(Career).where(Career.project_id == project_id)
        )
        careers = result.scalars().all()
        
        main_careers = []
        sub_careers = []
        
        for career in careers:
            career_info = {
                "id": career.id,
                "name": career.name,
                "category": career.category,
                "max_stage": career.max_stage
            }
            
            if career.type == "main":
                main_careers.append(career_info)
            else:
                sub_careers.append(career_info)
        
        return {
            "main_careers": main_careers,
            "sub_careers": sub_careers,
            "total_count": len(careers)
        }


# 创建全局服务实例
career_service = CareerService()