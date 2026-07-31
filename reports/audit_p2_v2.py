"""Audit SQL Phase 2 v2 — best hour, regime, vol, principes combination."""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row

print("=" * 60)
print("AUDIT PHASE 2 v2 — LEVIERS RENTABLES MAX")
print("=" * 60)

print()
print("=== BEST HOUR x GBPUSD (90J, n>=3) ===")
rows = conn.execute(
    """
    SELECT strftime('%H', fs.timestamp) hour,
           COUNT(*) n, ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY hour HAVING n>=3 ORDER BY total DESC
    """
).fetchall()
for r in rows:
    print(f"  {r['hour']}h n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# Regime (depuis regime_snapshots)
print()
print("=== PNL x REGIME 90J ===")
try:
    rows = conn.execute(
        """
        SELECT rs.regime_type, COUNT(*) n,
               ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
               ROUND(SUM(pt.pips_simulated),1) total
        FROM paper_trades pt
        JOIN regime_snapshots rs ON pt.snapshot_id = rs.snapshot_id
        WHERE pt.opened_at > datetime('now','-90 days')
        GROUP BY rs.regime_type HAVING n>=5 ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        print(f"  {r['regime_type']:20s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR {e}")

# Phase
print()
print("=== PNL x PHASE (cycle comportemental) 90J ===")
try:
    rows = conn.execute(
        """
        SELECT b.phase, COUNT(*) n,
               ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
               ROUND(SUM(pt.pips_simulated),1) total
        FROM paper_trades pt
        JOIN behaviors b ON pt.snapshot_id = b.snapshot_id
        WHERE pt.opened_at > datetime('now','-90 days')
        GROUP BY b.phase HAVING n>=5 ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        print(f"  {str(r['phase'])[:25]:25s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR {e}")

# Top principes purs (juste 1 principe, pas dilution)
print()
print("=== PRINCIPE PUR (1 seul) GBPUSD M5 HAUSSIERE 90J ===")
rows = conn.execute(
    """
    SELECT json_array_length(principes_source) as nb,
           principes_source, COUNT(*) n,
           ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
           ROUND(SUM(pips_simulated),1) total
    FROM paper_trades
    WHERE substr(snapshot_id,4,6)='GBPUSD' AND direction='haussiere'
      AND opened_at > datetime('now','-90 days')
    GROUP BY principes_source HAVING n>=3 ORDER BY total DESC LIMIT 15
    """
).fetchall()
for r in rows:
    print(f"  ({r['nb']}p) {str(r['principes_source'])[:60]:60s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# hold time effect
print()
print("=== SLOPE: trades <5min vs >30min ===")
try:
    rows = conn.execute(
        """
        SELECT
        CASE
          WHEN (julianday(closed_at) - julianday(opened_at))*24*60 < 5 THEN '<5min'
          WHEN (julianday(closed_at) - julianday(opened_at))*24*60 < 30 THEN '5-30min'
          ELSE '>30min'
        END as bucket, COUNT(*) n, ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
               ROUND(SUM(pips_simulated),1) total
        FROM paper_trades WHERE opened_at > datetime('now','-90 days')
        GROUP BY bucket ORDER BY total DESC
        """
    ).fetchall()
    for r in rows:
        print(f"  {r['bucket']:8s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")
except Exception as e:
    print(f"  ERR {e}")

# Pips distribution
print()
print("=== PIPS DISTRIB (gains/pertes) 90J ===")
rows = conn.execute(
    """
    SELECT
    CASE WHEN is_win=1 THEN 'GAINS' ELSE 'PERTES' END as cat,
           COUNT(*) n, ROUND(AVG(pips_simulated),2) avg,
           ROUND(MIN(pips_simulated),2) minp, ROUND(MAX(pips_simulated),2) maxp,
           ROUND(SUM(pips_simulated),1) total
    FROM paper_trades WHERE opened_at > datetime('now','-90 days')
    GROUP BY cat
    """
).fetchall()
for r in rows:
    print(f"  {r['cat']:8s} n={r['n']:3d} avg={r['avg']:+6.2f}p min={r['minp']:+6.2f}p max={r['maxp']:+6.2f}p total={r['total']:+7.1f}p")

conn.close()
