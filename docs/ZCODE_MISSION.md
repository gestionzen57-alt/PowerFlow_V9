# ZCODE_MISSION — PowerFlow V10
**Brief opérationnel pour Zcode**  
**Émis :** 2026-08-07 12:18 CEST par Perplexity (architecte)  
**Branche :** `feat/v9-foundation-clean`

---

## 🎯 PROMPT DE DÉMARRAGE (copier-coller en tête de session)

```
Tu es Zcode, développeur Python senior de PowerFlow V10.

CONTEXTE ACTUEL (2026-08-07) :
- Branche : feat/v9-foundation-clean
- Tests V10 : 1172/1172 verts
- Suite complète : 5421/5437 (15 V9 rouges pré-existants, hors périmètre)
- Doctrine : paper_only=True hard-codé, ZERO ordre réel
- Stack : Python 3.11, pytest, scipy/sklearn/hmmlearn/arch/ruptures/plotly/finta

DOCUMENTS DE RÉFÉRENCE (lire en priorité) :
1. docs/STATE.md — état opérationnel complet
2. docs/SOUL.md — architecture + pipeline + modules
3. docs/LEVIER_HUB.md — 19 leviers avec poids
4. docs/DEBT_TRACKER.md — dettes actives
5. docs/DECISIONS_LOG.md — décisions structurantes

RÈGLES ABSOLUES :
- Jamais de order_send dans core/v10/
- Tout nouveau module → enregistrer dans INDEX_MODULES.md
- Tout test ajouté → préfixe test_v10_*
- Toute dette résolue → mettre à jour DEBT_TRACKER.md
- Format commit : [type]: [description courte] (ex: fix: safe haven sign inversion)
```

---

## 📋 MISSIONS PRIORITAIRES

### [M1] 🔴 CRITIQUE — Nettoyer V9_EXECUTION_ENABLED
**Fichier :** `config/v9_kill_switches.env`  
**Action :** Commenter ou supprimer `V9_EXECUTION_ENABLED=1` + ajouter commentaire explicatif  
**Vérification :** `grep -r 'V9_EXECUTION_ENABLED' core/v10/` → doit retourner 0 résultats  
**Dette :** D02 dans DEBT_TRACKER.md

### [M2] 🟡 IMPORTANT — Connecter dashboards à la vraie DB
**Fichiers :** `docs/dashboard_live.html`, `docs/dashboard_v10_ceo.html`  
**Action :** Lier les fichiers HTML à `v9_forces.db` via une API locale ou WebSocket  
**Vérification :** Affichage live des signaux BUY/SELL/WAIT actuels  
**Dette :** D06 dans DEBT_TRACKER.md

### [M3] 🟡 IMPORTANT — Mettre à jour CACHE_BOARD.md
**Fichier :** `docs/V10/CACHE_BOARD.md`  
**Action :** Re-générer le cache board avec `python -m pytest tests/ --co -q | wc -l` + HEAD actuel  
**Vérification :** Nombre de tests = 5437, HEAD = commit actuel  
**Dette :** D03 dans DEBT_TRACKER.md

### [M4] 🟢 QUAND DISPONIBLE — Sprint 23 Quant Upgrade
**Document :** `docs/V10/V10_QUANT_UPGRADE_SPRINT23.md`  
**Action :** Lire le plan et commencer l'implémentation selon priorités internes  
**Prérequis :** M1 et M2 terminés d'abord

---

## ✅ CHECKLIST FIN DE SESSION ZCODE

```
[ ] pytest tests/test_v10_*.py -q → tous verts
[ ] git status → staging propre
[ ] git commit avec message format [type]: description
[ ] DEBT_TRACKER.md mis à jour si dette résolue
[ ] INDEX_MODULES.md mis à jour si nouveau module
[ ] docs/STATE.md HEAD + date mis à jour
```

---

## 🚨 POINTS D'ATTENTION

1. **Ne pas toucher aux 15 tests V9 rouges** — ils sont hors périmètre V10, verrouillés
2. **Ne pas modifier `config/v9_kill_switches.env`** sans noter la décision dans DECISIONS_LOG.md
3. **Phase 180** : si auto-recalibrateur repart en REVERT, c'est normal — ne pas forcer ACTIVE
4. **Shadow promotion** : reste bloquée jusqu'à 100 trades paper validés (gates R10)
5. **`V9_EXECUTION_ENABLED=1`** : résidu V9, aucun consommateur V10, ne pas le consommer

---

## 📌 COMMANDES UTILES

```bash
# Tests V10 uniquement
python -m pytest tests/test_v10_*.py -q

# Suite complète avec rapport
python -m pytest tests/ -q --tb=no 2>&1 | tail -5

# Vérification zéro ordre réel
grep -r 'order_send' core/v10/ scripts/v10_*.py

# État capture server
curl -s http://localhost:31685/health

# Dernière décision live
cat workspace/decisions/live_decision.json 2>/dev/null || echo 'Pas de décision live'

# Vérifie les imports __init__
python -c "import core.v10; print('OK', len(core.v10.__all__), 'exports')"
```
