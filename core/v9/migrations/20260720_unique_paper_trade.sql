-- Motion #32 — idempotence paper_trades (résolution drift loop)
-- Schéma RÉEL de paper_trades : (trade_id PK, snapshot_id, direction, confiance,
-- principes_source, opened_at, closed_at, pips_simulated, is_win, risk_go_context).
-- Le prompt Motion #32 référençait (principle_name, side, outcome) — colonnes INEXISTANTES.
-- Contrainte durable réelle = UNIQUE(snapshot_id, direction, principes_source).
--
-- Idempotent : ré-exécutable sans effet de bord. Sur la prod du 2026-07-20 la dédup
-- est un NO-OP (0 doublon vérifié — les 18 fantômes sont déjà dans
-- paper_trades_dedup_20260720). Le DELETE protège d'une éventuelle réapparition
-- entre la vérif et la création de l'index (keep = MIN(rowid), le plus ancien).

-- 1) Dédup défensive (NO-OP si 0 doublon) — conserve la ligne la plus ancienne par triplet.
DELETE FROM paper_trades
WHERE rowid NOT IN (
    SELECT MIN(rowid)
    FROM paper_trades
    GROUP BY snapshot_id, direction, principes_source
);

-- 2) Contrainte d'unicité durable (empêche toute re-duplication future).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pt_snap_dir_princ
    ON paper_trades (snapshot_id, direction, principes_source);
