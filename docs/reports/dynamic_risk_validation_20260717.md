# Validation DynamicRiskManager (SHADOW) — 2026-07-17

> Session Opus, dernière fenêtre avant reset. Objectif : statuer sur la
> promotion SHADOW→ACTIVE du DynamicRiskManager (Phase 13.3), et lever ou
> confirmer le risque look-ahead de l'ExitSimulator documenté à la clôture
> de semaine.
>
> **Lecture seule.** Aucune modification de `core/v9/*`. Le module reste SHADOW.

## Verdict

| Axe | Résultat |
|---|---|
| Robustesse moteur | ✅ **Prêt** — 2000/2000 décisions rejouées en `source=dynamic`, 0 fallback, 0 crash |
| Câblage `trade_engine` (étape 4b) | ✅ Additif, try/except, non bloquant (R2/R6) — kill switch en place |
| Tests | ✅ 1556 passed / 1 skipped (Windows SIGTERM) |
| **Promotion ACTIVE** | 🔴 **NON — pas cette session.** Impact économique majeur + vérité terrain (WR) non fiable |

**Conclusion** : le DynamicRiskManager est **techniquement mûr et sûr en SHADOW**,
mais son passage APPLY est **prématuré**. Ce n'est pas un défaut de code — c'est
que la métrique qui devrait valider son gain (le WR de résolution) est
structurellement trompeuse (voir §3). On ne promeut pas un moteur de risque sur
une mesure de P&L qu'on sait biaisée.

## 1. Robustesse (rejeu SHADOW sur 2000 décisions résolues)

Rejeu de `DynamicRiskManager.evaluate()` sur les 2000 décisions résolues les
plus récentes disposant d'un `contexte_complet` (baseline statique de comparaison
= TP 8 / SL 15).

```
source=dynamic : 2000 (100.0%)   source=fallback : 0   erreurs contexte : 0
```

Le moteur ne tombe jamais en fallback sur données réelles et ne lève jamais.
La détection de phase produit une décision exploitable à chaque snapshot.

### Distribution des phases détectées (WR réel du trade sous la phase)

| Phase | n | WR réel |
|---|---|---|
| distribution | 1702 | 68.7 % |
| cassure | 148 | 64.9 % |
| trend | 72 | 68.1 % |
| retour | 61 | 70.5 % |
| accumulation | 12 | 75.0 % |
| **climax** | **5** | **20.0 %** |

- ✅ Le **garde-fou climax** est cohérent : la phase isole bien les pires trades
  (WR 20 %), et le profil `allow_new_position=False` les éviterait.
- ⚠️ **Biais de distribution** : 85 % des snapshots classés `distribution`.
  **→ DIAGNOSTIQUÉ, voir §1bis.**

## 1bis. Diagnostic du biais « distribution » (85 %) — RÉSOLU

> Outillé par `scripts/v9_dashboard_risk.py` (lecture seule, rejeu du
> `DynamicRiskManager` sur les contextes réels). Reproduit exactement le
> chiffre : rejeu des 2000 résolues → **85.0 % distribution**.

### Chaîne causale (3 couches)

1. **Amont — sémantique de `culmination`.** `behavior_analyzer._determine_phase`
   (l. 480-497) étiquette `culmination` **toute qualification qui persiste
   ≥3 barres à intensité non décroissante** (`streak[-1] >= max(streak[:-1])`).
   C'est de la **PERSISTANCE**, pas de l'épuisement au sens analyse technique.
   Sur l'ensemble des comportements : **62 057 / 72 665 = 85.4 % `culmination`**.
2. **Classifieur — mapping mono-signal.** `phase_classifier` règle #4 mappe
   `behavior_phase == "culmination"` (seul) → `DISTRIBUTION`. Choix **délibéré
   et testé** (`test_detect_distribution_culmination`), pas un bug accidentel.
3. **Propagation.** culmination (85 %) → distribution (85 %), à condition
   qu'aucune règle prioritaire ne pré-empte.

### Découverte majeure — le 85 % est NON-STATIONNAIRE (artefact d'échantillon)

Le « 85 % » provient de l'**échantillon résolu** (`is_win` non nul), dominé par
un ancien lot ~GBPUSD où `point_de_rupture` est rare. Sur les décisions
**récentes** (représentatives de ce que verra le moteur en live), la donne
s'inverse — `point_de_rupture` ≈ **59 %** → **CASSURE** (priorité > distribution)
pré-empte :

| Phase | Fenêtre RÉSOLUE (validation) | Fenêtre RÉCENTE (live) |
|---|---|---|
| distribution | **95.1 %** (89.9 % WR) | 15.9 % |
| cassure | 2.5 % | **58.9 %** |
| trend | 1.2 % | 11.3 % |
| accumulation | 0.1 % | 5.8 % |
| retour / climax | ~1 % | 4.8 % / 3.3 % |

### Verdict

- Le 85 % **n'est PAS un marché réellement en distribution**, ni un crash du
  moteur : c'est un mislabel sémantique amont (`culmination`=persistance),
  fidèlement propagé, et **spécifique à l'échantillon résolu**.
- Il **ne bloque pas l'activation** : en live, le moteur produit un mix
  équilibré, mené par CASSURE.
- **Nouveau point de vigilance pour APPLY** : la part de **CASSURE** (profil
  agressif SL18/TP22, trailing) suit le taux de `point_de_rupture`. C'est
  désormais le profil dominant probable en live — à surveiller sous APPLY,
  bien plus que la question « distribution ».
