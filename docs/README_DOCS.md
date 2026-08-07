# README_DOCS — Carte de navigation docs/
**Guide de navigation dans la documentation PowerFlow V10**  
**Mis à jour :** 2026-08-07 12:18 CEST

> Ce fichier est le point d'entrée unique pour trouver n'importe quel document.  
> Si un fichier n'est pas listé ici, il est soit archivé, soit obsolète.

---

## 📍 Fichiers critiques (lire en premier)

| Fichier | Rôle | Public |
|---|---|---|
| [`STATE.md`](STATE.md) | État opérationnel live + prochaines étapes | CEO + Agents |
| [`SOUL.md`](SOUL.md) | Vision + pipeline + modules + tables décision | CEO + Agents |
| [`ZCODE_MISSION.md`](ZCODE_MISSION.md) | Prompt démarrage + missions Zcode | Zcode |
| [`AGENT_PROMPT_MASTER.md`](AGENT_PROMPT_MASTER.md) | Prompt universel multi-agent | Tous agents |
| [`DECISIONS_LOG.md`](DECISIONS_LOG.md) | Journal décisions structurantes | CEO + Agents |

---

## 📐 Architecture & pipeline

| Fichier | Contenu |
|---|---|
| [`PIPELINE_MAP.md`](PIPELINE_MAP.md) | Pipeline ASCII + fail-open R6 + latences |
| [`LEVIER_HUB.md`](LEVIER_HUB.md) | 19 leviers L1-L19 + matrice compatibilité |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Architecture technique détaillée |
| [`INDEX_MODULES.md`](INDEX_MODULES.md) | Index complet des modules Python |
| [`NOMENCLATURE.md`](NOMENCLATURE.md) | Conventions de nommage |
| [`LEXIQUE.md`](LEXIQUE.md) | Glossaire termes techniques |

---

## 🗺️ Planification

| Fichier | Contenu |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | Feuille de route stratégique |
| [`HERMES_PLAN_V10.md`](HERMES_PLAN_V10.md) | Plan Hermes Sprints 1-15 |
| [`DEBT_TRACKER.md`](DEBT_TRACKER.md) | Registre dettes techniques |

---

## 🔧 Opérationnel

| Fichier | Contenu |
|---|---|
| [`SESSION_RITUEL.md`](SESSION_RITUEL.md) | Rituel démarrage/fin session |
| [`CRONS_INVENTORY.md`](CRONS_INVENTORY.md) | Inventaire crons actifs |
| [`GIT_OPERATOR_PROCEDURE.md`](GIT_OPERATOR_PROCEDURE.md) | Procédures Git |
| [`MULTI_IA_PROCEDURE.md`](MULTI_IA_PROCEDURE.md) | Coordination multi-agents |
| [`DOC_GOVERNANCE.md`](DOC_GOVERNANCE.md) | Règles de gouvernance docs |

---

## 📂 Dossiers

| Dossier | Contenu |
|---|---|
| `docs/V10/` | Documentation technique Sprints Hermes |
| `docs/audits/` | Rapports d'audit R1-R9 |
| `docs/checkpoints/` | Checkpoints CEO |
| `docs/phases/` | Documentation par phase |
| `docs/architecture/` | Schémas architecture |
| `docs/doctrine/` | Doctrine et principes |
| `docs/monitoring/` | Monitoring et alertes |

---

## 🗄️ Archivés (contexte uniquement)

Ces fichiers contiennent de l'historique utile mais ne reflètent pas l'état actuel :

- `JOURNAL_PHASES.md` — 102KB historique complet phases V9
- `BILAN_CEO_SPRINT_03_08_2026.md` — bilan daté
- `CHECKPOINT_SPRINT_CEO_03_08_2026*.md` — checkpoints datés
- `RAPPORT_SESSION_20260721.md` — rapport daté
- `LECTURE_MARCHE_ASYMETRIE_2026-07-18.md` — analyse marché datée
- `V9_PLAN_COMPLET.md`, `V9_FONCTIONNEMENT.md` — docs V9

---

## ⚡ Navigation rapide par question

| Question | Fichier |
|---|---|
| Quel est l'état actuel du système ? | `STATE.md` |
| Comment fonctionne le pipeline ? | `SOUL.md` section 2 ou `PIPELINE_MAP.md` |
| Quels modules existent ? | `SOUL.md` section 3 ou `INDEX_MODULES.md` |
| Quelles sont les dettes en cours ? | `DEBT_TRACKER.md` |
| Quelle mission pour Zcode ? | `ZCODE_MISSION.md` |
| Comment démarrer une session ? | `SESSION_RITUEL.md` |
| Pourquoi cette décision a été prise ? | `DECISIONS_LOG.md` |
| C'est quoi L7 ou le Hub score ? | `LEVIER_HUB.md` |
| Quand passera-t-on en réel ? | `ROADMAP.md` |
