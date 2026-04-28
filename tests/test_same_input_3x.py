"""
测试：同一输入跑 3 次，对比输出差异
判断是系统问题还是 LLM 问题
"""
import sys
import os
import time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests

BASE_URL = "http://localhost:8000"

TEST_INPUTS = [
    "我好烦啊，最近工作压力特别大",
    "怎么才能坚持学习？我总是半途而废",
    "我想赚钱但不想工作，有什么办法吗？",
]


def chat(user_input: str, session_id: str) -> dict:
    """发送对话请求"""
    resp = requests.post(
        f"{BASE_URL}/chat",
        json={"user_input": user_input, "session_id": session_id},
        timeout=120,
    )
    return resp.json()


def main():
    print("="*70)
    print("同一输入跑 3 次，对比输出差异")
    print("="*70)

    # 检查服务器
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
    except:
        print("错误：服务器未启动")
        return

    for i, test_input in enumerate(TEST_INPUTS, 1):
        print(f"\n{'='*70}")
        print(f"测试用例 {i}: '{test_input}'")
        print(f"{'='*70}")

        outputs = []
        for run in range(1, 4):
            session_id = f"test_{i}_run_{run}"
            print(f"\n  第 {run} 次运行...", end=" ", flush=True)
            try:
                start = time.time()
                result = chat(test_input, session_id)
                elapsed = time.time() - start
                output = result.get("output", "")
                print(f"✅ {elapsed:.1f}s")
                outputs.append(output)
            except Exception as e:
                print(f"❌ {e}")
                outputs.append(f"[错误: {e}]")

        # 对比输出
        print(f"\n  --- 输出对比 ---")
        for run, output in enumerate(outputs, 1):
            print(f"\n  [第 {run} 次] ({len(output)}字)")
            print(f"  {output}")

        # 判断差异
        if len(set(outputs)) == 1:
            print(f"\n  ⚠️ 3 次输出完全相同 → 可能是系统模板问题")
        else:
            print(f"\n  ✅ 3 次输出不同 → LLM 在正常生成")

        time.sleep(2)

    print(f"\n{'='*70}")
    print("测试完成！")


if __name__ == "__main__":
    main()