- **Correctif éventuel = AMONT** (`behavior_analyzer`, définition de
  `culmination`), dans un cycle dédié avec sa propre validation — **pas** un
  patch du classifieur sous pression (casserait les tests, invaliderait
  l'historique `is_win`). Non retenu pour lundi.

### Impact SL/TP (dynamique − statique 8/15)

```
ΔTP moyen : +7.99 pips  (le TP dynamique double ~ 8 → 16)
ΔSL moyen : −2.05 pips  (stops resserrés)
RR moyen  : 1.21 (dynamique)  vs  0.53 (statique)
```

L'activation **restructure l'économie des trades** (RR ×2.3). Ce n'est pas un
ajustement marginal → l'esprit de R2 (additif, ne pas casser ce qui marche)
impose une validation P&L solide *avant* APPLY, pas après.

### Garde-fou vs trades réellement pris

74 trades pris auraient été bloqués par le DRM (climax + sessions non tradables).
WR de ces trades bloqués : **66.2 %** — élevé. Sur la métrique actuelle, le
blocage coûterait des gagnants. Mais cette lecture est **confondée par le biais
WR** (§3), donc non concluante en l'état.

## 2. Câblage & doctrine

- Hook `trade_engine.py` étape 4b (l. 287-310) : purement additif, `result["dynamic_risk"]`
  attaché au diagnostic, le `tp_pips/sl_pips` réel **inchangé**. try/except (R6),
  kill switch `_dynamic_risk_enabled()` (défaut ON en SHADOW).
- R18 respecté : détection code pur, aucun LLM.
- Clamp de sécurité présent (SL 6-25, TP 4-40).

## 3. Look-ahead ExitSimulator — **disculpé** (résultat majeur)

Le risque documenté à la clôture de semaine (« WR 84.9 % suspect, TP<SL,
look-ahead possible ») a été **testé et écarté** :

### 3a. Fenêtre temporelle du résolveur — propre

`scripts/v9_resolve_decision_auto.py::_fetch_future_mids` :
`WHERE timestamp > start AND timestamp <= end` — le `>` **strict** exclut la
barre d'entrée, l'horizon plafonne la fenêtre. Pas de fuite temporelle.

### 3b. Résolution intrabar — n'explique pas le WR

Re-résolution d'un échantillon de 800 décisions (TP 8/SL 15, horizon 6 h) en
**détection intrabar** (high/low par barre, hypothèse pessimiste SL-first sur
ambiguïté) vs la méthode `mid`-only actuelle :

```
mid-only  : WR 89.8 %   (win 641 / loss 73)
intrabar  : WR 89.2 %   (win 647 / loss 78)
ΔWR = +0.5 pt   |   barres ambiguës (TP & SL même barre) : 0
```

**0 barre où TP et SL sont touchés dans la même barre.** L'ajout du high/low ne
déplace le WR que de 0.5 pt → le WR élevé **n'est pas** un artefact intrabar ni
un look-ahead.

### 3c. Vraie cause : géométrie des barrières + métrique trompeuse

Le WR haut est une propriété **mathématique** de la config TP proche (8) / SL
loin (15) sur un horizon de 6 h : le prix touche presque toujours +8 avant −15.
WR ~90 %, mais **RR = 0.53** — chaque perte efface ~2 gains. C'est exactement
pourquoi le batch frais draine à **56.8 % WR / +0.1 pip ≈ breakeven** (cf. audit
clôture semaine) : la métrique fiable est l'**espérance (pips/trade)**, pas le WR.

**Conséquence pour lundi** : le chantier « fix look-ahead ExitSimulator » est
**réorienté**. Il n'y a pas de look-ahead à corriger. Le vrai travail est de
piloter le système sur l'espérance et le RR, pas sur le WR — et c'est
précisément ce que le DynamicRiskManager adresse (RR 0.53 → 1.21). L'ironie :
le DRM est probablement la bonne réponse, mais on ne peut pas le prouver avec la
métrique WR actuelle.

## 4. Reprise lundi — état vérifié

| Point | État |
|---|---|
| Capture live (vendredi 09:12 UTC) | ✅ serveur actif port 31685, dernier snapshot 0.8 min, 5 paires fraîches |
| Heartbeat | ✅ `--check` OK (timestamp UTC, fix clôture semaine confirmé) |
| **MT4 relance dimanche 22h UTC** | 🔴 **risque confirmé** — ni `v9_market_open.py` ni `v9_bootstrap.py` ne lancent MT4 (aucune ref subprocess/terminal). GUI liée à la session interactive → **vérification manuelle obligatoire** à la réouverture |

## 5. Recommandations (ordre)

1. **Ne pas promouvoir** le DynamicRiskManager en APPLY tant que le pilotage
   n'est pas fait sur l'espérance/RR (décision CEO).
2. **Lundi, priorité 1** : vérifier MT4 lancé après tout reboot week-end.
3. Investiguer le **biais de distribution** (85 % des phases) du
   `MarketCycleDetector` avant tout APPLY.
4. Abandonner le chantier « fix look-ahead » (non-bug) ; le remplacer par un
   tableau de bord **espérance/RR** par phase.

---

_Scripts de validation (scratchpad, non versionnés) : `validate_drm.py`,
`lookahead_probe.py`. Reproductibles à la demande._
