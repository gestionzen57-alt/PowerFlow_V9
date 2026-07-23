# Processus d'étude comportementale V9

> **Objectif** : structurer l'analyse microstructure pour tirer profit des
> recherches et améliorer la prédiction du système.

## 1. Cycle d'étude comportementale

Le processus d'étude suit 4 étapes, chacune tracée dans ce document :

```
OBSERVER → ANALYSER → CORRIGER → VALIDER
```

### 1.1 Observer

Query DB 7j sur les champs microstructure de `forces_snapshots` :

| Champ | Rôle | Filtre possible |
|---|---|---|
| vitesse | Signal leading (momentum naissant) | vit=0 → pas de mouvement |
| croisement_detecte | Croisement de forces | vit<0.01 → croisement mort |
| recroisement_detecte | Cross-back = inversion | =1 → invalider signal |
| rejet_repulsion_detecte | Faux croisement | =1 → bloquer |
| compression_extension_etat | Squeeze avant expansion | neutre → pas d'énergie |
| cvd_delta | Pression buy/sell | opposé → divergence |
| spread_points | Liquidité | >5 → slippage |
| direction | Sens du mouvement | aligne avec croisement |

Query DB sur `behaviors` :

| Champ | Rôle |
|---|---|
| qualification | Type de comportement (maintien, rotation, tension, lutte) |
| comportement_precedent | Transition depuis l'état précédent |
| sens_transition | Direction de la transition |
| point_de_rupture_detecte | Rupture structurelle |

### 1.2 Analyser

Décomposer par TF (M5 = bruit, M15 = structurel, H1 = tendance) :
- Comportement AVANT le croisement (3 snapshots)
- Comportement AU moment du croisement
- Comportement APRES le croisement (3 snapshots)

Identifier 3 patterns :
1. **CONFIRMATION** : direction maintenue, vitesse persiste, compression présente
2. **REJET** : direction s'inverse, vitesse retombe, pas de compression
3. **MORT** : tout reste neutre, vitesse 0, pas d'énergie

### 1.3 Corriger

Appliquer les corrections dans l'ordre d'impact :
1. Filtres bloquants dans `_behavioral_filter` (signal_generator.py)
2. Boosts de confiance pour les patterns gagnants
3. Nouveaux principes YAML (conditions comportementales)
4. Ajustements config (scales, blacklists, régimes)

### 1.4 Valider

- Tests pytest (signal_generator + decision_logger + dynamic_risk)
- Pipeline restart + vérification live (signaux post-restart)
- Suivi 7j : mesurer WR et pips des nouveaux signaux filtrés vs non filtrés

## 2. Étude réalisée 22-23/07 — 7 axes

### Axe 1 — Vitesse
- vit=0 : 2319 snaps, direction neutre dominante
- vit>0.05 : 63 snaps, TOUJOURS haussier (biais NO_BAISSIERE)
- **Filtre** : croisement à vit<0.01 = mort → bloqué

### Axe 2 — Compression/Extension
- neutre : 2449 snaps, 4.8% de croisements
- compression : 158 snaps, 19.6% de croisements (4x plus)
- **Boost** : compression/extension présente → +5 confiance

### Axe 3 — CVD
- CVD>0 : 48% haussier, 31% baissier
- CVD<0 : 31% haussier, 49% baissier
- **Boost** : CVD aligné avec direction → +5 confiance

### Axe 4 — Rejet/Répulsion
- 286 rejets sur 7j (champ existant non utilisé)
- **Filtre** : rejet_repulsion_detecte=1 → bloquer

### Axe 5 — Recroisement
- EURUSD M5 : 71% de cross-backs
- **Filtre** : recroisement_detecte=1 → bloquer

### Axe 6 — Spread
- 5% des snapshots ont spread>5
- **Filtre** : spread>5 → bloquer

### Axe 7 — Transitions de comportement
- rotation_leadership → rotation_leadership (n=4115) = instabilité
- maintien → maintien (n=3324) = tendance stable
- **Filtre** : rotation_leadership → bloquer

## 3. Filtres et boosts implémentés

### Filtres bloquants (_behavioral_filter)

| Filtre | Condition | Action | Source |
|---|---|---|---|
| Rejet | rejet_repulsion_detecte=1 | Bloquer | Axe 4 |
| Recroisement | recroisement_detecte=1 | Bloquer | Axe 5 |
| Spread large | spread_points>5 | Bloquer | Axe 6 |
| Croisement mort | croisement + vit<0.01 | Bloquer | Axe 1 |
| Rotation leadership | qualification="rotation_leadership" | Bloquer | Axe 7 |

