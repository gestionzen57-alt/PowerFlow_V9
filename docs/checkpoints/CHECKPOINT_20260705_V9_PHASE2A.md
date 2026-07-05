# CHECKPOINT — PowerFlow V9 — Phase 2A — EA MT4 (rebuild propre)

## Date
2026-07-05

## Branche
`feat/v9-phase2-ea-mt4`

## Contexte
Phase 1 (6 formats cognitifs) terminée et fusionnée sur `feat/v9-foundation-clean`.
La Phase 2 démarre par la couche Forces côté capture réelle : reconstruction de
la sonde EA MT4 qui alimente le pipeline, en s'appuyant sur la structure du
repo V8 (`D:\Projet\V8`) comme référence d'audit, jamais comme base de code
reprise telle quelle.

## Mission
Reconstruire un EA MT4 propre pour V9 (from scratch), aligné sur
`docs/architecture/formats/FORMAT_FORCES.md`, en corrigeant les bugs connus de
V8 plutôt qu'en les hérités implicitement.

## Livrables

- `ea/V9_Sonde_TF.mq4` — sonde candle-close, 1 instance par timeframe
  (M5, M15, M30, H1, H4, D1 en usage normal ; M1 supporté en secours).
  Timer (`OnTimer`), `ShiftIndex=1` par défaut, replay historique configurable
  (`ReplayOnInit`, `ReplayBars`), anti-duplicate par signature complète
  (OHLC + 8 forces), JSON aligné `schema_version`/`snapshot_id`/`timestamp`
  ISO8601 UTC/`source` de FORMAT_FORCES.md.
- `ea/V9_Sonde_M1.mq4` — sonde M1 dédiée, mode tick/vélocité. Réactive
  (`OnTick`, aucun timer), fenêtre glissante de 5000 ms (ring buffer),
  `nb_ticks_fenetre` et `vitesse_tick_<devise>` calculés par devise via
  `GetTickCount()`, anti-duplicate strict par seuil de variation minimum
  (`MinForceDelta`). Replay historique séparé (bougies M1 fermées, pas des
  ticks simulés).
- `ea/V9_Sonde_README.md` — procédure de compilation MetaEditor, déploiement
  par timeframe, vérification de réception, procédure de diagnostic des
  buffers SDI, et rappel des bugs V8 corrigés par construction.

## Audit du code V8 — ce qui a été vérifié avant d'écrire le nouveau code

Fichiers audités : `ea/EA_PowerFlow_V8_Sonde_TF.mq4`,
`ea/EA_PowerFlow_V8_UniversalSonde.mq4`, `ea/EA_PowerFlow_V7_UniversalSonde_FINAL.mq4`,
`ea/SDI_Diagnostic_EA.mq4`, ainsi que les archives d'audit :
`docs/checkpoints/AUDIT_SHIFT_INDEX_20260619.md`,
`docs/checkpoints/AUDIT_CAPTURE_FORCES_20260619.md`,
`docs/checkpoints/CHECKPOINT_2026_06_24_ARCHITECTURE_FORCES.md`,
`ea/PROCEDURE_SHIFTINDEX_2026_06_30.md`,
`briefs/BUG_RAPPORT_INVERSION_DELTA_FORCE_2026_06_29.md`,
`core/pf_force_state_CALIBRE.md`, `docs/COMPORTEMENTS_LECTURE_MULTITF_20260617.md`
(tous dans `D:\Projet\V8`).

