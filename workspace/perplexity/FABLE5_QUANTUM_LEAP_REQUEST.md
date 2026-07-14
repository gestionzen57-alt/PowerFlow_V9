# 🚀 FABLE 5 — INSTRUCTIONS (MAX 1 PAGE)

## ⚠️ CONTRAINTE CRITIQUE
Tu as cramé tous tes crédits la dernière fois. **Réponds en MAX 300 LIGNES de code/doc.** Si une tâche dépasse, découpe-la et demande confirmation avant de continuer. Ne génère JAMAIS plus de 300 lignes sans pause.

---

## 🎯 MISSION
PowerFlow V9 est un système de trading cognitif. Le pipeline live est **ACTIF** (37 décisions produites aujourd'hui). 7 crons Windows tournent. Telegram fonctionne. Tous les kill switches sont ON sauf `V9_EXECUTION_ENABLED` (interdit fondateur).

**Ce qu'il manque pour le saut quantique** (par ordre de priorité) :

---

## 1. 🔴 P3-CONSUME — ÉTENDRE (6-10h)
**Fait** : `ADAPTIVE_VOL_GATE.yaml` consomme les seuils adaptatifs (coalition, antagonisme, pliure).
**Reste** : 26 autres principes YAML ne les consomment pas.

**Instruction** : Créer un plan de migration pour les 26 principes. Ne PAS coder — juste un tableau :
- Principe | Champs adaptatifs à ajouter | Effort estimé | Risque

---

## 2. 🟠 BOUCLE D'APPRENTISSAGE (4-6h)
**Fait** : A2 (auto_calibrator) ON, cycle tourne, mais `cognitive_journal` et `learning_proposals` sont vides car WR > 60% sur toutes les sessions.

**Instruction** : Créer un plan pour :
- Abaisser le seuil de proposition de 60% → 50%
- Câbler `cognitive_journal` pour enregistrer même sans proposition
- Activer `learning_proposals` avec le meta-agent

---

## 3. 🟡 DASHBOARD HITL (1h)
**Brief Q3** : `v9_dashboard_web.py` existe mais n'est pas activé.

**Instruction** : Plan d'activation (port, cron, sécurité).

---

## 4. ⚪ ENTRÂINEMENT V9-TRADER-MINI v2 (4h)
**Dataset prêt** (Brief O5). Nouvelle baseline à entraîner sur les 8131 décisions DYNAMIC.

**Instruction** : Plan d'entraînement (ne PAS coder, juste les étapes).

---

## 📋 RÈGLES D'OR
1. **MAX 300 LIGNES** par réponse. Si besoin de plus, découpe en sous-tâches.
2. **ZERO code non demandé** — plans uniquement, sauf instruction explicite.
3. **ZERO storytelling** — faits, chiffres, actions.
4. **Si une tâche est trop large** → propose un découpage et attends.
5. **Ne pas toucher** à `core/v9/order_executor.py`, `V9_EXECUTION_ENABLED`, Phase 10, Phase 12.
