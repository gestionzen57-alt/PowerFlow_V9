"""Wrapper pytest avec timeout par fichier (30s)."""
import subprocess
import os
import sys
import time

# Fichiers deja fixes (skip)
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

print(f"Total files to test: {len(files)}")
print(f"Timeout per file: 30s")
print("---")

results = {}
for f in files:
    start = time.time()
    try:
        r = subprocess.run(
            ['.venv/Scripts/python', '-m', 'pytest', f'tests/{f}',
             '-q', '--tb=no', '-p', 'no:cacheprovider',
             '-k', 'not test_arbiter::test_trader_mini'],
            capture_output=True, text=True, timeout=30, cwd='.',
        )
        duration = time.time() - start
        # Parse output
        out = r.stdout + r.stderr
        if 'failed' in out.lower() or 'error' in out.lower():
            # Extraire le nombre de F
            for line in out.split('\n'):
                if 'failed' in line and ('passed' in line or 'error' in line):
                    results[f] = (line.strip(), duration)
                    print(f"{f}: {line.strip()} ({duration:.1f}s)")
                    break
            else:
                results[f] = ('? unknown ?', duration)
        else:
            results[f] = ('OK', duration)
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        results[f] = ('HANG', duration)
        print(f"{f}: HANG ({duration:.1f}s)")
    except Exception as e:
        results[f] = (f'EXC: {e}', duration)

print("---")
hangs = [f for f, r in results.items() if r[0] == 'HANG']
fails = [f for f, r in results.items() if r[0] not in ('OK', 'HANG') and 'failed' in r[0].lower()]
print(f"HANG: {len(hangs)} files: {hangs}")
print(f"FAIL: {len(fails)} files")
for f in fails[:20]:
    print(f"  {f}: {results[f][0]}")
