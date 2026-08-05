# ACTIVE TASKS — PowerFlow V10
_Mise à jour : 2026-08-05 — Session Perplexity_

---

## 🔥 TÂCHE CRITIQUE (BLOQUANTE)

### TASK-001 — `v10_currency_strength.py`
- **Priorité** : P0 — bloquant tout le reste
- **Statut** : 🔴 À créer
- **Responsable** : Hermes (Claude Code)
- **Chemin** : `core/v10/v10_currency_strength.py`
- **Contrainte doctrine** : R2 additif pur — ne pas modifier les modules V9 existants
- **Tests minimum** : 15 tests verts avant passage à TASK-002
- **Logique** : Reproduire calcul scores devises Fatman
  - 8 devises majeures : USD / EUR / GBP / JPY / CHF / CAD / AUD / NZD
  - Score par devise = moyenne pondérée des forces relatives sur M5/M15/M30/H1
  - Delta score = score_devise_A - score_devise_B → signal directionnel
  - Seuil signal fort : |delta| ≥ 2.0
  - Seuil signal moyen : 1.0 ≤ |delta| < 2.0

---

## 📋 TÂCHE SUIVANTE (dépend de TASK-001)

### TASK-002 — Injection M30 dans modules existants
- **Priorité** : P1 — après TASK-001 validée
- **Statut** : 🟡 En attente
- **Responsable** : Hermes
- **Fichiers** : `core/v10/v10_force.py`, `core/v10/v10_structure.py`, `core/v10/v10_context.py`
- **Action** : Ajouter timeframe M30 = 1800 secondes dans la grille TF
- **Contrainte** : 54 tests existants doivent rester verts après modification
- **Tests à ajouter** : ≥10 tests spécifiques M30

---

## 📋 TÂCHE SUIVANTE (dépend de TASK-002)

### TASK-003 — `v10_signal_engine.py`
- **Priorité** : P2
- **Statut** : 🟡 En attente
- **Responsable** : Hermes
- **Chemin** : `core/v10/v10_signal_engine.py`
- **Logique** : Agréger currency_strength + force + structure + context → signal composite
- **Output** : score confiance 0-100, direction, TF de déclenchement, levier recommandé
- **Tests minimum** : 20 tests

---

## 📋 TÂCHE DOCUMENTATION

### TASK-004 — Mise à jour `docs/STATE.md`
- **Priorité** : P1 (parallèle TASK-001)
- **Statut** : 🟡 À faire
- **Action** : Mettre à jour section "Phase V10" avec état TASK-001/002/003

---

## ❄️ TÂCHES GELÉES
- Phase 10 fédération agents → gelé doctrine
- Skills auto-générés → gelé doctrine
- Architecture mémoire avancée → gelé doctrine
