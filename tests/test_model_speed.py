"""
Human-OS Engine - NVIDIA NIM 中文模型速率测试
使用直接 HTTP 请求，避免 langchain 库的模型验证问题
"""
import sys
import os
import time
import requests
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import settings

keys = settings.get_api_keys()
api_key = keys[0]
base_url = settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1"

print(f"API Keys: {len(keys)}")
print(f"Base URL: {base_url}")
print(f"测试提示: '简要说明什么是复利效应？'\n")

# 测试模型列表
MODELS = [
    # Qwen 系列
    "qwen/qwen2.5-7b-instruct",
    "qwen/qwen2.5-coder-32b-instruct",
    "qwen/qwq-32b",
    
    # DeepSeek 系列
    "deepseek-ai/deepseek-v3.1",
    "deepseek-ai/deepseek-v3.2",
    "deepseek-ai/deepseek-r1-distill-qwen-32b",
    
    # 其他
    "z-ai/glm5",
    "minimaxai/minimax-m2.5",
    "moonshotai/kimi-k2-thinking",
    
    # 对比：当前 Llama
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
]

TEST_PROMPT = "简要说明什么是复利效应？"

results = []

for i, model in enumerate(MODELS, 1):
    print(f"[{i}/{len(MODELS)}] {model}...", end=" ", flush=True)
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": TEST_PROMPT}],
            "temperature": 0.3,
            "max_tokens": 512,
        }
        
        start = time.time()
        resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            chars = len(content)
            print(f"✅ {elapsed:.1f}s | {chars}字")
            results.append({"model": model, "time": elapsed, "chars": chars, "ok": True})
        else:
            err = resp.text[:80]
            print(f"❌ HTTP {resp.status_code}: {err}")
            results.append({"model": model, "time": 0, "chars": 0, "ok": False, "error": err})
            
    except Exception as e:
        err = str(e)[:80]
        print(f"❌ {err}")
        results.append({"model": model, "time": 0, "chars": 0, "ok": False, "error": err})
    
    time.sleep(2)  # 避免限速

# 汇总
print(f"\n{'='*70}")
print("测试结果汇总")
print(f"{'='*70}")
print(f"{'模型':<45} {'状态':<5} {'延迟':<8} {'字数':<6}")
print("-"*70)

ok_results = [r for r in results if r["ok"]]
ok_results.sort(key=lambda x: x["time"])

for r in ok_results:
    print(f"{r['model']:<45} {'✅':<5} {r['time']:<8.1f} {r['chars']:<6}")

for r in results:
    if not r["ok"]:
        print(f"{r['model']:<45} {'❌':<5} {'N/A':<8} {'N/A':<6}")

# 推荐
if ok_results:
    fastest = ok_results[0]
    best_quality = max(ok_results, key=lambda x: x["chars"])
    
    # 找一个平衡的（不太慢，字数不少）
    balanced = sorted(ok_results, key=lambda x: x["time"] if x["chars"] > 50 else x["time"]*2)[0]
    
    print(f"\n{'='*70}")
    print("推荐配置")
    print(f"{'='*70}")
    print(f"FAST（元控制器）: {fastest['model']} ({fastest['time']:.1f}s)")
    print(f"STANDARD（知识路由）: {balanced['model']} ({balanced['time']:.1f}s, {balanced['chars']}字)")
    print(f"DEEP（话术生成）: {best_quality['model']} ({best_quality['time']:.1f}s, {best_quality['chars']}字)")
