"""
Quick test: direct HTTP call to minimax
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

print(f"Testing minimaxai/minimax-m2.5 via direct HTTP...")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
payload = {
    "model": "minimaxai/minimax-m2.5",
    "messages": [
        {"role": "system", "content": "你是一个助手，直接回答问题"},
        {"role": "user", "content": "用一句话回答：2+2等于几？不要任何分析。"}
    ],
    "temperature": 0.3,
    "max_tokens": 100,
}

start = time.time()
try:
    resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=30)
    elapsed = time.time() - start
    if resp.status_code == 200:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"OK ({elapsed:.1f}s): {content}")
    else:
        print(f"HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