### Finding 1 — Ordre des buffers SDI / "AUD inversé"
Aucune inversion confirmée du **buffer AUD au niveau de l'EA**. L'ordre
`0=AUD, 1=GBP, 2=JPY, 3=USD, 4=CAD, 5=EUR, 6=CHF, 7=NZD` est documenté comme
une propriété vérifiée de l'indicateur `SDI TCSWL 600+` lui-même (couleurs des
buffers confirmées dans `CHECKPOINT_2026_06_24_ARCHITECTURE_FORCES.md`, section
1). Les mentions "AUD inversé" trouvées (`COMPORTEMENTS_LECTURE_MULTITF_20260617.md`)
renvoient à une période de données corrompue par l'EA legacy `V8_HTF` (qui
recalculait le SDI sur M1 pour tous les timeframes — voir Finding 2), pas à un
bug de mapping buffer↔devise. La "polarité AUD/NZD inversée" documentée dans
`pf_force_state_CALIBRE.md` est un finding de calibration **comportementale**
(mapping direction de trade GBPUSD en aval), sans rapport avec la lecture
brute des buffers par l'EA. La piste "USD inversé (`100 - force_usd`)"
mentionnée dans `COMPORTEMENTS_LECTURE_MULTITF_20260617.md` a été vérifiée et
infirmée dans `AUDIT_CAPTURE_FORCES_20260619.md` (aucune trace dans le code
actif, l'historique git ou les stash).

**Décision V9** : conserver l'ordre de lecture des buffers tel que vérifié
(pas de swap arbitraire, qui introduirait un bug réel à la place d'un bug
supposé), mais le rendre **configurable par input** (`BufIdx_AUD`, `BufIdx_GBP`,
etc.) pour permettre une correction sans recompilation si un futur diagnostic
le justifie. Procédure de re-vérification documentée dans
`V9_Sonde_README.md` section 4.

### Finding 2 — EA HTF hardcodant PERIOD_M1 (bug confirmé, déjà fixé côté V8, reconduit en V9)
L'EA `V8_UniversalSonde` en mode HTF appelait autrefois `ReadSDI(g_symbol,
PERIOD_M1, ...)` au lieu du vrai timeframe — toutes les forces "M5/M15/M30/H1"
stockées étaient en réalité des forces M1. Corrigé dans le V8 actuel
(`ReadSDI(sym, tf, sh, ...)`). V9 élimine structurellement ce risque : il n'y
a plus de mode "un chart lit plusieurs TF" — une instance `V9_Sonde_TF.mq4` =
un chart = `Period()` = le seul TF lu.

### Finding 3 — ShiftIndex mal aligné
V8 a connu un épisode où `ShiftIndex=0` était utilisé par défaut sur une
instance candle-close (`ea/PROCEDURE_SHIFTINDEX_2026_06_30.md`), cassant
`is_closed_bar` en aval pendant plusieurs jours. V9 fixe `ShiftIndex=1` par
défaut pour `V9_Sonde_TF.mq4` et sépare structurellement le mode tick (M1,
toujours `shift=0` en live) du mode candle-close (M5..D1, `shift=1`) dans deux
fichiers distincts — élimine le risque de confusion de configuration.

### Finding 4 — Décalage horaire broker vs UTC
Non documenté comme bug applicatif en V8 mais source de confusion récurrente
(`CHECKPOINT_2026_06_24_ARCHITECTURE_FORCES.md` section 2 : broker Tickmill
UTC+3, jamais converti). FORMAT_FORCES.md V9 exige un `timestamp` ISO8601 UTC
explicite : V9 introduit l'input `BrokerUTCOffsetHours` et une fonction de
conversion dédiée (`ToISO8601UTC`), documentée comme paramètre critique à
vérifier à chaque changement d'heure été/hiver du broker.

### Finding 5 — Sur-capture intra-bar / repainting DLL
`AUDIT_CAPTURE_FORCES_20260619.md` : la DLL `Hawkeye2012MT.dll` recalcule ses
buffers intra-bar, produisant plusieurs valeurs différentes pour la même
bougie côté capture Python (hors de portée d'un fix EA). V9 n'élimine pas ce
comportement DLL, mais limite son impact côté sonde : anti-duplicate par
signature complète (TF) et par seuil de variation minimum (M1).

## Validation
- Les 3 fichiers livrés existent dans `ea/`.
- Code MQ4 relu ligne à ligne pour cohérence de signatures de fonctions
  (paramètres/arguments alignés), absence de syntaxe MQL5-only non supportée,
  `#property strict` présent sur les deux EA.
- Ordre des buffers SDI vérifié par audit du code + doc V8 et documenté
  explicitement dans le code (commentaires) et le README (section 4).
- JSON aligné sur les champs requis par la mission et cohérent avec
  `FORMAT_FORCES.md` (schema_version, timestamp ISO8601 UTC, source, 8 devises
  au nommage canonique `force_<devise>`).
- M1 strictement séparé du candle-close : deux fichiers distincts, deux modes
  d'exécution (`OnTick` vs `OnTimer`), pas de partage de logique de vélocité.

## Prochaine étape
Merger `feat/v9-phase2-ea-mt4`, puis engager la Phase 2B — bridge DB : serveur
TCP Python côté réception (port 31685), stockage, et lecteur réel des forces
consommé par la future couche Scènes.
