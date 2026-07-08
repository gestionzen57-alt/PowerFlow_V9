# Replay 7 derniers jours — 2026-07-08

Commande réelle : `python scripts/v9_replay_doctrine_realign.py --days 7 --db data/v9_forces_snapshot_20260708.db`
(le script n'expose pas `--since`/`--baseline-pre` comme indiqué dans la consigne initiale —
adapté à sa signature réelle : `--hours/--days/--symbol/--db/--from/--to`. La comparaison
pré-patch (10 ACTIVE) vs post-patch (27 ACTIVE) est calculée en interne par le script,
sans besoin de fichier baseline externe.)

Symbole : GBPUSD (défaut du script) — seul symbole significatif dans la fenêtre
(EURUSD = 1 seul snapshot sur 100743, négligeable, non rejoué séparément).

=== Replay doctrine realign : 58200 snapshot(s) GBPUSD 2026-07-01T08:59:59.380364+00:00 -> 2026-07-08T08:59:59.380364+00:00 ===
Pré-patch  ACTIVE (10) : ['ANTAGONIST_NODE', 'COALITION_NODE', 'ELASTIC_BREATH', 'GRAMMAR_REGIME', 'GRAVITY_RESPRING_NODE', 'NODE_BIRTH_FAST', 'POWER_ANGLE_BREAK_TO_PRICE_IMPACT', 'PRICE_LAG_AT_NODE_BIRTH', 'RAW_NODE_BIRTH', 'ZONE_RETEST']
Post-patch ACTIVE (27) : 27 principes


--- Bilan ---
  Snapshots comparés : 58200
  Divergences pré/post-patch : 0
  -> Aucune divergence : le patch doctrine realign n'a modifié aucun signal déjà produit (attendu : les 17 principes nouvellement ACTIVE sont kind=grammar, conditions vides, structurellement non-émetteurs).
