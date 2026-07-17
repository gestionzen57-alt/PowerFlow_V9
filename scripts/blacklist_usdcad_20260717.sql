-- Blacklist USDCAD si WR < 30% sur n >= 20
-- À exécuter lundi 2026-07-20 si le WR USDCAD est toujours < 30%
-- Usage: sqlite3 data/v9_forces.db < scripts/blacklist_usdcad_20260717.sql

-- 1. Vérifier le WR actuel (lecture seule, jamais bloquant)
.print '=== WR USDCAD (last 30 jours) ==='
SELECT
    'USDCAD WR:',
    ROUND(AVG(CASE WHEN is_win=1 THEN 1.0 ELSE 0.0 END) * 100, 1) as wr_pct,
    COUNT(*) as n_total,
    SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) as wins
FROM decisions
WHERE symbol='USDCAD'
  AND action='preparer_entree'
  AND is_win IS NOT NULL
  AND timestamp > datetime('now', '-30 days');

-- 2. Si WR < 30% sur n >= 20, exécuter le blacklist ci-dessous.
--    Le blacklist force `paper_risk_manager.evaluate()` à retourner `go=False`
--    pour USDCAD, sans modifier le code Python (kill switch via config).

-- Option A (recommandée, lecture seule) : ajouter une ligne dans config/v9_kill_switches.env
-- echo "V9_BLACKLIST_SYMBOLS=USDCAD" >> config/v9_kill_switches.env
-- (à implémenter si pas déjà câblé dans paper_risk_manager)

-- Option B (SQL direct, dangereux) : supprimer les trades existants USDCAD
-- pour ne pas biaiser les futures calibrations. NE PAS EXÉCUTER sans motion CEO.
-- DELETE FROM paper_trades WHERE symbol='USDCAD';
-- DELETE FROM decisions WHERE symbol='USDCAD' AND action='preparer_entree';

-- 3. Note : la décision finale (blacklist oui/non) appartient à Søn.
--    Ce script est un prepared-not-applied : il documente la procédure, ne l'applique pas.
