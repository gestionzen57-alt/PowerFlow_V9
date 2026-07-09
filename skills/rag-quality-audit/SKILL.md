---
name: rag-quality-audit
description: "Audit qualité du RAG ChromaDB PowerFlow : couverture collections, distances cosinus, NULL metadata, WR empirique par analogie. Utilise mcp__powerflow-rag__rag_quality_audit, rag_list_collections, rag_wr_by_analogy."
version: 1.0
statut: ACTIVE
proprietaire: Hermes (profil powerflow)
date_creation: 2026-06-29
auto_update: true
derniere_maj: 2026-07-09
---
# rag-quality-audit — Audit qualité RAG ChromaDB

## Quand l'utiliser

Déclencheur : "combien de docs dans chaque collection ?", "distances cosinus > 1.5 ?", "WR par zone/session ?", "le RAG est-il sain ?", "audit contamination pre/post 22/06", "vol_regime NULL combien ?".

NE PAS utiliser pour : live market data (→ get_live_snapshot), rebuild ChromaDB (→ rag-builder-exploit).

## Outils MCP (port 3115)

### 1. `rag_quality_audit` — métriques globales
```python
mcp__powerflow-rag__rag_quality_audit(
    collections=None,  # None = 15 canoniques
    sample_size=100  # échantillon pour distances cosinus
)
```

Retourne : `{collections: [{name, count, sample_metadata_keys, sample_distance}], total_collections, total_docs}`.

### 2. `rag_list_collections` — inventaire simple
```python
mcp__powerflow-rag__rag_list_collections(include_empty=False)
```

Retourne : `{collections: [{name, count, sample_metadata_keys}], total, total_docs}`.

### 3. `rag_wr_by_analogy` — WR empirique par contexte
Cf. skill `rag-analog-search` pour les détails.

## KPIs qualité

| KPI | Seuil OK | Seuil alerte |
|-----|----------|--------------|
| **Total docs / collection** | > 100 | < 100 |
| **Distance cosinus moyenne** | < 1.5 | > 2.0 |
| **NULL metadata ratio** | < 10% | > 30% |
| **Coverage post-22/06** | > 80% | < 50% |
| **WR observé par analogie** | cohérent avec kpi_session_performance (3114) | delta > 30pts |

## Diagnostic contamination (post-replay)

Le RAG ChromaDB est filtré par `--min-date 2026-06-22` (étape RAG clean 29/06) pour éviter que les données replay 200 bougies/TF (features NaN `gbp_tension`, `usd_tension`, `absorption_factor`, `depth_acceleration`) ne polluent les analogies sémantiques.

Pour vérifier la couverture post-filtrage :
```python
mcp__powerflow-rag__rag_quality_audit(
    collections=["fresh_decision_log", "fresh_detected_patterns",
                "fresh_structure_ledger", "fresh_scene_journal",
                "fresh_antagonism_log", "fresh_coalition_log"]
)
```

Comparaison baseline (RAG_PILLIER.md §3) :
- `fresh_decision_log` : 3960 baseline → 1994 filtré (-49.6%)
- `fresh_detected_patterns` : 2576 → 2063 (-19.9%)
- `fresh_structure_ledger` : 3000 → 2472 (-17.6%)

## Workflow typique

1. **Audit hebdomadaire** (cron 04:30 UTC) : `rag_quality_audit(collections=None)` → log dans cache/rag_audit_<date>.json.
2. **Diagnostic contamination** : après chaque rebuild, vérifier que coverage post-22/06 est > 80%.
3. **Delta WR** : comparer `rag_wr_by_analogy(zone=Z, session=S)` avec `kpi_session_performance()` (port 3114) → cohérence cross-sources.

## Liens

- Pilier : `docs/RAG_PILLIER.md` (architecture + métriques baseline)
- Usage : `docs/RAG_USAGE.md`
- Diagnostic contamination : cache/weekly_data_2026_06_29.json + reports/WEEKLY_ANALYSIS_2026_06_29.md
- Module : `core/mcp_powerflow_rag.py` (server L5 port 3115)