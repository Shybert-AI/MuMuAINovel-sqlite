#!/usr/bin/env python3
"""调试AI配置"""
import os
import sys

def debug_ai_config():
    print("=== AI配置调试 ===")
    
    # 检查环境变量
    print("\n1. 环境变量检查:")
    env_vars = ["DATABASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "DEFAULT_AI_PROVIDER", "DEFAULT_MODEL"]
    for var in env_vars:
        value = os.getenv(var)
        if value:
            if "API_KEY" in var and len(value) > 20:
                print(f"  {var}: {value[:10]}...{value[-10:]}")
            else:
                print(f"  {var}: {value}")
        else:
            print(f"  {var}: [未设置]")
    
    # 检查配置
    print("\n2. 应用配置检查:")
    try:
        from app.config import settings
        
        print(f"  OpenAI API Key: {'已设置' if settings.openai_api_key else '未设置'}")
        if settings.openai_api_key:
            print(f"    -> {settings.openai_api_key[:10]}...{settings.openai_api_key[-10:]}")
        
        print(f"  OpenAI Base URL: {settings.openai_base_url}")
        print(f"  默认AI提供商: {settings.default_ai_provider}")
        print(f"  默认模型: {settings.default_model}")
        
        # 检查AI服务初始化
        print("\n3. AI服务初始化检查:")
        from app.services.ai_service import AIService
        
        # 测试默认初始化
        print("  a) 使用默认配置:")
        ai1 = AIService()
        print(f"    API提供商: {ai1.api_provider}")
        print(f"    默认模型: {ai1.default_model}")
        if ai1._openai_provider:
            client = ai1._openai_provider.client
            print(f"    OpenAI客户端Base URL: {client.base_url}")
            print(f"    OpenAI客户端API Key: {client.api_key[:10]}...{client.api_key[-10:]}")
        else:
            print("    OpenAI提供商未初始化")
        
        # 测试明确指定openai提供商
        print("\n  b) 明确指定openai提供商:")
        if settings.openai_api_key:
            ai2 = AIService(api_provider="openai")
            print(f"    API提供商: {ai2.api_provider}")
            if ai2._openai_provider:
                client = ai2._openai_provider.client
                print(f"    OpenAI客户端Base URL: {client.base_url}")
                print(f"    OpenAI客户端API Key: {client.api_key[:10]}...{client.api_key[-10:]}")
            else:
                print("    OpenAI提供商未初始化")
        else:
            print("    跳过(没有OpenAI API密钥)")
            
        return True
        
    except Exception as e:
        print(f"配置检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_env_file():
    print("\n=== 检查.env文件 ===")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_example_path = os.path.join(os.path.dirname(__file__), ".env.example")
    
    if os.path.exists(env_path):
        print(f".env文件存在: {env_path}")
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "OPENAI_BASE_URL=https://api.deepseek.com/v1" in content:
                    print("  ✅ .env中包含DeepSeek配置")
                else:
                    print("  ❌ .env中可能没有DeepSeek配置")
                    
                # 显示相关配置行
                lines = content.split('\n')
                ai_lines = [line for line in lines if any(keyword in line for keyword in ['OPENAI', 'DEFAULT_AI', 'DEFAULT_MODEL'])]
                for line in ai_lines[:10]:  # 只显示前10行
                    print(f"    {line}")
        except Exception as e:
            print(f"读取.env文件失败: {e}")
    else:
        print(f".env文件不存在，使用.env.example: {env_example_path}")
        if os.path.exists(env_example_path):
            with open(env_example_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "OPENAI_BASE_URL=https://api.deepseek.com/v1" in content:
                    print("  ✅ .env.example中包含DeepSeek配置")
                else:
                    print("  ❌ .env.example中没有DeepSeek配置")
    
    return True

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("开始调试AI配置...")
    
    # 设置环境变量模拟（如果需要）
    os.environ.pop('PYTHONUTF8', None)  # 清除之前的设置
    
    success1 = debug_ai_config()
    success2 = check_env_file()
    
    if success1 and success2:
        print("\n[OK] 调试完成")
        print("\n建议:")
        print("1. 确保.env文件存在且包含正确的DeepSeek配置")
        print("2. 重启应用使新配置生效")
        print("3. 检查应用日志确认使用的API端点")
    else:
        print("\n[ERROR] 调试过程中发现问题")
    
    return success1 and success2

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)