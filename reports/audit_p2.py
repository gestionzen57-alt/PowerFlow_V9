"""Audit SQL Phase 2 — 4 axes (90j + global)."""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row

print("=" * 60)
print("AUDIT PHASE 2 HEDGE FUND 28/07")
print("=" * 60)
print()

print("=== BILAN 90J GLOBAL ===")
r = conn.execute(
    "SELECT COUNT(*) n, SUM(is_win) w, ROUND(SUM(pips_simulated),1) total, "
    "ROUND(AVG(pips_simulated),2) avg, ROUND(100.0*SUM(is_win)/COUNT(*),1) wr "
    "FROM paper_trades WHERE opened_at > datetime('now','-90 days')"
).fetchone()
print(f"n={r['n']} W={r['w']} WR={r['wr']}% total={r['total']}p avg={r['avg']}p")

print()
print("=== PNL PAR SYMBOL (90J) ===")
rows = conn.execute(
    "SELECT substr(snapshot_id,4,6) sym, COUNT(*) n, "
    "ROUND(100.0*SUM(is_win)/COUNT(*),1) wr, "
    "ROUND(SUM(pips_simulated),1) total, "
    "ROUND(AVG(CASE WHEN is_win=1 THEN pips_simulated ELSE 0 END),2) avg_win, "
    "ROUND(AVG(CASE WHEN is_win=0 THEN pips_simulated ELSE 0 END),2) avg_loss "
    "FROM paper_trades WHERE opened_at > datetime('now','-90 days') "
    "GROUP BY sym ORDER BY total DESC"
).fetchall()
for r in rows:
    wins = r['n'] * (r['wr'] / 100.0)
    losses = r['n'] - wins
    gross_win = wins * r['avg_win']
    gross_loss = losses * abs(r['avg_loss'])
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0
    print(f"  {r['sym']:8s} n={r['n']:3d} WR={r['wr']:5.1f}% total={r['total']:+7.1f}p "
          f"avg_win={r['avg_win']:+5.2f}p avg_loss={r['avg_loss']:6.2f}p PF={pf:5.2f}")

print()
print("=== HEURES DE TRADE 7J (UTC) ===")
rows = conn.execute(
    """
    SELECT strftime('%H', fs.timestamp) as hour, COUNT(*) n
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE pt.opened_at > datetime('now','-7 days')
    GROUP BY hour ORDER BY hour
    """
).fetchall()
for r in rows:
    print(f"  {r['hour']}h: {r['n']} trades")

print()
print("=== BEST HOUR x SYMBOL (90J) ===")
rows = conn.execute(
    """
    SELECT substr(pt.snapshot_id,4,6) sym, strftime('%H', fs.timestamp) hour,
           COUNT(*) n, ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE pt.opened_at > datetime('now','-90 days')
    GROUP BY sym, hour HAVING n>=5 ORDER BY total DESC LIMIT 15
    """
).fetchall()
for r in rows:
    print(f"  {r['sym']:8s} {r['hour']}h n={r['n']:3d} total={r['total']:+7.1f}p")

conn.close()
