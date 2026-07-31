"""audit_p2_v5.py — Phase 6 motion CEO « EDGE FUND MAX ».

Recherche leviers complementaires : vol_regime × session × comportemental.
"""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row

print("=" * 60)
print("PHASE 6 — NOUVEAUX LEVIERS EDGE FUND (v5)")
print("=" * 60)

# 1. vol_regime × GBPUSD haussier 11-13h UTC
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x VOL_REGIME ===")
rows = conn.execute(
    """
    SELECT rs.vol_regime, rs.vol_regime_level, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY rs.vol_regime, rs.vol_regime_level HAVING n>=3 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!! MEGA' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:8s} vol={str(r['vol_regime']):12s} lvl={r['vol_regime_level']} "
          f"n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 2. Session × GBPUSD haussier 90j
print()
print("=== GBPUSD HAUSSIERE x SESSION (90j) ===")
rows = conn.execute(
    """
    SELECT
      CASE
        WHEN cast(strftime('%H', fs.timestamp) as int) BETWEEN 7 AND 10 THEN 'asia'
        WHEN cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 14 THEN 'london_ny'
        WHEN cast(strftime('%H', fs.timestamp) as int) BETWEEN 15 AND 18 THEN 'ny'
        ELSE 'other'
      END as session,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY session HAVING n>=5 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:3s} {r['session']:15s} n={r['n']:3d} "
          f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 3. delta_vol (CVD) × GBPUSD haussier 11-13h UTC
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x DELTA_VOL (CVD) ===")
try:
    rows = conn.execute(
        """
        SELECT
          CASE
            WHEN rs.delta_vol > 100 THEN 'haute'
            WHEN rs.delta_vol BETWEEN -100 AND 100 THEN 'neutre'
            ELSE 'basse'
          END as delta_bucket,
          COUNT(*) n,
          ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
          ROUND(SUM(pt.pips_simulated),1) total
        FROM paper_trades pt
        JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
        JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
        WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
          AND pt.direction='haussiere'
          AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
          AND pt.opened_at > datetime('now','-90 days')
          AND rs.delta_vol IS NOT NULL
        GROUP BY delta_bucket HAVING n>=3 ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
        print(f"  {flag:3s} delta_{r['delta_bucket']:8s} n={r['n']:3d} "
              f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR: {e}")

# 4. palier (consolidation) × GBPUSD haussier 11-13h UTC
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x PALIER_TYPE ===")
rows = conn.execute(
    """
    SELECT
      CASE
        WHEN rs.palier_duration_bars >= 100 THEN 'long_palier'
        WHEN rs.palier_duration_bars BETWEEN 20 AND 99 THEN 'med_palier'
        WHEN rs.palier_duration_bars < 20 THEN 'short_palier'
        ELSE 'no_palier'
      END as palier_bucket,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
      AND rs.palier_duration_bars IS NOT NULL
    GROUP BY palier_bucket HAVING n>=3 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:3s} palier_{r['palier_bucket']:14s} n={r['n']:3d} "
          f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 5. Top correlation GBPUSD haussier 11-13h UTC x regime_type (filtre)
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x REGIME (top) ===")
rows = conn.execute(
    """
    SELECT rs.regime_type, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY rs.regime_type HAVING n>=3 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:3s} {str(r['regime_type']):20s} n={r['n']:3d} "
          f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# 6. Stale regime (drift detection) - regim non-frais
print()
print("=== GBPUSD HAUSSIERE 11-13h UTC x STALE ===")
try:
    rows = conn.execute(
        """
        SELECT rs.stale, COUNT(*) n,
               ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
               ROUND(SUM(pt.pips_simulated),1) total
        FROM paper_trades pt
        JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
        JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
        WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
          AND pt.direction='haussiere'
          AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
          AND pt.opened_at > datetime('now','-90 days')
          AND rs.stale IS NOT NULL
        GROUP BY rs.stale HAVING n>=3 ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        flag = '!!!' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
        print(f"  {flag:3s} stale={r['stale']} n={r['n']:3d} "
              f"WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR: {e}")

conn.close()