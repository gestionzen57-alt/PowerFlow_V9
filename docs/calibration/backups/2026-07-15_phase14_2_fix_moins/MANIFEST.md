# Backup MD5 — Phase 14.2 (fix the 5-)
Date : 2026-07-15 05:35 UTC
Chantier : phase14_2_fix_moins
Fichiers backupés :
  - core/v9/learning_offset_applier.py (MD5 vérifié)
  - core/v9/arbiter.py (MD5 vérifié, pas de modif prévue)
Motif : refonte du module learning_offset_applier pour traiter les 5- du
bilan Phase 14 :
  1. Cache in-memory TTL 60s (singleton) → evite lecture DB a chaque
     consolidate().
  2. Bornes asymetriques (haussier [0.85, 1.20], baissier [0.80, 1.10]) →
     magnitude directionnelle (booster haussier plus fort, retenir baissier).
  3. Kill switch par defaut ON (motion CEO §3.6 §1) → activation effective
     immediate (etait OFF par defaut avant, motion CEO distincte requise).
  4. Calibration mapping : helper dans le module pour dry-run.
  5. Tests adaptes.

R8 backup MD5 obligatoire — learning_offset_applier.py est dans la liste
des fichiers a backup avant modif (logique de scoring, mapping numerique).
arbiter.py non touche (singleton deja en place), backup defensif uniquement.