### Boosts de confiance (signal_generator)

| Boost | Condition | Gain | Plafond |
|---|---|---|---|
| Compression/extension | comp_state in (compression, extension) | +5 | 70 |
| CVD aligné | cvd_delta même signe que direction | +5 | 70 |
| Croisement validé | croisement + vit>0.05 | +5 | 70 |

### Nouveau principe

| Principe | Conditions | Action |
|---|---|---|
| GRAMMAR_CROISEMENT_CONFIRMATION | croisement + vit>0.05 + pas de rejet + pas de recroisement | +10 confiance |

## 4. Pistes d'amélioration — Pôle étude

### Court terme (prochaines sessions)

1. **Confirmation différée** : attendre 2-3 snapshots après croisement
   avant de générer le signal (deferred trigger). Le système trade
   actuellement l'événement, pas la confirmation.

2. **Analyse spread par paire** : USDJPY a un spread structurellement
   plus large. Adapter le seuil par paire au lieu de 5 global.

3. **Filtre tick_volume** : volume = 0 ou très bas → pas de liquidité.
   Ajouter un seuil minimum de tick_volume par snapshot.

4. **Corrélation CVD × prix** : détecter les divergences CVD (prix monte
   mais CVD descend = distribution, signal baissier latent).

### Moyen terme (T+7j à T+30j)

5. **Machine learning sur transitions** : utiliser les transitions de
   comportement (behaviors.comportement_precedent → qualification) pour
   prédire la probabilité de réussite par pattern de transition.

6. **Heatmap comportementale** : croiser (qualification × session × régime)
   pour identifier les niches structurelles (ex: "maintien" en ASIE
   EXTENSION = edge, "rotation" en LONDRES NEUTRE = bruit).

7. **Velocity profile** : modéliser la courbe de vitesse typique avant
   un mouvement directionnel. La vitesse accélère-t-elle graduellement
   ou y a-t-il un seuil de déclenchement ?

8. **Compression duration** : combien de temps la compression dure-t-elle
   avant l'expansion ? Un snapshot en compression ne suffit pas — il faut
   savoir si la compression dure depuis 3+ snapshots (vraie squeeze)
   ou si c'est ponctuel.

### Long terme (T+30j+)

9. **Order flow reconstruction** : utiliser CVD + tick_volume + spread
   pour reconstruire un proxy de order flow et détecter absorption
   (large volume sans mouvement de prix = limit orders absorbent).

10. **Behavioral Bayesian** : intégrer les patterns comportementaux
    comme contextes additionnels dans le Bayesian calibrator (au lieu
    de juste principle × symbol × tf × session × regime, ajouter
    qualification × compression_state × cvd_direction).

11. **Regime detection v2** : le régime NEUTRE actuel est binaire.
    Un régime "NEUTRE avec compression naissante" n'est pas la même
    chose qu'un "NEUTRE profond sans énergie". Affiner la détection.

12. **Multi-paire correlation** : quand GBPUSD et EURUSD croisent
    haussier simultanément, c'est un signal USD-negative fort.
    Détecter les coalitions cross-paire en temps réel.

## 5. Comment reproduire une étude

```bash
# 1. Query DB 7j
PYTHONPATH=. .venv/Scripts/python.exe -c "
import sqlite3
c = sqlite3.connect('file:data/v9_forces.db?mode=ro', uri=True)
# ... queries ...
"

# 2. Analyser avant/après croisement
# Voir skill v9-croisement-confirmation § DB Queries

# 3. Appliquer les filtres dans _behavioral_filter
# Voir skill v9-behavioral-analysis § Implementation

# 4. Tester
PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_signal_generator.py -q

# 5. Restart pipeline
netstat -ano | grep 31685.*LISTENING
taskkill /PID <pid> /F
PYTHONPATH=. .venv/Scripts/python.exe -m core.v9.capture_server  # background

# 6. Suivre 7j
python scripts/v9_dashboard_today.py
```

## 6. Références

- Skills : `v9-behavioral-analysis`, `v9-croisement-confirmation`, `v9-recalibration-loop`
- DB : `forces_snapshots` (46 champs), `behaviors` (25 champs), `decisions` (27 champs)
- Code : `signal_generator.py:_behavioral_filter()`, `signal_generator.py` boosts
- YAML : `core/v9/principles/GRAMMAR_CROISEMENT_CONFIRMATION.yaml`
- Backup MD5 : `backups/fix_calibration_20260722/`