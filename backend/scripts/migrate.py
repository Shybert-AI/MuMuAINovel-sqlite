#!/usr/bin/env python3
"""
数据库自动迁移脚本
用于开发和生产环境的数据库迁移管理
"""
import subprocess
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.logger import get_logger

logger = get_logger(__name__)


def run_command(cmd: list, description: str) -> bool:
    """运行命令并返回是否成功"""
    try:
        logger.info(f"🚀 {description}...")
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"✅ {description}成功")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            logger.error(f"❌ {description}失败")
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False
    except Exception as e:
        logger.error(f"❌ {description}异常: {e}")
        return False


def create_migration(message: str = None):
    """创建新的迁移版本"""
    if not message:
        message = input("请输入迁移描述: ").strip()
        if not message:
            message = "auto_migration"
    
    cmd = ["alembic", "revision", "--autogenerate", "-m", message]
    return run_command(cmd, f"生成迁移: {message}")


def upgrade_database(revision: str = "head"):
    """升级数据库到指定版本"""
    cmd = ["alembic", "upgrade", revision]
    return run_command(cmd, f"升级数据库到: {revision}")


def downgrade_database(revision: str = "-1"):
    """降级数据库到指定版本"""
    cmd = ["alembic", "downgrade", revision]
    return run_command(cmd, f"降级数据库到: {revision}")


def show_current():
    """显示当前数据库版本"""
    cmd = ["alembic", "current"]
    return run_command(cmd, "查看当前版本")


def show_history():
    """显示迁移历史"""
    cmd = ["alembic", "history", "--verbose"]
    return run_command(cmd, "查看迁移历史")


def show_heads():
    """显示最新版本"""
    cmd = ["alembic", "heads"]
    return run_command(cmd, "查看最新版本")


def stamp_database(revision: str = "head"):
    """标记数据库版本（不执行迁移）"""
    cmd = ["alembic", "stamp", revision]
    return run_command(cmd, f"标记数据库版本: {revision}")


def auto_migrate():
    """自动迁移：生成并执行迁移"""
    logger.info("=" * 60)
    logger.info("🔄 开始自动迁移流程")
    logger.info("=" * 60)
    
    # 1. 创建迁移
    if not create_migration("auto_migration"):
        logger.error("❌ 自动迁移失败：无法生成迁移")
        return False
    
    # 2. 执行迁移
    if not upgrade_database():
        logger.error("❌ 自动迁移失败：无法执行迁移")
        return False
    
    logger.info("=" * 60)
    logger.info("✅ 自动迁移完成")
    logger.info("=" * 60)
    return True


def init_database():
    """初始化数据库（首次部署）"""
    logger.info("=" * 60)
    logger.info("🔧 初始化数据库")
    logger.info("=" * 60)
    
    # 创建初始迁移
    if not create_migration("initial_migration"):
        logger.warning("⚠️ 无法创建初始迁移，可能已存在")
    
    # 执行迁移
    if not upgrade_database():
        logger.error("❌ 初始化失败")
        return False
    
    logger.info("=" * 60)
    logger.info("✅ 数据库初始化完成")
    logger.info("=" * 60)
    return True


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python migrate.py create [message]    - 创建新迁移")
        print("  python migrate.py upgrade [revision]  - 升级数据库（默认: head）")
        print("  python migrate.py downgrade [revision] - 降级数据库（默认: -1）")
        print("  python migrate.py current            - 显示当前版本")
        print("  python migrate.py history            - 显示迁移历史")
        print("  python migrate.py heads              - 显示最新版本")
        print("  python migrate.py stamp [revision]   - 标记版本（默认: head）")
        print("  python migrate.py auto               - 自动迁移（生成+执行）")
        print("  python migrate.py init               - 初始化数据库")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create":
        message = sys.argv[2] if len(sys.argv) > 2 else None
        success = create_migration(message)
    elif command == "upgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        success = upgrade_database(revision)
    elif command == "downgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
        success = downgrade_database(revision)
    elif command == "current":
        success = show_current()
    elif command == "history":
        success = show_history()
    elif command == "heads":
        success = show_heads()
    elif command == "stamp":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        success = stamp_database(revision)
    elif command == "auto":
        success = auto_migrate()
    elif command == "init":
        success = init_database()
    else:
        logger.error(f"❌ 未知命令: {command}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()