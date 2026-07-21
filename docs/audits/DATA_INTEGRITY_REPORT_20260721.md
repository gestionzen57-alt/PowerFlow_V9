# Rapport Data Integrity V9 — 2026-07-21 04:56 UTC

## TL;DR
- **DB integrity : ✅ OK** — aucun doublon, aucune corruption, schémas cohérents.
- **Couverture streams : 🔴 67% MORTS** — 28/42 streams (symbol × timeframe) sans données depuis >60min.
- **Action immédiate** : `v9_ops.py start` pour relancer le daemon Python si tué, puis vérifier côté MT4 que les 6×7 EAs sont bien sur les charts et que `ReplayOnInit=true` les fait rejouer au démarrage.

## Détail DB integrity (data/v9_forces.db, 3.7 GB)

| Vérification | Résultat |
|---|---|
| Doublons `forces_snapshots.snapshot_id` | ✅ ratio 1.000 (143894 lignes / 143894 uniques) |
| Doublons `forces_snapshots` par symbol | ✅ ratio 1.00 sur tous les symbols |
| Top snapshot_id dupliqués | ✅ aucun |
| Tables shadow/archive | ⚠️ `principle_evaluations_shadow_archive_20260718` 1.98M (historique), `meta_strategy_shadow_log` 10k (Phase E) |
| Tables vides suspectes | ⚠️ `agent_event_bus=0`, `cognitive_journal=0`, `principle_causal_journal=1` |
| Schéma `paper_trades` | 10 cols, pas de `symbol`/`created_at` (résolution via `snapshot_id` JOIN) |

## Distribution regime_snapshots (665872 lignes)

| Symbol | Lignes | Note |
|---|---|---|
| GBPUSD | 566456 | 85% du total — bien plus actif (REPLAY + ticks continus) |
| USDJPY | 25008 | sous-alimenté |
| EURUSD | 20048 | sous-alimenté |
| USDCHF | 21344 | sous-alimenté |
| USDCAD | 18616 | sous-alimenté |
| AUDUSD | 14400 | sous-alimenté |

## Distribution par TF

| TF | Lignes | Note |
|---|---|---|
| M15 | 434616 | dominant |
| M1 | 108016 | OK |
| M5 | 97008 | OK |
| M30 | 10048 | faible |
| H1 | 7400 | faible |
| H4 | 4656 | faible |
| D1 | 4128 | faible (1 bougie/jour) |

## Fraicheur streams (NOW = 2026-07-21 04:56 UTC)

### 🟢 LIVE (≤10min) — 10 streams
- AUDUSD M15, AUDUSD M5
- EURUSD M1
- GBPUSD M15, M5, M1
- USDCAD M1
- USDCHF M1
- USDJPY M1

### 🟡 LENT (10-60min) — 4 streams
- AUDUSD H1, M30
- GBPUSD H1, M30

### 🔴 MORT (>60min) — 28 streams

| Symbol | TF morts | Δ minutes | Note |
|---|---|---|---|
| EURUSD | D1, H4, H1, M30, M5 | 3952-6109 | tous morts depuis 3-4 jours |
| USDCHF | D1, H4, H1, M15, M30 | 1195-5034 | tous morts depuis 1-4 jours |
| USDCAD | D1, H4, H1, M15, M30, M5 | 314 | tous TF morts depuis 5h |
| AUDUSD | H4, D1 | 236-475 | partiel |
| USDJPY | H4, H1, M30, M15, M5, D1 | 475-1195 | partiel |
| GBPUSD | H4, D1 | 236-474 | partiel |

## Hypothèses (par ordre de probabilité)

1. **MT4 a planté/redémarré** sur certains terminals, les EAs ne sont pas revenus proprement (cf. skill `daemon-mort` 2026-07-16). Le daemon Python `capture_server` peut aussi être mort côté Windows.
2. **Crash silencieux des EAs** : MT4 « sans réponse » = EA gelée, n'envoie plus. Refresh MT4 ou ré-attachement EA peut suffire.
3. **Marché fermé** : c'est mardi 04:56 UTC = avant l'ouverture Asie. Les TF D1 meurent naturellement entre 22:00 UTC et ~21:00 UTC le lendemain (1 bougie/jour). Mais EURUSD M5 mort depuis 4j = pas naturel.

## Action immédiate recommandée

```bash
# 1. Vérifier daemon Python
.venv/Scripts/python.exe -c "
import socket
try:
    s = socket.socket()
    s.settimeout(2)
    s.connect(('127.0.0.1', 31685))
    print('capture_server: UP')
except Exception as e:
    print(f'capture_server: DOWN ({e})')
"

# 2. Si DOWN, relancer en foreground ou via v9_ops
# (voir skill daemon-mort pour recette)

# 3. Côté MT4, vérifier que les EAs V9_Sonde_TF et V9_Sonde_M1 sont
# bien attachés sur les 6 paires × 7 TF (42 charts au total).
# Onglet Experts → "[V9 Sonde ...] Sent | ..." doit défiler.
```

## Garde-fous respectés

- Aucune modif DB, lecture seule.
- Backup R8 non requis (audit read-only).
- Motion #18 REGIME non-active respectée.
- Phase 12 EXECUTION OFF respectée.

## Référence

- Skill daemon-mort : `powerflow-v9-module-authoring` §9 (recette crash recovery)
- AGENT.md §Commandes de vérification rapide
- ea/V9_Sonde_README.md §3 (vérification envoi EA)