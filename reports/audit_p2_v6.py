"""audit_p2_v6.py — Phase 9 motion CEO « EDGE FUND MAX ».

Validation SQL reelle des 10 leviers L10-L19 + BUG-P6 + R6.
"""
import sqlite3

conn = sqlite3.connect(r"C:\projet\V9\data\v9_forces.db")
conn.row_factory = sqlite3.Row


def show(label, rows):
    print()
    print(f"=== {label} ===")
    if not rows:
        print("  (0 rows)")
        return
    for r in rows:
        d = dict(r)
        wr = d.get("wr") or 0
        flag = "!!! MEGA" if wr >= 80 else ("OK" if wr >= 50 else "KO")
        line = f"  {flag:8s}"
        for k, v in d.items():
            line += f" {k}={v}"
        print(line)


# L10 — CVD (FAUX POSITIF: pas de table cvd_snapshots)
show("L10 — CVD (FAUX POSITIF Perplexity, pas de table)", conn.execute("""
    SELECT 'no_cvd_table' as status, COUNT(*) n,
           ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
           ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
""").fetchall())

# L11 — Behavior qualification (jointure via scene_id_ref+symbol+timestamp)
show("L11 — Behavior qualification GBPUSD haussier 90j", conn.execute("""
    SELECT
      CASE WHEN b.qualification IS NULL THEN 'no_qualif'
           ELSE b.qualification END as qualif,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    LEFT JOIN scenes s ON s.forces_snapshot_ref = fs.snapshot_id
    LEFT JOIN behaviors b ON b.scene_id_ref = s.scene_id
      AND b.symbol = 'GBPUSD'
      AND b.timeframe = 'M5'
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY qualif HAVING n >= 3 ORDER BY total DESC
""").fetchall())

# L12 — Palier duration
show("L12 — Palier duration GBPUSD haussier 11-13h UTC 90j", conn.execute("""
    SELECT
      CASE WHEN rs.palier_duration_bars IS NULL THEN 'no_palier'
           WHEN rs.palier_duration_bars >= 80 THEN 'long_palier'
           WHEN rs.palier_duration_bars BETWEEN 20 AND 79 THEN 'med_palier'
           ELSE 'short_palier'
      END as palier_bucket,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    LEFT JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY palier_bucket HAVING n >= 3 ORDER BY total DESC
""").fetchall())

# L13 — Coalition HTF via scenes.coalitions_json
show("L13 — Coalition D1 JSON GBPUSD haussier 90j", conn.execute("""
    SELECT
      CASE WHEN s.coalitions_json IS NULL OR s.coalitions_json = '' THEN 'no_coalition'
           WHEN s.coalitions_json LIKE '%D1%' THEN 'has_D1'
           WHEN s.coalitions_json LIKE '%H4%' THEN 'has_H4_only'
           ELSE 'lower_TF_only'
      END as coalition_bucket,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    LEFT JOIN scenes s ON s.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY coalition_bucket HAVING n >= 3 ORDER BY total DESC
""").fetchall())

# L14 — Jour de la semaine
show("L14 — Jour de la semaine GBPUSD haussier 90j", conn.execute("""
    SELECT
      CASE cast(strftime('%w', pt.opened_at) as int)
        WHEN 0 THEN 'dimanche' WHEN 1 THEN 'lundi'
        WHEN 2 THEN 'mardi' WHEN 3 THEN 'mercredi'
        WHEN 4 THEN 'jeudi' WHEN 5 THEN 'vendredi'
        WHEN 6 THEN 'samedi'
      END as dow,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY dow ORDER BY total DESC
""").fetchall())

# L15 — Stars duo/trio
show("L15 — Principes GBPUSD haussier 90j (pur/duo/trio)", conn.execute("""
    SELECT
      CASE
        WHEN json_array_length(principes_source) = 1
             AND principes_source LIKE '%PRICE_LAG%' THEN 'PRICE_LAG_pur'
        WHEN json_array_length(principes_source) = 1
             AND principes_source LIKE '%POWER_ANGLE%' THEN 'PA_pur'
        WHEN json_array_length(principes_source) = 1
             AND principes_source LIKE '%GRAVITY%' THEN 'GRAVITY_pur'
        WHEN json_array_length(principes_source) = 2
             AND principes_source LIKE '%PRICE_LAG%'
             AND principes_source LIKE '%POWER_ANGLE%' THEN 'DUO_PA'
        WHEN json_array_length(principes_source) = 3
             AND principes_source LIKE '%PRICE_LAG%'
             AND principes_source LIKE '%POWER_ANGLE%'
             AND principes_source LIKE '%GRAVITY%' THEN 'TRIO_PAG'
        ELSE 'other'
      END as combo,
      COUNT(*) n,
      ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
      ROUND(SUM(pips_simulated),1) total
    FROM paper_trades
    WHERE substr(snapshot_id,4,6) = 'GBPUSD'
      AND direction = 'haussiere'
      AND opened_at > datetime('now','-90 days')
    GROUP BY combo HAVING n >= 3 ORDER BY total DESC LIMIT 10
""").fetchall())

