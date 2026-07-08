# Diagnostic ANTAGONIST_NODE — D:\Projet\V9\data\v9_forces.db

- **Date** : généré par `diagnose_antagonist_node.py`
- **Verdict** : **INERT_MARKET**
- **Raison** : H1 et M5 strictement corrélés sur la période (257 snapshots, 0 divergent). ANTAGONIST_NODE attend des fenêtres d'antagonisme (notes YAML : terrain optimal = NEWS_SHOCK, divergence H1 vs M5 amplifiée par choc liquidité).
- **Snapshots analysés** : 257
- **Conditions satisfaites (toutes)** : 0
- **Divergences H1 vs M5** : 0
- **N conditions YAML** : 5

## Distribution couples (h1_dir, m5_dir)

| h1_dir | m5_dir | count |
|---|---|---|
| 'HAUSSIERE' | 'HAUSSIERE' | 256 |
| 'NEUTRE' | 'HAUSSIERE' | 1 |

## Échantillons

| snapshot | h1_dir | m5_dir | h1_state | m5_state |
|---|---|---|---|---|
| `22800-025572` | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' |
| `19201-025571` | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' |
| `15601-025570` | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' |
| `12001-025569` | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' |
| `08401-025568` | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' | 'HAUSSIERE' |

## Évaluation des conditions (1 snapshot)

| idx | field | op | target | ctx value | result |
|---|---|---|---|---|---|
| 0 | h1_state | not_in | ['NEUTRAL', None] | 'HAUSSIERE' | True |
| 1 | m5_state | not_in | ['NEUTRAL', None] | 'HAUSSIERE' | True |
| 2 | h1_dir | != | NONE | 'HAUSSIERE' | True |
| 3 | m5_dir | != | NONE | 'HAUSSIERE' | True |
| 4 | h1_dir | != | m5_dir | 'HAUSSIERE' | False |
