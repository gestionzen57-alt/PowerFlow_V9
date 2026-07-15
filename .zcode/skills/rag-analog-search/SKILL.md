---
name: rag-analog-search
description: "Recherche sémantique RAG ChromaDB PowerFlow avec metadata filter pour trouver des analogies de setups (zone/session/vol_regime/outcome). Utilise mcp__powerflow-rag__rag_search_narrative, rag_top_analogies, rag_wr_by_analogy."
version: 1.0
statut: ACTIVE
proprietaire: Hermes (profil powerflow)
date_creation: 2026-06-29
auto_update: true
derniere_maj: 2026-07-09
---
# rag-analog-search — Recherche d'analogies RAG PowerFlow

## Quand l'utiliser

Déclencheur : "trouve des analogies pour X", "quelles décisions similaires à Y ?", "WR historique zone Z + session S ?", "cherche dans la mémoire RAG", "quand on a vu pareil la dernière fois".

NE PAS utiliser pour : recherche web, live market data (→ get_live_snapshot), calibration WR globale (→ kpi_session_performance 3114).

## Outils MCP (port 3115)

### 1. `rag_top_analogies` — top-N analogies pour setup live
**Usage** : injecter dans prompt LLM pf_analyst avant décision.

```python
mcp__powerflow-rag__rag_top_analogies(
    symbol="GBPUSD",
    vol_regime="CALM",
    session="NY",
    key_pattern="GBP_EXHAUSTION_USD_WEAK",  # optionnel
    metadata_filter={"$and": [{"outcome": "WIN"}]},  # optionnel
    n_results=5,
    max_chars=600
)
```

Retourne : `{block, char_count, hits_count, wr_observed, n_resolved}`.
- `block` : texte prêt à injecter dans prompt
- `wr_observed` : % WR empirique sur les hits résolus (None si <5 samples)

### 2. `rag_search_narrative` — recherche libre multi-collections
```python
mcp__powerflow-rag__rag_search_narrative(
    query="GBPUSD LOW NY construction",
    collections=["analyst_decisions", "fresh_decision_log"],  # defaut = 15
    metadata_filter={"zone": "LOW", "session": "NY"},  # wrap $and auto
    n_results=5
)
```

Retourne : `{hits: [{content_preview, source, distance, type, timestamp}], count, elapsed_ms}`.

### 3. `rag_wr_by_analogy` — WR empirique par contexte
```python
mcp__powerflow-rag__rag_wr_by_analogy(
    zone="LOW",
    session="NY",
    vol_regime="CALM",  # optionnel
    outcome_filter="WIN",  # "" = tous
    n_results=50
)
```

Retourne : `{n_hits, wins, losses, wr_pct, context}`.

## Filtres ChromaDB avancés

```python
# Egalité simple
{"zone": "LOW"}

# Multi-clés (wrap $and automatique par _filter_to_chromadb_where)
{"zone": "LOW", "session": "NY", "vol_regime": "CALM"}
# Equivalent à {"$and": [{"zone":"LOW"}, {"session":"NY"}, {"vol_regime":"CALM"}]}

# Outcome résolu seulement (analyst_outcomes.resolution non-NULL)
{"outcome": {"$ne": None}}
```

ATTENTION : ChromaDB exige UN SEUL opérateur top-level → wrap `$and` obligatoire si multi-clés.

## Workflow typique

1. **Décision live** : `rag_top_analogies(vol_regime=current, session=current, key_pattern=top_pattern)` → bloc 600 chars injecté dans prompt.
2. **Audit setup** : `rag_wr_by_analogy(zone=Z, session=S)` → WR historique avant de risquer le capital.
3. **Recherche libre** : `rag_search_narrative(query, collections=pertinentes)` → explorer la mémoire RAG.

## Limites

- **Latence** : 50-150ms cold, 0ms cache hit (TTL 90s dans core/pf_analyst_rag.py).
- **BUG STATE.md #1** : `analyst_outcomes.resolution` NULL sur 937/937 rows → `outcome_filter="WIN"` retourne 0 hit jusqu'au backfill resolver (P0 #1 weekly analysis).
- **Distances cosinus** : < 1.5 = bonne analogie ; 1.5-2.0 = marginal ; > 2.0 = bruit.

## Liens

- Module : `core/pf_rag_document_builder.py` (génère les docs narratifs)
- Module : `core/pf_analyst_rag.py` (analogies → prompt pf_analyst)
- Pilier : `docs/RAG_PILLIER.md` (architecture complète)
- Usage : `docs/RAG_USAGE.md` (API rag_query + rag_search)