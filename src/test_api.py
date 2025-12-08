#!/usr/bin/env python3
"""测试各个 API 是否正常工作"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpt_request import (
    request_gpt51_token,
    request_claude_token,
)

def test_gpt51():
    print("=" * 50)
    print("测试 gpt-51 API...")
    print("=" * 50)
    try:
        response, usage = request_gpt51_token("你好，请简单回复'测试成功'", max_completion_tokens=100)
        if response:
            print(f"✅ gpt-51 API 成功!")
            print(f"   Response: {response.choices[0].message.content[:100]}")
            print(f"   Usage: {usage}")
        else:
            print(f"❌ gpt-51 API 返回 None")
    except Exception as e:
        print(f"❌ gpt-51 API 失败: {e}")

def test_claude():
    print("=" * 50)
    print("测试 claude API...")
    print("=" * 50)
    try:
        response, usage = request_claude_token("你好，请简单回复'测试成功'", max_tokens=100)
        if response:
            print(f"✅ claude API 成功!")
            # Claude 响应格式不同
            content = response.content[0].text if hasattr(response, 'content') else str(response)
            print(f"   Response: {content[:100]}")
            print(f"   Usage: {usage}")
        else:
            print(f"❌ claude API 返回 None")
    except Exception as e:
        print(f"❌ claude API 失败: {e}")

if __name__ == "__main__":
    print("\n🧪 开始 API 测试...\n")
    
    # 测试各个 API
    test_claude()
    print()
    test_gpt51()
    
    print("\n🧪 API 测试完成!\n")
