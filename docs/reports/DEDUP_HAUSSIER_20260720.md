# DEDUP Haussier GBPUSD — Motion B (2026-07-20)

- **18 doublons** GBPUSD M15 haussier (3 snapshots × 7, `opened_at` 19/07 15h41 → 20/07 00h05) supprimés — même bug d'idempotence `post_decision_hook` que le baissier, désormais corrigé par `bff59e2` (empêche les futurs doublons). Trade légitime conservé = le plus ancien par `opened_at` (ouvert 15h41).
- Réversibilité **R8** : backup in-DB `paper_trades_dedup_20260720` (18 lignes) ; `PRAGMA quick_check`=ok ; pas de VACUUM (writer live). `V9_EXECUTION_ENABLED=0`.
- **paper_trades** : 1 173 → **1 155** (−18) ; 0 doublon restant dans la fenêtre ≥ 2026-07-19. Effet de bord attendu : `test_post_catastrophe_wr_acceptable` (WR live 18/07+) 35.6 % → **29.6 % (n=27)** — la dédup a retiré des wins ; test laissé **rouge et visible** (décision CEO, signal réel à surveiller, échantillon petit). Les 993 doublons du 17/07 (vague backtest début juillet) sont **hors périmètre** de cette motion.
