# Kelly Fractionnel — sizing bayésien-borné (Axe 1.2 / J2)

> **Statut** : câblé, **OFF par défaut** (kill switch `V9_KELLY_FRACTIONAL_ENABLED=0`, R25' strict).
> Promotion ACTIVE = motion CEO explicite séparée. Livré 2026-07-21.
> **Modules** : `core/v9/v9_kelly_sizing.py` (câblage), `core/v9/bayesian_calibrator.py` (moteur J1),
> intégration `core/v9/trade_engine.py` (section 3a4).

## 1. Pourquoi

Le sizing V9 était soit statique (lots fixes), soit issu du `DynamicRiskManager`
(cycles/phases → SL/TP), sans **composante probabiliste** fondée sur le WR réel.

La confiance déclarée par l'arbiter est **anti-calibrée** — mesure du 2026-07-21 :

| Fenêtre | Brier score | Lecture |
|---|---|---|
| 7 j | **0.4467** | ≫ 0.25 (aléatoire) → pire que le hasard |

Table de fiabilité (décile de confiance déclarée → WR observé) :

| conf déclarée | n | WR observé | gap |
|---|---|---|---|
| 0.6–0.7 | 132 | 0.523 | −0.144 |
| 0.7–0.8 | 63 | 0.508 | −0.220 |
| 0.8–0.9 | 13 | 0.615 | −0.211 |
| 0.9–1.0 | 430 | 0.470 | **−0.528** |

**Conséquence** : sizer proportionnellement à la confiance déclarée est
**anti-Kelly** — on met le plus gros risque (décile 0.9-1.0) là où l'edge est
en réalité inexistant (WR 0.47). Le posterior **Beta(α,β)** agrège les WIN/LOSS
*réels* par contexte : c'est la seule base de sizing probabiliste honnête.

## 2. Modèle mathématique

### 2.1 Posterior Beta-Binomial (rappel J1)

Pour un contexte `(principle, symbol, timeframe, session, regime)`, prior
uniforme `Beta(1,1)` :

```
α = 1 + wins,  β = 1 + losses,  n = wins + losses
E[WR] = α / (α + β)
```

`P(WR > 0.5) = 1 − CDF_Beta(0.5; α, β)` mesure la crédibilité de l'edge.

### 2.2 Kelly fractionnel → multiplicateur borné

Kelly complet (mise optimale en fraction de capital), avec `p = E[WR]`,
`q = 1−p`, `b = rr` (reward:risk estimé TP/SL) :

```
f_full = (p · b − q) / b
```

Comme `f_full < 1` toujours, on ne borne pas `f_full` directement mais on le
cartographie en **multiplicateur de taille** : `fraction` (quart-Kelly = 0.25)
est la référence de Kelly-complet mappée sur 1.0× (taille de base). D'où :

```
kelly_multiplier = clamp( f_full / fraction , floor , cap )
                 = clamp( f_full / 0.25 , 0.3 , 2.0 )
```

Un edge égal à `fraction` de Kelly complet ⇒ taille de base (×1.0). Un edge
plus fort dépasse 1.0 (jusqu'au cap 2.0) ; un edge marginal descend vers le
floor 0.3. (Divergence assumée vs la formule littérale de la spec — cf.
`bayesian_calibrator.kelly_fraction` docstring et DECISIONS_LOG §J1.)

### 2.3 Composition multiplicative

Le multiplicateur **ne remplace jamais** le sizing existant, il le module :

```
final_size = base_size × dynamic_risk_multiplier × kelly_multiplier
```

où `base_size` est le `position_size` déjà décidé par `paper_risk_manager`
(puis éventuellement réduit par le `PortfolioRiskManager` corrélation et
plafonné par le `CVaR ceiling`). Kelly s'applique **en dernier**, additif (R2).

## 3. Workflow

```
context_key = (principle, symbol, timeframe, session, regime)
      │  build_context_key(db_path, snapshot_id)  ← lecture ro decisions
      ▼
BayesianCalibrator.fit_context(context_key) → BetaPosterior(α,β,n)
      │
      ├── n < MIN_N (20) ...................... → multiplier = 1.0 (neutre)
      ├── P(WR>0.5) < MIN_PROB_ABOVE (0.6) .... → multiplier = 1.0 (neutre)
      ├── f_full ≤ 0 (pas d'edge positif) ..... → multiplier = 1.0 (neutre)
      └── sinon → kelly_fraction() → clamp[0.3, 2.0] → multiplier appliqué
      ▼
apply_kelly_to_sizing(base_size, engine, context_key, dynamic_risk_multiplier)
      ▼
final_size = base × dynamic × kelly     (kelly = 1.0 si kill switch OFF)
```

## 4. Câblage `trade_engine` (non-intrusif)

- **Import défensif** (`KELLY_AVAILABLE`) : un import cassé rend le hook inerte.
- **Propriété lazy** `TradeEngine.kelly_engine` : construit `BayesianCalibrator`
  + `KellySizingEngine` à la première utilisation (aucun coût si non utilisé).
- **Propriété d'observabilité** `TradeEngine.kelly_sizing_report` : snapshot
  lecture seule du multiplicateur pour le dernier snapshot traité ; renvoie
  `None` si câblage indisponible / kill switch OFF / aucun snapshot traité.
- **Hook de sizing** (`process()` section 3a4) : gardé par
  `V9_KELLY_FRACTIONAL_ENABLED`. Si ON, multiplie `risk_result["position_size"]`
  par le multiplicateur Kelly et journalise (`[KELLY] mult=... size a→b`). Le
  flux `prepare → enter → manage → exit` reste inchangé (R2 strict).

Aucune modification du `DynamicRiskManager` (composition, pas remplacement),
du `config.py` (seuils calibrés intacts), ni de la DB (lecture seule stricte).

## 5. Garde-fous (R6 défensif)

| Garde-fou | Valeur | Effet |
|---|---|---|
| Kill switch OFF | défaut | Module inert (`kelly_multiplier = 1.0`) |
| `MIN_N` | 20 | Pas de sizing sans 20+ observations → neutre |
| `MIN_PROB_ABOVE` | 0.6 | Edge non confirmé → neutre |
| `floor` / `cap` | 0.3 / 2.0 | Multiplicateur strictement borné |
| Fail-safe | — | DB inaccessible / scipy off / erreur → log ERROR + neutre |
| Lecture seule | `mode=ro` | Aucune écriture, aucune migration |

## 6. Métriques cibles (conditions d'évaluation avant promotion)

- Sharpe > 1.0
- Drawdown < 200 pips
- WR > 70 %

## 7. Conditions d'activation

Promotion ACTIVE (`V9_KELLY_FRACTIONAL_ENABLED=1`) = **motion CEO explicite**
(R25' strict). Le câblage étant multiplicatif et borné, l'activation est
réversible sans régression : remettre le switch à `0` restaure exactement le
sizing antérieur (`final = base × dynamic`, kelly neutralisé à 1.0).

## 8. Smoke / vérification

```bash
python scripts/v9_kelly_sizing_smoke.py --n 8 --seed 7
```

Affiche, pour N contextes réels tirés de la DB live, le posterior, le Kelly
brut/fractionnel, le multiplicateur et son application ; vérifie que tous les
multiplicateurs restent dans `[0.3, 2.0]`. Exemple observé (2026-07-21) : min
0.533 / moyenne 1.143 / max 2.000 sur 8 contextes — bornes respectées.
