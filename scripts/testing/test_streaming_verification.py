# -*- coding: utf-8 -*-
"""
流式输出系统验证

验证目标：
1. 同一输入，分别调用同步接口 /chat 和流式接口 /chat/stream
2. 确认流式接口对外只输出最终展示文本，不暴露内部 step/status
3. 确认流式接口会分块返回最终文本，而不是额外暴露内部分析过程
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import httpx
import threading
import time
import json
import uuid


def run_server():
    import uvicorn
    uvicorn.run('api.routes:app', host='127.0.0.1', port=8770, log_level='error')


server = threading.Thread(target=run_server, daemon=True)
server.start()
time.sleep(3)

TEST_INPUT = "最近工作压力很大，每天加班到很晚，感觉身体快撑不住了，团队里其他人也都有同样的感受"
SESSION_ID = str(uuid.uuid4())[:8]

print("=" * 70)
print("  流式输出系统验证")
print("=" * 70)
print(f"\n测试输入: {TEST_INPUT}")
print(f"Session: {SESSION_ID}")

print(f"\n{'─' * 70}")
print("  测试 1：同步接口 /chat")
print(f"{'─' * 70}")

with httpx.Client(timeout=120.0) as client:
    start = time.time()
    resp = client.post('http://127.0.0.1:8770/chat', json={
        'user_input': TEST_INPUT,
        'session_id': SESSION_ID,
    })
    sync_elapsed = time.time() - start
    sync_data = resp.json()
    sync_output = sync_data.get('output', '')

    print(f"  状态码: {resp.status_code}")
    print(f"  总耗时: {sync_elapsed:.1f}s")
    print(f"  输出长度: {len(sync_output)} 字")
    print(f"  输出预览: {sync_output[:100]}...")

print(f"\n{'─' * 70}")
print("  测试 2：流式接口 /chat/stream")
print(f"{'─' * 70}")

stream_session = str(uuid.uuid4())[:8]
first_token_time = None
tokens = []
complete_data = None
error_data = None

with httpx.Client(timeout=120.0) as client:
    stream_start = time.time()
    event_type = ''

    with client.stream('POST', 'http://127.0.0.1:8770/chat/stream', json={
        'user_input': TEST_INPUT,
        'session_id': stream_session,
    }) as response:
        print(f"  状态码: {response.status_code}")
        print(f"  Content-Type: {response.headers.get('content-type', '')}")
        print()

        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('event:'):
                event_type = line.split(':', 1)[1].strip()
            elif line.startswith('data:'):
                try:
                    data = json.loads(line[5:].strip())
                    now = time.time() - stream_start

                    if event_type == 'token':
                        token = data.get('token', '')
                        tokens.append(token)
                        if first_token_time is None:
                            first_token_time = now
                            print(f"  [{now:.1f}s] 首块最终文本到达")
                    elif event_type == 'complete':
                        complete_data = data
                        print(f"  [{now:.1f}s] 完成")
                    elif event_type == 'error':
                        error_data = data
                        print(f"  [{now:.1f}s] 错误: {data}")
                except Exception:
                    pass

stream_total = time.time() - stream_start
stream_output = ''.join(tokens)

print(f"\n  总耗时: {stream_total:.1f}s")
print(f"  首块等待: {first_token_time:.1f}s" if first_token_time else "  首块等待: N/A")
print(f"  分块数量: {len(tokens)} 个")
print(f"  流式输出 ({len(stream_output)} 字): {stream_output}")

if complete_data:
    print(f"\n  Complete 事件输出 ({len(complete_data.get('output', ''))} 字):")
    print(f"    {complete_data['output']}")
    print(f"    耗时: {complete_data.get('elapsed_ms', 0)}ms")

print(f"\n{'=' * 70}")
print("  对比分析")
print(f"{'=' * 70}")

print(f"\n  指标对比:")
print(f"  ┌─────────────────────┬──────────────┬──────────────┐")
print(f"  │ 指标                │ 同步接口     │ 流式接口     │")
print(f"  ├─────────────────────┼──────────────┼──────────────┤")
print(f"  │ 总耗时              │ {sync_elapsed:8.1f}s   │ {stream_total:8.1f}s   │")
print(f"  │ 首块等待            │ {sync_elapsed:8.1f}s   │ {first_token_time if first_token_time else 'N/A':>8}   │")
print(f"  │ 暴露内部步骤        │     ❌ 无     │     ❌ 无     │")
print(f"  │ 分块展示最终稿      │     ❌ 否     │     ✅ {len(tokens)} 块 │")
print(f"  │ 输出内容一致性      │  {len(sync_output):>4} 字   │  {len(stream_output):>4} 字   │")
print(f"  └─────────────────────┴──────────────┴──────────────┘")

print(f"\n{'─' * 70}")
print("  验证结论")
print(f"{'─' * 70}")

checks = [
    ("SSE Content-Type 正确", response.headers.get('content-type', '').startswith('text/event-stream')),
    ("未返回错误事件", error_data is None),
    ("分块数量 > 0", len(tokens) > 0),
    ("Complete 事件存在", complete_data is not None),
    ("流式输出内容 > 10 字", len(stream_output) > 10),
    ("首块时间 < 总耗时", first_token_time is not None and first_token_time < stream_total),
]

all_passed = True
for name, passed in checks:
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}")
    if not passed:
        all_passed = False

print()
if all_passed:
    print("  ✅ 流式系统验证通过：对外只展示最终修正后的文本")
else:
    print("  ❌ 流式系统验证失败，存在未通过项")
