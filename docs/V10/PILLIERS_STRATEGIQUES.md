# PILIERS STRATÉGIQUES — La synthèse du projet V10 (13/08 19:30 UTC)

> **Le système est un chasseur, pas un notaire.**
> Il ne valide pas le passé — il reconnaît la qualité dans l'instant.
> Libre. Vif. Sans friction. Protégé par R10.

---

## 🏛️ LE PARADIGME (Søn 13/08)

```
❌ ANCIEN : NOTAIRE
   Block/Allow binaire → freeze config → 30 trades → gate → GO
   Friction. Paralysie. Le marché bouge, le système attend.

✅ ACTUEL : CHASSEUR
   Score de qualité 0-10 → action immédiate selon la qualité
   Vitesse. Lucidité. Le marché bouge, le système agit.
```

---

## 🎯 LE SCORE DE QUALITÉ (le cœur du chasseur)

```
SCORE [0-10] — ce que le système "voit" instantanément

  📊 Pilier 7 — Forces dans les zones (0-3)     ✅ Codé
     +3 : zone dynamique extrême (p10/p90)
     +2 : zone haute/basse (p25/p75)
     +1 : zone moyenne en mouvement

  📈 Pilier 1 — Cinématique (-4 à +2)           ✅ Codé
     +2 : accélération favorable
     +1 : extension saine
      0 : neutre
     -2 : exhaustion (pic → retombée)
     -2 : divergence (force ≠ prix)

  🔗 Pilier 2 — Confluence TF (-1 à +2)         ✅ Codé
     +2 : 4/4 TF alignés (M5+M15+M30+H1)
     +1 : 3/4 alignés
      0 : 2/4
     -1 : conflit majoritaire

  🔄 Pilier 6 — Phase du cycle (0-2)            ⬜ Placeholder (brainstorming)
     +2 : naissance, +1 : expansion, 0 : maturité, -2 : épuisement

  🌐 Pilier 3 — Coalition (0-1)                 ⬜ Placeholder (brainstorming)
     +1 : alignée, 0 : neutre, -1 : rompue

VERDICT INSTANTANÉ (pas de gate, pas d'attente) :
  ≥ 7  → 🟢 EXPLOITABLE — sizing renforcé (×1.0-1.5)
  4-6  → 🟡 SURVEILLER — sizing réduit (×0.5-0.8)
  < 4  → 🔴 BRUIT — ignorer (×0)
```

---

## 📋 LES 7 PILIERS DE LA LECTURE DE MARCHÉ

| # | Pilier | Description | Codé ? | Module |
|---|---|---|---|---|
| 1 | **Cinématique** | La courbe avant la valeur : pics, exhaustion, divergence | ✅ | `v10_cinematics.py` |
| 2 | **Imbrication TF** | M5+M15+M30+H1, sizing modulé par confluence | ✅ | `v10_confluence_tf.py` |
| 3 | **Coalition multidevise** | Leader/follower, rupture risk-on, safe haven | ⬜ | `v10_coalition_devises.py` (squelette) |
| 4 | **Personnalité de devise** | Tempo, véracité, comportement par devise | ⬜ | `v10_personality_devise.py` (squelette) |
| 5 | **Fractalité temporelle** | 1min → H4, TF de lisibilité par devise | ⬜ | `v10_fractalite_tf.py` (squelette) |
| 6 | **Cycles Fatman** | Naissance → expansion → maturité → épuisement | ⬜ | `v10_cycles_fatman.py` (squelette) |
| 7 | **Forces par TF** | Échelles propres, zones par percentile, croisement + double test + propagation/répulsion | 🔶 | `v10_forces_par_tf.py` (calibration OK) |

**Module unificateur** : `v10_quality_score.py` — agrège les 5 piliers en un score 0-10.

---

## 🏗️ L'ARCHITECTURE (7 couches)

```
COUCHE 0 — MARCHÉ (DB forces_snapshots, chaque TF son échelle)
   ↓
COUCHE 1 — LECTURE PAR TF (Pilier 7) → zones par percentile
   ↓
COUCHE 2 — CASCADE TEMPORELLE (Pilier 5+2) → confluence TF
   ↓
COUCHE 3 — CYCLES FATMAN (Pilier 6) → phase du cycle
   ↓
COUCHE 4 — PERSONNALITÉ DE DEVISE (Pilier 4) → calibrage par devise
   ↓
COUCHE 5 — COALITION MULTIDEVISE (Pilier 3) → contexte global
   ↓
COUCHE 6 — CINÉMATIQUE (Pilier 1) → pics, divergence, exhaustion
   ↓
COUCHE 7 — SCORE DE QUALITÉ + DÉCISION + GARDE-FOUS R10
   Score 0-10 → EXPLOITABLE / SURVEILLER / BRUIT
   Circuit breaker DD + news guard + correlation guard
```

