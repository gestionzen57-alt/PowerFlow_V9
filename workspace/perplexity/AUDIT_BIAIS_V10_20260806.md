# 🔍 AUDIT DES BIAIS — PowerFlow V10 (lecture Fatman & compréhension continue)

> **Date :** 2026-08-06 · **HEAD :** `0804001` · **Tests :** 1223/1223
> **Méthode :** vérification à la source (DB + code réel), pas d'assertion non testée.

---

## ✅ BIAIS V10 CORRIGÉS (cette session)

| # | Biais | Découverte | Fix | Statut |
|---|-------|-----------|-----|--------|
| 1 | **Fraîcheur EURUSD** | EURUSD STALE 10j (M5/M30/H1/H4 = 2026-07-27, 827301s) vs autres paires fraîches. Pipeline décidait sur prix périmé. | STALE GATE R10 dans `v10_live_decision.py` + `v10_cortex_live.py` (seuil par TF : M30=2h, H1=4h, H4=8h) → WAIT si périmé | ✅ |
| 2 | **Comptage WR** | `query_coherence` faisait `COUNT(*)` sur toutes les lignes mais `SUM(is_win)` sur les résolues → WR dilué (rotation_leadership "7%" = artefact, réalité 78%) | `WHERE is_win IS NOT NULL` | ✅ |

---

## ✅ BIAIS V9 CORRIGÉS DANS V10 (vérifiés)

| Biais V9 | V10 | Vérif |
|----------|-----|-------|
| NZD 99.8% (654k/655k sur NZD seul) | NZD dans CURRENCIES + DIRECT_PAIRS + force_nzd en DB | ✅ code + DB |
| Timeframe M15 75% | V10 décide sur M30/H1/H4 | ✅ `TIMEFRAMES_DEFAULT` |
| Directionnel short 46/39% | Direction dérivée du régime (TRENDING_DOWN→short, sinon long) | ✅ `v10_live_decision.py:158-166` |
| Proxy vélocité inerte (volume absent) | GARCH/EWMA vol + delta_flow (absorption/stacked) | ✅ modules actifs |

---

## 🟡 BIAIS RÉSIDUELS DÉTECTÉS (documentés honnêtement, non masqués)

| Biais | Impact | Note |
|-------|--------|------|
| **Volume M5/M15 4×** | La cohérence globale est noyée par les TF rapides (18k résolus sur M1/M5/M15 vs 4.5k sur M30/H1/H4). WR reste stable (maintien 0.79→0.81) mais bascule chute (0.75→0.66, n=94) | Le registre garde l'historique V9 pour référence, V10 décide sur M30/H1/H4. À filtrer par TF pour la cohérence de décision. |
| **NZD nominal vs réel** | NZDUSD a 0 snapshots (colonne force_nzd existe mais pas la paire). Toute paire NZD = fail-open (WAIT). Support nominal, pas réel. | Pas de crash (R6), mais couverture NZD non effective. |
| **D1 WR 0.61** | Échantillon faible (n=67) → WR non fiable sur D1 | Petit échantillon, pas de conclusion. |

---

## ✅ VERIFIÉ SAIN (pas de biais)

- **Distribution des forces** : moyennes ~49, 0% null, aucune devise dominante
- **Direction** : haussière 12103 vs baissière 12209 = 50/50 équilibré
- **Safe haven Fatboy** : forces équilibrées → False (pas de faux positif), JPY/CHF forts → True (correct). Fix ZCode `885a851` présent (ligne 278-279).
- **Seuils** : GAP_STANDARD=35, GAP_INSTITUTION=48, SIGMA=12/28 (constants, calibrés via bayesian_recalibrator par paire×TF, 18 paires×TF dans v10_active_thresholds.json)
- **Overrides runtime** : non appliqués au démarrage live (pas de biais d'override actif)
- **Encodage** : UTF-8 partout (pas de biais d'encodage)
- **WR par paire** : stable (0.77-0.80) — pas de biais de paire

---

## 🎯 SYNTHÈSE

**2 biais V10 réels corrigés** (fraîcheur + comptage) — les deux faussaient le WR et le drift.
**1 biais résiduel à surveiller** (volume M5/M15 4× dans la cohérence) — recommandé de filtrer la cohérence par TF de décision.
**1 limitation de couverture** (NZD nominal sans données) — documentée, pas de crash.

**Leçon centrale :** le pire biais était opérationnel (décider sur du prix périmé en croyant que c'est du live), pas dans la logique de lecture. Le stale gate est maintenant un garde-fou permanent.

---

*Fin de l'audit des biais. Chaque conclusion est vérifiée à la source (DB + code réel). R9 : aucune fabrication.*
