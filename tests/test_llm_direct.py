"""
Test LLM call directly
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ["NVIDIA_API_KEY"] = ""

from llm.nvidia_client import invoke_deep, invoke_standard, invoke_fast

print("=== Testing invoke_deep (话术生成) ===")
try:
    result = invoke_deep("你好，用中文回答", "你是一个助手")
    print(f"Success: {result[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Testing invoke_standard (知识路由) ===")
try:
    result = invoke_standard("简要说明复利效应", "你是一个助手")
    print(f"Success: {result[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Testing invoke_fast (元控制器) ===")
try:
    result = invoke_fast("判断类型：我好烦", "你是分类器")
    print(f"Success: {result[:200]}")
except Exception as e:
    print(f"Error: {e}")