---

## 🎯 L'EDGE OVERLAP (le terrain de chasse)

```
Fenêtre   : 12-16 UTC (OVERLAP Londres + NY)
Paires    : EURUSD, USDCHF, AUDUSD
TF        : M15 (barres fermées)
Signal    : |delta_forces| ≥ 25 → BUY si delta>0, SELL sinon
Filtre    : score de qualité 0-10 (cinématique + confluence + zones)
TP/SL     : TP=2xATR, SL=1xATR, hold max 4 barres M15
Sizing    : modulé par le score (🟢 ×1.0-1.5, 🟡 ×0.5-0.8, 🔴 ×0)
R10       : zéro ordre réel (broker non connecté)
```

---

## 📜 LA MÉTHODOLOGIE (contrat multi-IA)

> **Le brainstorming de Søn est la source de vérité. L'implémentation suit,
> ne précède pas.**

- **Piste A** : Brainstorming → reformuler, documenter, NE PAS coder
- **Piste B** : Implémentation → uniquement les piliers stables et validés
- **Piste C** : Test → benchmark sur données NON utilisées pour le choix

Voir `docs/V10/METHODOLOGIE_INJECTION.md` pour le contrat complet.

---

## 🛡️ LES GARDE-FOUS (R10)

| Garde-fou | Rôle | Statut |
|---|---|---|
| Circuit breaker DD | Halt si DD journalier/hebdo/mensuel dépassé | ✅ Branché |
| News guard | Blocage fenêtre news (NFP/CPI/FOMC) | ✅ Branché |
| Correlation guard | Blocage sur-exposition paires corrélées | ✅ Branché |
| Risk shield | DD max 10%, position max 2%, levier max 5x | ✅ Branché |
| Kill switch CEO | Override ultime | ✅ Actif |

---

## 📊 L'ÉTAT (13/08 19:30)

| Élément | État |
|---|---|
| Tests V10 | ✅ 1380/1380 verts |
| Score de qualité | ✅ Codé et testé (🟢 EXPLOITABLE sur pic, 🔴 BRUIT sur exhaustion) |
| Edge OVERLAP | ✅ Config figée (delta≥25, TP=2x/SL=1x, cinématique, confluence) |
| Suivi trades shadow | ✅ Open/resolve/track record |
| Cron actif | `v10-edge-overlap-shadow` (*/20 lun-ven) |
| Brainstorming | 🔶 7 piliers extraits, 2 codés, 5 en attente |
| R10 | ✅ Zéro ordre réel |

---

## 🧠 LA DOCTRINE (Søn)

> *"Chaque jour est unique. Il n'y a pas de loi, mais une façon d'exploiter
> et comprendre la réalité du marché."*

> *"Ne m'enferme pas dans un laboratoire stérile. Trouve les choses
> exploitables. La qualité. Pas de friction."*

> *"La valeur des forces est propre au time frame. Les valeurs ne sont
> pas agrégées. C'est pour cela que la lecture temporelle est complexe."*

---

## 📚 DOCUMENTS PIVOTS (à lire au démarrage session)

1. `docs/V10/METHODOLOGIE_INJECTION.md` — le contrat multi-IA (**EN PREMIER**)
2. `docs/V10/PILLIERS_STRATEGIQUES.md` — ce fichier (synthèse)
3. `docs/V10/POINT_GENERAL_INSTITUTIONNEL.md` — tableau de bord détaillé
4. `docs/V10/LECTURE_FORCES_PAR_TIMEFRAME.md` — Pilier 7
5. `docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` — Pilier 6+7
6. `docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` — Pilier 4+5+6
7. `docs/V10/BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` — Pilier 1+2+3

---

> **Le système V10 est un chasseur.**
> Il reconnaît la qualité quand elle se présente.
> Il agit sans friction, protégé par R10.
> La lecture de Søn guide chaque couche. Le score de qualité unifie.