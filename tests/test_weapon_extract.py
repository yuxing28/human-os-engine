"""Quick test: weapon extraction"""
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from schemas.context import Context
from simulation.arena_loop import run_system_once

ctx = Context(session_id='test_weapon')
print('Testing weapon extraction...')
start = time.time()
result = run_system_once('我好烦，工作压力大，怎么坚持学习？', ctx)
elapsed = time.time() - start

output = result['output']
print(f'Output: {output[:80]}...')
print(f'Weapons: {result["weapons_used"]}')
print(f'Mode: {result["context_snapshot"]["mode"]}')
print(f'Elapsed: {elapsed:.1f}s')
