"""audit_p2_v4.py — Phase 5 motion CEO « EDGE FUND MAX » recherche leviers."""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row

print("=" * 60)
print("PHASE 5 — NOUVEAUX LEVIERS EDGE FUND")
print("=" * 60)

# 1. Regime x GBPUSD haussier
print()
print("=== GBPUSD HAUSSIERE x REGIME (90j) ===")
rows = conn.execute(
    """
    SELECT rs.regime_type, rs.vol_regime, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY rs.regime_type, rs.vol_regime HAVING n>=5 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!! MEGA' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:8s} regime={str(r['regime_type']):15s} vol={str(r['vol_regime']):10s} "
          f"n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 2. Top paires 11-13h UTC (corrélation inter-paires)
print()
print("=== TOP PAIRES HAUSSIERE 11-13h UTC (90j) ===")
rows = conn.execute(
    """
    SELECT substr(pt.snapshot_id,4,6) sym, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE pt.direction='haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY sym HAVING n>=5 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:3s} {r['sym']:8s} n={r['n']:3d} "
          f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 3. Behavior x GBPUSD haussiere 11-13h UTC
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x BEHAVIOR ===")
try:
    rows = conn.execute(
        """
        SELECT b.qualification, COUNT(*) n,
               ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
               ROUND(SUM(pt.pips_simulated),1) total
        FROM paper_trades pt
        JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
        JOIN behaviors b ON b.snapshot_id = pt.snapshot_id
        WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
          AND pt.direction='haussiere'
          AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
          AND pt.opened_at > datetime('now','-90 days')
        GROUP BY b.qualification HAVING n>=3 ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
        print(f"  {flag:3s} {str(r['qualification']):25s} n={r['n']:3d} "
              f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR: {e}")

# 4. Vol regime (faible/moyen/fort) sur GBPUSD haussiere 11-13h UTC
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x VOL_REGIME ===")
rows = conn.execute(
    """
    SELECT rs.vol_regime, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY rs.vol_regime HAVING n>=3 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:3s} vol={str(r['vol_regime']):10s} n={r['n']:3d} "
          f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 5. Daily PNL GBPUSD haussiere 60j
print()
print("=== DAILY PNL GBPUSD HAUSSIERE 60j ===")
rows = conn.execute(
    """
    SELECT date(pt.opened_at) d,
           ROUND(SUM(pt.pips_simulated),1) daily_pnl,
           COUNT(*) n
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND pt.opened_at > datetime('now','-60 days')
    GROUP BY d HAVING n>=1 ORDER BY d DESC LIMIT 20
    """
).fetchall()
total_pnl = 0
for r in rows:
    flag = 'WIN' if r['daily_pnl'] > 0 else 'LOSS'
    total_pnl += r['daily_pnl']
    print(f"  {flag:4s} {r['d']} n={r['n']:2d} daily={r['daily_pnl']:+7.1f}p")
print(f"\n  TOTAL 60j GBPUSD haussiere = {total_pnl:+.1f}p")

conn.close()