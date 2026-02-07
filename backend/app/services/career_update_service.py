"""职业更新服务 - 根据章节分析自动更新角色职业信息"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.character import Character
from app.models.career import Career, CharacterCareer
from app.logger import get_logger

logger = get_logger(__name__)


class CareerUpdateService:
    """职业更新服务 - 根据章节分析结果自动更新角色职业"""
    
    @staticmethod
    async def update_careers_from_analysis(
        db: AsyncSession,
        project_id: str,
        character_states: List[Dict[str, Any]],
        chapter_id: str,
        chapter_number: int
    ) -> Dict[str, Any]:
        """
        根据章节分析结果更新角色职业
        
        Args:
            db: 数据库会话
            project_id: 项目ID
            character_states: 角色状态变化列表（来自PlotAnalysis）
            chapter_id: 章节ID
            chapter_number: 章节编号
            
        Returns:
            更新结果字典，包含更新数量和变更日志
        """
        if not character_states:
            logger.info("📋 角色状态列表为空，跳过职业更新")
            return {"updated_count": 0, "changes": []}
        
        updated_count = 0
        changes_log = []
        
        logger.info(f"🔍 开始分析第{chapter_number}章的角色职业变化...")
        
        for char_state in character_states:
            char_name = char_state.get('character_name')
            career_changes = char_state.get('career_changes', {})
            
            # 如果没有职业变化信息，跳过
            if not career_changes or not isinstance(career_changes, dict):
                continue
            
            # 检查是否有实质性的职业变化
            main_stage_change = career_changes.get('main_career_stage_change', 0)
            sub_career_changes = career_changes.get('sub_career_changes', [])
            new_careers = career_changes.get('new_careers', [])
            
            if main_stage_change == 0 and not sub_career_changes and not new_careers:
                continue
            
            logger.info(f"  👤 检测到角色 [{char_name}] 有职业变化")
            
            # 1. 查询角色
            char_result = await db.execute(
                select(Character).where(
                    Character.name == char_name,
                    Character.project_id == project_id
                )
            )
            character = char_result.scalar_one_or_none()
            
            if not character:
                logger.warning(f"  ⚠️ 角色不存在: {char_name}，跳过")
                continue
            
            # 2. 更新主职业阶段
            if main_stage_change != 0 and character.main_career_id:
                success = await CareerUpdateService._update_main_career_stage(
                    db=db,
                    character=character,
                    stage_change=main_stage_change,
                    chapter_number=chapter_number,
                    career_changes=career_changes,
                    changes_log=changes_log
                )
                if success:
                    updated_count += 1
            
            # 3. 更新副职业（如果有）
            if sub_career_changes and isinstance(sub_career_changes, list):
                for sub_change in sub_career_changes:
                    success = await CareerUpdateService._update_sub_career_stage(
                        db=db,
                        character=character,
                        project_id=project_id,
                        sub_change=sub_change,
                        chapter_number=chapter_number,
                        changes_log=changes_log
                    )
                    if success:
                        updated_count += 1
            
            # 4. 添加新职业（如果有）
            if new_careers and isinstance(new_careers, list):
                for new_career_name in new_careers:
                    success = await CareerUpdateService._add_new_career(
                        db=db,
                        character=character,
                        project_id=project_id,
                        career_name=new_career_name,
                        chapter_number=chapter_number,
                        changes_log=changes_log
                    )
                    if success:
                        updated_count += 1
        
        # 提交所有更改
        if updated_count > 0:
            await db.commit()
            logger.info(f"✅ 职业更新完成: 共更新了 {updated_count} 个角色的职业信息")
        else:
            logger.info("📋 本章没有角色职业变化")
        
        return {
            "updated_count": updated_count,
            "changes": changes_log
        }
    
    @staticmethod
    async def _update_main_career_stage(
        db: AsyncSession,
        character: Character,
        stage_change: int,
        chapter_number: int,
        career_changes: Dict[str, Any],
        changes_log: List[Dict[str, Any]]
    ) -> bool:
        """更新主职业阶段"""
        try:
            # 查询主职业关联
            char_career_result = await db.execute(
                select(CharacterCareer).where(
                    CharacterCareer.character_id == character.id,
                    CharacterCareer.career_type == 'main'
                )
            )
            char_career = char_career_result.scalar_one_or_none()
            
            if not char_career:
                logger.warning(f"  ⚠️ {character.name} 没有主职业关联记录")
                return False
            
            # 查询职业信息
            career_result = await db.execute(
                select(Career).where(Career.id == char_career.career_id)
            )
            career = career_result.scalar_one_or_none()
            
            if not career:
                logger.warning(f"  ⚠️ 职业ID {char_career.career_id} 不存在")
                return False
            
            # 计算新阶段（不超过最大阶段，不低于1）
            old_stage = char_career.current_stage
            new_stage = min(max(1, old_stage + stage_change), career.max_stage)
            
            # 如果没有实际变化，跳过
            if new_stage == old_stage:
                logger.info(f"  📊 {character.name} 的 {career.name} 已达到边界，无法变更")
                return False
            
            # 更新CharacterCareer表
            char_career.current_stage = new_stage
            
            # 同步更新Character表的冗余字段
            character.main_career_stage = new_stage
            
            # 记录变更日志
            change_desc = f"{'晋升' if stage_change > 0 else '降级'}"
            breakthrough_desc = career_changes.get('career_breakthrough', '')
            
            changes_log.append({
                'character': character.name,
                'career': career.name,
                'career_type': 'main',
                'old_stage': old_stage,
                'new_stage': new_stage,
                'change': stage_change,
                'chapter': chapter_number,
                'description': breakthrough_desc
            })
            
            logger.info(
                f"  ✨ {character.name} 的主职业 [{career.name}] "
                f"{old_stage}阶 → {new_stage}阶 ({change_desc})"
            )
            if breakthrough_desc:
                logger.info(f"     突破描述: {breakthrough_desc[:50]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"  ❌ 更新主职业失败: {str(e)}")
            return False
    
    @staticmethod
    async def _update_sub_career_stage(
        db: AsyncSession,
        character: Character,
        project_id: str,
        sub_change: Dict[str, Any],
        chapter_number: int,
        changes_log: List[Dict[str, Any]]
    ) -> bool:
        """更新副职业阶段"""
        try:
            career_name = sub_change.get('career_name')
            stage_change = sub_change.get('stage_change', 0)
            
            if not career_name or stage_change == 0:
                return False
            
            # 1. 查询职业（通过名称）
            career_result = await db.execute(
                select(Career).where(
                    Career.name == career_name,
                    Career.project_id == project_id,
                    Career.type == 'sub'
                )
            )
            career = career_result.scalar_one_or_none()
            
            if not career:
                logger.warning(f"  ⚠️ 副职业 [{career_name}] 不存在")
                return False
            
            # 2. 查询角色-职业关联
            char_career_result = await db.execute(
                select(CharacterCareer).where(
                    CharacterCareer.character_id == character.id,
                    CharacterCareer.career_id == career.id,
                    CharacterCareer.career_type == 'sub'
                )
            )
            char_career = char_career_result.scalar_one_or_none()
            
            if not char_career:
                logger.warning(f"  ⚠️ {character.name} 没有 [{career_name}] 副职业")
                return False
            
            # 3. 计算新阶段
            old_stage = char_career.current_stage
            new_stage = min(max(1, old_stage + stage_change), career.max_stage)
            
            if new_stage == old_stage:
                return False
            
            # 4. 更新阶段
            char_career.current_stage = new_stage
            
            # 5. 同步更新Character表的sub_careers JSON字段
            import json
            sub_careers = json.loads(character.sub_careers) if character.sub_careers else []
            for sc in sub_careers:
                if sc.get('career_id') == career.id:
                    sc['stage'] = new_stage
                    break
            character.sub_careers = json.dumps(sub_careers, ensure_ascii=False)
            
            # 6. 记录变更
            changes_log.append({
                'character': character.name,
                'career': career.name,
                'career_type': 'sub',
                'old_stage': old_stage,
                'new_stage': new_stage,
                'change': stage_change,
                'chapter': chapter_number
            })
            
            logger.info(
                f"  ✨ {character.name} 的副职业 [{career.name}] "
                f"{old_stage}阶 → {new_stage}阶"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"  ❌ 更新副职业失败: {str(e)}")
            return False
    
    @staticmethod
    async def _add_new_career(
        db: AsyncSession,
        character: Character,
        project_id: str,
        career_name: str,
        chapter_number: int,
        changes_log: List[Dict[str, Any]]
    ) -> bool:
        """为角色添加新职业"""
        try:
            # 1. 查询职业
            career_result = await db.execute(
                select(Career).where(
                    Career.name == career_name,
                    Career.project_id == project_id
                )
            )
            career = career_result.scalar_one_or_none()
            
            if not career:
                logger.warning(f"  ⚠️ 职业 [{career_name}] 不存在，无法添加")
                return False
            
            # 2. 检查是否已存在
            existing_result = await db.execute(
                select(CharacterCareer).where(
                    CharacterCareer.character_id == character.id,
                    CharacterCareer.career_id == career.id
                )
            )
            if existing_result.scalar_one_or_none():
                logger.info(f"  📋 {character.name} 已拥有 [{career_name}]，跳过")
                return False
            
            # 3. 根据职业类型添加
            if career.type == 'main':
                # 检查是否已有主职业
                if character.main_career_id:
                    logger.warning(f"  ⚠️ {character.name} 已有主职业，无法添加新主职业")
                    return False
                
                # 添加主职业
                import uuid
                new_char_career = CharacterCareer(
                    id=str(uuid.uuid4()),
                    character_id=character.id,
                    career_id=career.id,
                    career_type='main',
                    current_stage=1
                )
                db.add(new_char_career)
                
                # 更新Character表
                character.main_career_id = career.id
                character.main_career_stage = 1
                
                logger.info(f"  ✨ {character.name} 获得新主职业 [{career_name}]")
                
            else:  # sub职业
                # 检查副职业数量（最多2个）
                sub_count_result = await db.execute(
                    select(CharacterCareer).where(
                        CharacterCareer.character_id == character.id,
                        CharacterCareer.career_type == 'sub'
                    )
                )
                if len(sub_count_result.scalars().all()) >= 2:
                    logger.warning(f"  ⚠️ {character.name} 的副职业已达上限(2个)")
                    return False
                
                # 添加副职业
                import uuid
                new_char_career = CharacterCareer(
                    id=str(uuid.uuid4()),
                    character_id=character.id,
                    career_id=career.id,
                    career_type='sub',
                    current_stage=1
                )
                db.add(new_char_career)
                
                # 更新Character表的sub_careers JSON
                import json
                sub_careers = json.loads(character.sub_careers) if character.sub_careers else []
                sub_careers.append({
                    'career_id': career.id,
                    'stage': 1
                })
                character.sub_careers = json.dumps(sub_careers, ensure_ascii=False)
                
                logger.info(f"  ✨ {character.name} 获得新副职业 [{career_name}]")
            
            # 记录变更
            changes_log.append({
                'character': character.name,
                'career': career.name,
                'career_type': career.type,
                'action': 'new',
                'chapter': chapter_number
            })
            
            return True
            
        except Exception as e:
            logger.error(f"  ❌ 添加新职业失败: {str(e)}")
            return False