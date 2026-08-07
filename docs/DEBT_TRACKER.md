# DEBT_TRACKER — PowerFlow V10
**Registre des dettes techniques actives**  
**Mis à jour :** 2026-08-07 12:18 CEST

> Toute dette doit avoir un propriétaire et une date cible.  
> Statuts : 🔴 Critique · 🟡 Modéré · 🟢 Mineur · ✅ Résolue

---

## Dettes actives

| ID | Sévérité | Description | Propriétaire | Date cible | Statut |
|---|---|---|---|---|---|
| D01 | 🔴 | 15 tests V9 rouges (pré-existants, V9 verrouillé) | Søn (mandat requis) | TBD | 🔴 Open |
| D02 | 🟡 | `V9_EXECUTION_ENABLED=1` résidu dans `config/v9_kill_switches.env` | Zcode | Next sprint | 🟡 Open |
| D03 | 🟡 | `docs/V10/CACHE_BOARD.md` obsolète (692 tests, HEAD 40ed93a) | Hermes | Next sprint | 🟡 Open |
| D04 | 🟡 | `V10_QUANT_UPGRADE_SPRINT23.md` — sprint 23 non commencé | Zcode | TBD | 🟡 Open |
| D05 | 🟢 | Plusieurs docs/checkpoint_*.md dupliqués sans consolidation | Perplexity | Session actuelle | 🟢 Open |
| D06 | 🟢 | `dashboard_live.html` et `dashboard_v10_ceo.html` — pas reliés à la vraie DB | Zcode | TBD | 🟢 Open |

---

## Dettes résolues

| ID | Description | Résolution | Date |
|---|---|---|---|
| R01 | Safe Haven flip inversé `v10_currency_strength` | commit `885a851` fix signe | 2026-08-05 |
| R02 | Doublon `v10_strategy_layers` / `v10_filter_compositor` | Wrapper réécrit | 2026-08 |
| R03 | `core/v10/__init__.py` 27 noms non résolus dans `__all__` | Réparé exhaustivement | 2026-08 |
| R04 | Stale gate dans boucles live (audit R9) | Réparé sprint R9 | 2026-08 |

---

## Règle de gestion

1. Toute nouvelle dette détectée → ajout immédiat ici avec ID séquentiel
2. Toute résolution → déplacer en section "Résolues" avec commit de référence
3. Aucune dette D01/D02 ne peut être marquée ✅ sans commit vérifié
4. CEO review dettes 🔴 à chaque checkpoint session
