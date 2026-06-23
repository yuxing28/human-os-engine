"""
Human-OS Engine - 真实对话测试

通过 API 发送多轮真实对话，测试系统输出质量。
"""
import sys
import os
import time
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests

BASE_URL = "http://localhost:8000"


def chat(user_input: str, session_id: str = "test") -> dict:
    """发送对话请求"""
    resp = requests.post(
        f"{BASE_URL}/chat",
        json={"user_input": user_input, "session_id": session_id},
        timeout=120,
    )
    return resp.json()


def run_scenario(name: str, messages: list[str], session_id: str):
    """测试一个对话场景"""
    print(f"\n{'='*70}")
    print(f"场景: {name}")
    print(f"{'='*70}")
    
    for i, msg in enumerate(messages, 1):
        print(f"\n--- 第 {i} 轮 ---")
        print(f"用户: {msg}")
        
        try:
            start = time.time()
            result = chat(msg, session_id)
            elapsed = time.time() - start
            
            output = result.get("output", "")
            print(f"\n系统 ({elapsed:.1f}s): {output}")
            if any(key in result for key in ("debug", "mode", "priority", "emotion", "input_type")):
                print("  [提示] 接口仍返回了内部字段，请继续检查。")
                
        except requests.exceptions.Timeout:
            print(f"\n系统: [超时 - 120s 无响应]")
        except Exception as e:
            print(f"\n系统: [错误 - {e}]")
        
        time.sleep(1)


def main():
    print("="*70)
    print("Human-OS Engine 真实对话测试")
    print("="*70)
    
    # 检查服务器
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"服务器状态: {resp.status_code}")
    except:
        print("错误：服务器未启动，请先运行 py main.py --api")
        return
    
    # 场景 1：情绪表达 → 寻求建议
    run_scenario(
        "情绪倾诉 + 寻求建议",
        [
            "我好烦啊，最近工作压力特别大",
            "每天加班到很晚，感觉身体都快垮了",
            "你说我该怎么办？要不要辞职？",
        ],
        "scenario_1",
    )
    
    # 场景 2：问题咨询
    run_scenario(
        "学习方法咨询",
        [
            "怎么才能坚持学习？我总是半途而废",
            "我试过很多方法，但都坚持不了几天",
        ],
        "scenario_2",
    )
    
    # 场景 3：场景描述（职场冲突）
    run_scenario(
        "职场冲突",
        [
            "老板当众批评我，我觉得很没面子",
        ],
        "scenario_3",
    )
    
    # 场景 4：攻击性输入
    run_scenario(
        "攻击性输入",
        [
            "你懂什么，你又不是人",
        ],
        "scenario_4",
    )
    
    # 场景 5：逻辑矛盾
    run_scenario(
        "逻辑矛盾",
        [
            "我想赚钱但不想工作，有什么办法吗？",
        ],
        "scenario_5",
    )
    
    # 场景 6：放弃信号
    run_scenario(
        "放弃信号",
        [
            "算了，不聊了，太累了",
        ],
        "scenario_6",
    )
    
    # 场景 7：混合输入（情绪+问题）
    run_scenario(
        "混合输入",
        [
            "我好焦虑，怎么才能提高转化率？",
        ],
        "scenario_7",
    )
    
    # 场景 8：多轮深入对话
    run_scenario(
        "多轮深入对话",
        [
            "我最近总是失眠",
            "工作压力大，而且我觉得自己做不好",
            "我害怕被辞退",
            "有什么办法能快速调整状态吗？",
        ],
        "scenario_8",
    )
    
    print(f"\n{'='*70}")
    print("所有场景测试完成！")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
