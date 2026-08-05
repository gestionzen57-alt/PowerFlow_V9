# DECISIONS LOG — PowerFlow V10
_Historique des décisions structurantes_

---

## 2026-08-05 — Session Perplexity (11h37 CEST)

### DEC-2026-08-05-001
**Décision** : Intégration du TF M30 dans la grille officielle V10  
**Contexte** : Manquant dans V9 et absent des modules v10_force/structure/context  
**Raison** : Le Fatman utilise M30 comme TF de confirmation intermédiaire entre M15 et H1  
**Impact** : TASK-002 créée — injection M30 après TASK-001 validée  
**Statut** : ✅ Décidé — en attente d'exécution

### DEC-2026-08-05-002
**Décision** : `v10_currency_strength.py` est le module #1 prioritaire absolu  
**Contexte** : Compréhension Fatman confirmée — le signal Fatman est fondé sur les scores de forces devises  
**Raison** : Sans scores devises corrects, tous les autres modules (force, structure, context) produisent du bruit directionnel  
**Impact** : TASK-001 bloquante — rien d'autre ne démarre avant 15 tests verts  
**Statut** : ✅ Décidé

### DEC-2026-08-05-003
**Décision** : Plan Hermes edge fund quantique rédigé et poussé sur le repo  
**Contexte** : Demande de plan d'action complet no-limit pour Hermes en mode autopilote  
**Raison** : Centraliser la vision V10 dans un document unique lisible par Hermes sans contexte de session  
**Impact** : `docs/HERMES_PLAN_V10.md` créé — référence principale pour les sessions Claude Code  
**Statut** : ✅ Décidé

### DEC-2026-08-05-004
**Décision** : Tous les fichiers workspace/perplexity poussés directement via GitHub MCP (sans terminal local)  
**Contexte** : Utilisateur ne voit pas les fichiers Perplexity sur le repo  
**Raison** : Push direct API GitHub = source de vérité garantie sans dépendance au filesystem local  
**Statut** : ✅ Exécuté

---

## 2026-08-04 — Session Perplexity

### DEC-2026-08-04-001
**Décision** : Reverse-engineering du Fatman validé  
**Contexte** : Source code indicateur partagé par l'utilisateur  
**Raison** : Compréhension exacte de la logique calcul — scores devises pondérés multi-TF  
**Impact** : Architecture V10 réorientée vers currency_strength en priorité  
**Statut** : ✅ Décidé

### DEC-2026-08-04-002
**Décision** : 6 setups edge fund identifiés avec levier, WR et R:R  
**Contexte** : Analyse signaux Fatman × structure marché  
**Raison** : Formaliser les edges tradables avant de coder le signal engine  
**Statut** : ✅ Décidé — documenté dans HERMES_PLAN_V10.md
