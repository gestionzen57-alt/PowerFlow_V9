# Checklist diagnostic rapide — PowerFlow V9

> Quand quelque chose ne va pas, exécuter ces vérifications dans l'ordre.

## 1. Pipeline DOWN

```bash
# Le serveur de capture tourne-t-il ?
python scripts/v9_ops.py status

# Le port 31685 est-il occupé ?
netstat -ano | findstr :31685

# Y a-t-il des logs récents ?
tail -20 logs/v9_capture.log

# Redémarrage
python scripts/v9_ops.py boot
```

## 2. Pas de données récentes

```bash
# Dernier snapshot reçu ?
python scripts/v9_ops.py status

# L'EA MT4 est-il actif sur les charts ?
# Vérifier le smiley vert en bas à droite de chaque chart MT4

# Le port correspond-il entre l'EA et config.py ?
# EA : ServerPort=31685, config.py : LISTEN_PORT=31685
```

## 3. Tests qui échouent

```bash
# Voir les échecs en détail
python -m pytest tests/ -v --tb=long 2>&1 | head -100

# Vérifier si c'est une régression ou un xfail connu
grep -r "xfail" tests/ | head -10
```

## 4. DB corrompue ou verrouillée

```bash
# Vérifier l'intégrité
python -c "import sqlite3; c=sqlite3.connect('data/v9_forces.db'); c.execute('PRAGMA integrity_check'); print(c.fetchone())"

# Taille
ls -lh data/v9_forces.db

# Backup + VACUUM
python scripts/v9_db_hygiene.py --dry-run
```

## 5. Erreur Python / import

```bash
# Vérifier les imports
python -c "from core.v9.config import *; print('OK')"

# Vérifier la version Python
python --version  # doit être >= 3.11
```

## 6. Git problématique

```bash
# Conflit ?
git status

# Divergence avec remote ?
git log --oneline -5 origin/feat/v9-foundation-clean
git log --oneline -5 feat/v9-foundation-clean

# Réparation
git pull --rebase origin feat/v9-foundation-clean
```

## 7. Erreur connue — divergence calendrier DST

Si le dashboard affiche "Marché : FERMÉ" mais que le live tourne :
- C'est l'anomalie DST US documentée (calendrier canonique UTC fixe 22h vs EDT 21h)
- Voir `docs/deployment/V9_AUTOMATION_RUNBOOK.md` §Anomalie connue
- Pas un bug, pas d'action corrective
