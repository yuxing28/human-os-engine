"""
Quick test: deepseek-v3.1 and v3.2 availability
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
base_url = settings.nvidia_base_url

print(f"Testing DeepSeek models on NVIDIA NIM...\n")

MODELS = [
    "deepseek-ai/deepseek-v3.1",
    "deepseek-ai/deepseek-v3.2",
    "deepseek-ai/deepseek-r1-distill-qwen-32b",
]

for model in MODELS:
    print(f"Testing {model}...", end=" ", flush=True)
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "用一句话回答：2+2等于几？"}],
            "temperature": 0.3,
            "max_tokens": 50,
        }
        
        start = time.time()
        resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=45)
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print(f"✅ {elapsed:.1f}s | {len(content)}字: {content[:60]}")
        else:
            print(f"❌ HTTP {resp.status_code}: {resp.text[:100]}")
            
    except requests.exceptions.Timeout:
        print(f"❌ 超时(45s)")
    except Exception as e:
        print(f"❌ {str(e)[:80]}")
