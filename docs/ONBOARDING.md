# ONBOARDING — PowerFlow V10
**Guide de démarrage rapide pour tout nouvel agent IA**  
**Émis :** 2026-08-07 12:18 CEST

> Ce fichier est conçu pour être lu en < 3 minutes.  
> Il donne le contexte minimum pour être opérationnel immédiatement.

---

## 🚦 Qui es-tu ?

### Tu es Zcode (développeur Python)
→ Lis `ZCODE_MISSION.md` — il contient ton prompt, tes missions et tes commandes.

### Tu es Hermes (pipelines / sprints)
→ Lis `docs/V10/STATE.md` puis reprends le dernier sprint non terminé dans `HERMES_PLAN_V10.md`.

### Tu es un agent généraliste (analyse, conseil)
→ Lis `STATE.md` + `SOUL.md` sections 1-4. C'est suffisant pour contribuer.

### Tu es Perplexity (architecte docs)
→ Lis `README_DOCS.md` + `STATE.md`. Toute modification doc → commit sur `feat/v9-foundation-clean`.

---

## ⚡ Le système en 5 lignes

1. **PowerFlow V10** = algo trading Forex paper-only (jamais d'ordre réel)
2. **Pipeline** : capture → régimes HMM → filtres composites → scoring Hub → décision BUY/SELL/WAIT
3. **21 modules** Python dans `core/v10/`, tous testés (1172/1172 verts)
4. **Branche active** : `feat/v9-foundation-clean` sur GitHub `gestionzen57-alt/PowerFlow_V9`
5. **CEO** : Søn — toute décision finale lui appartient

---

## 🔴 Règles non-négociables

| Règle | Détail |
|---|---|
| Zéro ordre réel | `paper_only=True` partout, 0 `order_send` dans V10 |
| Tests obligatoires | Tout nouveau code → `test_v10_*.py` qui passe |
| Doc synchronisée | Nouveau module → `INDEX_MODULES.md` + `SOUL.md` |
| Dettes documentées | Toute dette → `DEBT_TRACKER.md` |
| Décisions tracées | Toute décision structurante → `DECISIONS_LOG.md` |

---

## 📁 3 fichiers à lire absolument

1. **`STATE.md`** — où en est le système maintenant
2. **`SOUL.md`** — comment ça marche (pipeline + modules + tables)
3. **`DEBT_TRACKER.md`** — ce qui est cassé / en attente

---

## 🛑 Ce qu'il NE FAUT PAS faire

- ❌ Modifier `core/v10/` sans test associé
- ❌ Changer `config/v9_kill_switches.env` sans note dans DECISIONS_LOG.md
- ❌ Forcer la promotion RL SHADOW→ACTIVE (gates non remplies)
- ❌ Créer de nouveaux fichiers docs sans les ajouter dans README_DOCS.md
- ❌ Supposer que `V9_EXECUTION_ENABLED=1` active quelque chose dans V10 (c'est un résidu)

---

## 📞 En cas de doute

- Architecture globale → `SOUL.md`
- Décision passée → `DECISIONS_LOG.md`
- Bug / dette → `DEBT_TRACKER.md`
- Navigation docs → `README_DOCS.md`
- Escalade → CEO (Søn)
