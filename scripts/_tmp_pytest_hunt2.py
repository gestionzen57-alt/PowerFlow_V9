"""Wrapper pytest batch 1 (a-l fichiers)."""
import subprocess
import os
import time

FIXED = {
    'test_mcp_servers.py',
    'test_mcp_servers_new.py',
    'test_mcp_servers_phase_e1.py',
    'test_v9_pyramiding_engine.py',
    'test_v9_re_resolve.py',
    'test_v9_self_improving.py',
}

files = sorted([
    f for f in os.listdir('tests')
    if f.startswith('test_') and f.endswith('.py') and f not in FIXED
])

# Batch 1: a-l (premiere moitie alphabetique)
batch1 = [f for f in files if f < 'test_m']
print(f"Batch 1: {len(batch1)} files (a-l)")

# Lancer pytest sur le batch 1 avec timeout 180s
start = time.time()
try:
    r = subprocess.run(
        ['.venv/Scripts/python', '-m', 'pytest', 'tests/']
        + [f'tests/{f}' for f in batch1]
        + ['-q', '--tb=no', '-p', 'no:cacheprovider',
           '-k', 'not test_arbiter::test_trader_mini', '--co'],
        capture_output=True, text=True, timeout=60, cwd='.',
    )
    print(f"Collection OK in {time.time()-start:.1f}s")
    # Last line of output
    print(r.stdout.split('\n')[-2] if r.stdout else r.stderr)
except subprocess.TimeoutExpired:
    print(f"Collection HANG after {time.time()-start:.1f}s")
    # Find which file hangs by narrowing down
    mid = len(batch1) // 2
    batch1a = batch1[:mid]
    batch1b = batch1[mid:]

    for subname, sub in [('batch1a', batch1a), ('batch1b', batch1b)]:
        start = time.time()
        try:
            r = subprocess.run(
                ['.venv/Scripts/python', '-m', 'pytest'] + [f'tests/{f}' for f in sub]
                + ['-q', '--tb=no', '-p', 'no:cacheprovider', '-k',
                   'not test_arbiter::test_trader_mini', '--co'],
                capture_output=True, text=True, timeout=30, cwd='.',
            )
            print(f"{subname} collection OK in {time.time()-start:.1f}s ({len(sub)} files)")
        except subprocess.TimeoutExpired:
            print(f"{subname} collection HANG after {time.time()-start:.1f}s ({len(sub)} files)")