# L16 — Vol regime
show("L16 — Vol regime GBPUSD haussier 11-13h UTC 90j", conn.execute("""
    SELECT
      CASE WHEN rs.vol_regime IS NULL THEN 'no_vol'
           ELSE rs.vol_regime END as vol_regime,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
    LEFT JOIN regime_snapshots rs ON rs.forces_snapshot_ref = fs.snapshot_id
    WHERE substr(pt.snapshot_id,4,6) = 'GBPUSD'
      AND pt.direction = 'haussiere'
      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
      AND pt.opened_at > datetime('now','-90 days')
    GROUP BY vol_regime HAVING n >= 3 ORDER BY total DESC
""").fetchall())

# L17 — Recovery post-3-loss
show("L17 — Trade #4 apres 3 losses GBPUSD haussier 90j", conn.execute("""
    SELECT outcome, COUNT(*) n, ROUND(AVG(pips_simulated),2) avg_pips
    FROM (
      SELECT pt.is_win as outcome, pt.pips_simulated,
        LAG(pt.is_win,1) OVER (PARTITION BY substr(pt.snapshot_id,4,6), pt.direction ORDER BY pt.opened_at) as prev1,
        LAG(pt.is_win,2) OVER (PARTITION BY substr(pt.snapshot_id,4,6), pt.direction ORDER BY pt.opened_at) as prev2,
        LAG(pt.is_win,3) OVER (PARTITION BY substr(pt.snapshot_id,4,6), pt.direction ORDER BY pt.opened_at) as prev3
      FROM paper_trades pt
      WHERE pt.opened_at > datetime('now','-90 days')
        AND substr(pt.snapshot_id,4,6) = 'GBPUSD'
        AND pt.direction = 'haussiere'
    ) WHERE prev1=0 AND prev2=0 AND prev3=0
    GROUP BY outcome
""").fetchall())

# L18 — EURUSD baissiere 13-15h UTC
show("L18 — EURUSD baissiere 13-15h UTC 90j", conn.execute("""
    SELECT
      substr(snapshot_id,4,6) sym, direction, COUNT(*) n,
      ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
      ROUND(SUM(pips_simulated),1) total
    FROM paper_trades
    WHERE substr(snapshot_id,4,6) = 'EURUSD'
      AND direction = 'baissiere'
      AND cast(strftime('%H', opened_at) as int) BETWEEN 13 AND 15
      AND opened_at > datetime('now','-90 days')
    GROUP BY sym, direction HAVING n >= 5
""").fetchall())

# L19 — Cognitive journal post-calibration (ts = unix epoch)
show("L19 — Trades post auto_calibrator (cogn journal) 90j", conn.execute("""
    SELECT
      CASE WHEN cj.id IS NULL THEN 'no_calib_event'
           WHEN pt.opened_at < datetime(cj.ts, 'unixepoch') THEN 'pre_calib'
           WHEN (julianday(pt.opened_at) - julianday(datetime(cj.ts, 'unixepoch'))) * 24 <= 2 THEN 'post_calib_fresh_2h'
           ELSE 'post_calib_stale'
      END as timing,
      COUNT(*) n,
      ROUND(100.0*SUM(pt.is_win)/COUNT(*),1) wr,
      ROUND(SUM(pt.pips_simulated),1) total
    FROM paper_trades pt
    LEFT JOIN cognitive_journal cj ON cj.event_type = 'auto_calibrator'
      AND cj.ts = (
        SELECT MAX(cj2.ts) FROM cognitive_journal cj2
        WHERE cj2.event_type = 'auto_calibrator' AND cj2.ts <= strftime('%s', pt.opened_at)
      )
    WHERE pt.opened_at > datetime('now','-90 days')
    GROUP BY timing HAVING n >= 3 ORDER BY total DESC
""").fetchall())

# BUG-P6 — Trades ouverts > 5min jamais fermes par L3
show("BUG-P6 — Trades > 5min ouverts (L3 devrait avoir agi)", conn.execute("""
    SELECT
      COUNT(*) total_open,
      SUM(CASE WHEN (julianday('now') - julianday(opened_at)) * 24 * 60 > 5 THEN 1 ELSE 0 END) aged_5min,
      SUM(CASE WHEN (julianday('now') - julianday(opened_at)) * 24 * 60 > 60 THEN 1 ELSE 0 END) aged_60min
    FROM paper_trades WHERE closed_at IS NULL
""").fetchall())

# R6 — Spread/slippage tracking
show("R6 — Spread/slippage tracking", conn.execute("""
    SELECT 'paper_trades.spread_pips' as col, COUNT(*) n FROM pragma_table_info('paper_trades') WHERE name LIKE '%spread%'
    UNION ALL
    SELECT 'paper_trades.slippage_pips', COUNT(*) FROM pragma_table_info('paper_trades') WHERE name LIKE '%slippage%'
    UNION ALL
    SELECT 'transaction_costs', COUNT(*) FROM pragma_table_info('paper_trades') WHERE name LIKE '%tx_cost%'
""").fetchall())

conn.close()
print()
print("=" * 70)
print("FIN AUDIT PHASE 9 SQL")
print("=" * 70)