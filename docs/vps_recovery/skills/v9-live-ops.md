# V9 Live Ops — Opérations pipeline live

> Skill compact. Voir `powerflow-v9-live-ops` pour l'intégral.

## Port canonique

**31685** — port de référence V9 définitif.

## Séquence démarrage

### 1. Attacher les EA (7 charts GBPUSD)

| Chart | EA | Inputs |
|-------|----|--------|
| M1 | `V9_Sonde_M1.mq4` | ServerPort=31685, BrokerUTCOffset=3 |
| M5..D1 | `V9_Sonde_TF.mq4` | ServerPort=31685, ShiftIndex=1 |

### 2. Démarrer le serveur

```bash
python scripts/v9_ops.py start
```

### 3. Vérifier le flux

```bash
python scripts/v9_ops.py log
# Un nouveau snapshot doit apparaître dans les 60s
```

### 4. Valider

```bash
python scripts/v9_ops.py validate-ea
python scripts/v9_ops.py watch
```

## Distinguer live vs replay

| Indice | Live | Replay |
|--------|------|--------|
| Timestamp | Avance (~60s) | Fixe |
| Nouveaux snapshots | Oui | Non |
| Stale sur 10 derniers | ~0-1/10 | Dépend |

## Problèmes connus

| Symptôme | Cause | Solution |
|----------|-------|----------|
| Aucun snapshot après 2 min | EA pas déployé ou mauvais port | Vérifier ServerPort=31685 |
| validate-ea WinError 10013 | Serveur occupe le port | Utiliser `--from-db` |
| ANTAGONIST_NODE 0% | H1 et M5 alignés | Normal — pas un bug |
| Pas de signal/décision | Régime NEUTRE majoritaire | Normal en marché calme |
