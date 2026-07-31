"""Verif mega-edge avec timestamp UTC correct."""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row

print("=== MEGA-EDGE: GBPUSD M5 haussiere 11-13h UTC (timestamp snapshot) ===")
# Utiliser fs.timestamp (du snapshot, plus fiable que opened_at)
rows = conn.execute(
    """
    SELECT COUNT(*) n, SUM(pt.is_win) w,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total,
           ROUND(AVG(pt.pips_simulated),2) avg
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
      AND pt.direction='haussiere'
      AND substr(pt.snapshot_id,instr(pt.snapshot_id,'-'),-2)='M5'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    """
).fetchall()
for r in rows:
    print(f"  n={r['n']} W={r['w']} WR={r['wr']}% total={r['total']}p avg={r['avg']}p")

print()
print("=== PNL 11-13h UTC par symbol/direction ===")
rows = conn.execute(
    """
    SELECT substr(pt.snapshot_id,4,6) sym, pt.direction, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY substr(pt.snapshot_id,4,6), pt.direction
    ORDER BY total DESC
    """
).fetchall()
for r in rows:
    print(f"  {r['sym']} {r['direction']:10s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

# Best hour/symbol/tf/direction
print()
print("=== TOP 20 (sym × tf × dir × hour) 90J n>=5 ===")
rows = conn.execute(
    """
    SELECT substr(pt.snapshot_id,4,6) sym, substr(pt.snapshot_id,instr(pt.snapshot_id,'-'),-2) tf,
           pt.direction, strftime('%H', fs.timestamp) h,
           COUNT(*) n, ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE pt.opened_at > datetime('now','-90 days')
    GROUP BY substr(pt.snapshot_id,4,6), substr(pt.snapshot_id,instr(pt.snapshot_id,'-'),-2),
             pt.direction, strftime('%H', fs.timestamp)
    HAVING n>=5 ORDER BY total DESC LIMIT 20
    """
).fetchall()
for r in rows:
    flag = '!!! MEGA' if r['wr'] >= 80 else ('OK' if r['wr'] >= 50 else 'KO')
    print(f"  {flag:8s} {r['sym']} {r['tf']} {r['direction']:10s} {r['h']}h "
          f"n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p")

conn.close()
