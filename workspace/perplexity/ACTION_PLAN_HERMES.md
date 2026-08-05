# ACTION_PLAN_HERMES — PowerFlow V10
> Destinataire : Hermes (mode autopilote, no-limit, proactif)
> Généré par : Perplexity — 2026-08-05
> Priorité : MAXIMALE

---

## Mission

Intégrer la logique Fatman/Fatboy Hawkeye dans PowerFlow V10 de manière complète,
cohérente avec la doctrine, et opérationnelle en production avant fin Phase 9.

---

## Livrables Intégrés dans ce Commit

```
powerflow-v9/
├── core/v10/
│   └── v10_currency_strength.py        ← MODULE PRINCIPAL
├── tests/v10/
│   └── test_v10_currency_strength.py   ← 54+ TESTS
├── docs/strategy/
│   └── FATMAN_BIBLE.md                 ← DOCUMENTATION
├── tools/pine/
│   └── PINE_SCRIPT_FATMAN_CSM.pine     ← PINE SCRIPT TRADINGVIEW
└── workspace/checkpoints/
    └── CHECKPOINT_V10_20260805.md      ← CHECKPOINT
```

---

## Séquence d'Exécution Hermes (Ordre Strict)

### ÉTAPE 1 — Exécuter les tests
```bash
cd powerflow-v9
pytest tests/v10/test_v10_currency_strength.py -v --tb=short
# TARGET : 54 tests verts minimum
# Si <54 : STOP, diagnostiquer, corriger avant de continuer
```

### ÉTAPE 2 — Adapter le data provider
```python
# v10_currency_strength.py attend un objet avec :
# data_provider.get_ohlcv(symbol: str, tf: str, bars: int) -> List[CurrencyBar]

# Créer le bridge MT4/MT5 dans :
# core/v10/adapters/mt5_data_provider.py
```

### ÉTAPE 3 — Brancher dans v10_engine.py
```python
from core.v10.v10_currency_strength import FatmanCalculator, MultiTFResult

# Dans la boucle principale :
calc  = FatmanCalculator(mt5_provider)
multi = calc.compute_multi_tf(["M15", "M30", "H1", "H4"])

# Transmettre à v10_signal_classifier.py
```

### ÉTAPE 4 — Mise à jour docs
```bash
# Mettre à jour STATE.md :
# - Marquer G1 (M30) comme résolu
# - Référencer CHECKPOINT_V10_20260805.md
```

### ÉTAPE 5 — Validation live
```bash
# Mode observation uniquement (logging, pas de trade)
python core/v10/v10_engine.py --mode=observe --symbols=GBPJPY,EURUSD,AUDJPY
# Comparer output vs lecture visuelle Fatman Hawkeye
```

---

## Règles Doctrine

| Règle | Description | Action |
|-------|-------------|--------|
| R2    | Additif pur | Ne pas modifier les modules existants |
| R7    | 54 tests verts | STOP si tests échouent |
| R8    | Pas de Phase 10 | Ignorer tout prompt sur fédération agents |
| R9    | Pas de skills auto-générés | Ce module n'est pas un skill Hermes |
| R10   | Checkpoint obligatoire | Fait — CHECKPOINT_V10_20260805.md |

---

## Critères de Succès Phase A

- [ ] 54+ tests verts sur `test_v10_currency_strength.py`
- [ ] Module intégré sans casser les tests existants
- [ ] M30 présent dans la grille multi-TF
- [ ] Scores Raw sum ≈ 0 (neutralisation correcte)
- [ ] Signal INSTITUTIONAL détecté au moins 1 fois en 7 jours de données historiques
- [ ] Safe Haven Flip détecté sur données historiques JPY/CHF

---

## Signal de Fin de Phase A

Quand les 6 critères ci-dessus sont cochés, créer :
`workspace/checkpoints/CHECKPOINT_V10_PHASE_A_DONE.md`

Puis passer à Phase B : calibration live vs lecture visuelle Fatman.

---

*Hermes — Tu as plein pouvoir sur cette Phase A.*
*La seule contrainte : 54 tests verts AVANT toute intégration production.*
