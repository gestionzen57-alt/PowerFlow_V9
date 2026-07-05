# PowerFlow V9 — Architecture, Processus & Feuille de Route

## 1. Le Principe Fondateur

PowerFlow V9 est construit sur un principe simple : le marche Forex est un systeme de forces.
8 devises (USD, GBP, EUR, JPY, CAD, CHF, AUD, NZD) s affrontent en permanence sur 7 timeframes
(M1, M5, M15, M30, H1, H4, D1). La force relative de chaque devise a chaque instant revele
la structure profonde du marche.

Ce qui fait la valeur de ce systeme, c est 10+ ans d observation humaine qui ont identifie des
patterns recurrents dans ces forces. V9 formalise cette lecture humaine en une chaine cognitive
automatisee.

## 2. Le Processus — Comment ca s articule

### Le flux de donnees

MT4 + Indicateur SDI (proprietaire)
    |  Lecture des buffers (8 devises x 7 TF)
    v
EA V9_Sonde_TF (MQL4)
    |  Formatage + envoi TCP
    v
Capture Server (Python, port 31685)
    |  Stale gate (rejette donnees > 5s)
    |  Anti-doublon (UNIQUE INDEX sur bar_time)
    v
v9_forces.db -> forces_snapshots
    |  Orchestrateur declenche automatiquement
    v
    CHAINE COGNITIVE (5 couches)
    1. SCENE        -> Capture l etat des forces
    2. COMPORTEMENT -> Qualifie l action
    3. FENETRE      -> Evalue l opportunite
    4. EXPLOITABILITE -> Juge si tradable
    5. DECISION (Phase 9) -> principes -> signaux -> action

### Le principe cle : la chaine est additive et filtrante

Chaque couche ajoute de l intelligence ET filtre :
- Forces -> 100% des donnees brutes
- Scenes -> structure l information (qui/quoi)
- Comportements -> ajoute la dynamique (comment)
- Fenetres -> filtre par opportunite (quand)
- Exploitabilite -> filtre par qualite (est-ce tradable)
- Decision -> transforme en action (que faire)

## 3. Les Phases d Evolution

### Phases 1-8 + Orchestrateur (FAIT)

| Phase | Construction | Statut |
|-------|-------------|--------|
| 1 | Formats de donnees | OK |
| 2 | Forces (capture TCP, DB, stale gate) | OK |
| 3 | Scenes (scene_builder, coalitions) | OK |
| 4 | Comportements (behavior_analyzer, 6+ types) | OK |
| 5 | Fenetres (window_gate, 4 statuts) | OK |
| 6 | Exploitabilite (evaluator, 5 niveaux) | OK |
| 7 | Live deploy (EA, capture_server) | OK |
| 8 | Monitoring (dashboard, calibration, replay) | OK |
| + | Orchestrateur live (chaine automatique) | OK |

Resultat : 1194 snapshots -> 1194 scenes -> 1194 comportements -> 1194 fenetres
-> 1194 evaluations, 0 erreurs, 148ms/snapshot.

### Phases restantes

| Phase | Objectif | Priorite |
|-------|----------|----------|
| 9 | Decision et Principes (signaux) | P0 |
| 10 | Federation d agents (multi-analyse) | P1 |
| 11 | Layer MT5 (microstructure ticks) | P2 |
| 12 | Execution d ordres | P2 |
| 13 | Apprentissage et auto-calibration | P3 |

## 4. Les Plus (Points Forts)

### Architecture propre
- Dossier V9 vierge, zero dette technique heritee de V6/V7/V8
- Chaine cognitive unifiee (vs fragmentee en V8)
- 139 tests automatises, 0 erreurs
- Separation nette : capture / chaine / monitoring

### Pipeline live valide
- EA MT4 -> TCP -> Python -> SQLite : flux complet fonctionnel
- Orchestrateur declenche la chaine automatiquement apres chaque snapshot
- Anti-replay : index UNIQUE empeche les doublons de bougies
- Stale gate : donnees perimees rejetees (> 5s)
- Performance : 148ms par snapshot pour la chaine complete

### Outils de monitoring
- Dashboard temps reel (forces, scenes, fenetres, exploitabilite)
- Calibration automatique (distributions, suggestions de seuils)
- Replay (rejouer n importe quelle session, comparer des scenes)
- Regeneration (reconstruire la chaine depuis des snapshots propres)

### Donnees propres
- 1394 snapshots sur 7 timeframes
- 1194 chaines completes (non-stale)
- 0 doublons apres dedup
- DB SQLite simple, portable, pas de serveur externe

### Fonde sur 10+ ans d experience
- Le systeme formalise une lecture humaine eprouvee
- Les principes V8 (27 ACTIVE) sont issus de l observation reelle
- La taxonomie des comportements reflète la grammaire de trading

## 5. Les Moins (Risques et Faiblesses)

### Dependance a l indicateur SDI
- Proprietaire, fonctionne uniquement sur MT4
- Si le broker change ou MT4 disparait, tout le pipeline casse
- Pas de fallback ou d alternative identifiee

### Replay different de Live
- Les donnees replay peuvent generer de faux signaux
- Le stale gate (5s) est adapte au live mais rejette du replay utile
- Solution : marquer replay vs live dans les decisions

### Calibration non encore faite sur donnees live
- Les seuils actuels sont des valeurs par defaut
- v9_calibration.py --analyze peut aider mais necessite des donnees live

### Couverture limitee
- Un seul symbole (GBPUSD) capture pour l instant
- MT5 tick layer absent de V9 (perte de microstructure)
- Pas de gestion d ordres (le systeme observe mais n agit pas)

### Latence cumulee
- 148ms/snapshot en chaine complete
- Ajouter 27 principes (Phase 9) pourrait porter a 200ms+

### Apprentissage absent
- Le systeme ne s ameliore pas seul
- Pas de feedback loop : les decisions ne sont pas evaluees retroactivement
- La calibration est manuelle (via --analyze)

## 6. Les Leviers a Activer

### Levier 1 — Calibration sur donnees live (PRIORITE MAX)
- Laisser le serveur tourner pendant une session de trading reelle
- Collecter les donnees live (market open -> close)
- Lancer v9_calibration.py --analyze sur les vraies donnees
- Ajuster : COALITION_THRESHOLD, ANTAGONISM_THRESHOLD, PLIURE_THRESHOLD,
  STALE_THRESHOLDS_MS
- Reiterer sur plusieurs sessions

### Levier 2 — Migration des principes V8 (Phase 9)
- Les 27 principes ACTIVE de V8 representent 10 ans de savoir trading
- Adapter (pas copier) au modele V9
- Commencer par 5-10 principes les plus importants
- Chaque principe = fonction pure (input -> bool + confidence)

### Levier 3 — Multi-paires
- Activer EURUSD, USDJPY, GBPJPY
- Le systeme est concu pour 8 devises mais ne recoit qu une paire
- Le SceneBuilder doit agreger les forces cross-paires

### Levier 4 — Federation d agents (Phase 10)
- Un agent par couche (scene agent, behavior agent, etc.)
- Un agent arbitre qui consolide
- Un agent risk manager qui filtre les decisions

### Levier 5 — Layer MT5 (Phase 11)
- Lecture des ticks GBPUSD en temps reel
- Detection de micro-patterns (absorption, rejection, acceleration)
- Le MT4 (forces) dicte, le MT5 (ticks) confirme

### Levier 6 — Feedback loop d apprentissage (Phase 13)
- Logger le resultat de chaque signal (gagnant/perdant/neutre)
- Comparer les predictions vs realite
- Ajuster automatiquement les seuils des principes
- Identifier les principes qui performent le mieux

## 7. Timeline Previsionnelle

JUILLET 2026
- Semaine 1 : V9 Phases 1-8 + orchestrateur live, audit V8, calibration live
- Semaine 2 : Phase 9 Decision et Principes, migration 10 principes V8
- Semaine 3 : Calibration live des principes, multi-paires, dashboard --signals
- Semaine 4 : Phase 10 Federation d agents, premier paper-trading

AOUT 2026
- Phase 11 : Layer MT5 (microstructure)
- Phase 12 : Execution d ordres (paper -> reel)
- Phase 13 : Feedback loop d apprentissage

SEPTEMBRE 2026
- Deploiement production
- Trading live avec gestion du risque
- Auto-calibration continue

## 8. Ce Qui Change vs V8

| Aspect | V8 | V9 |
|--------|----|----|
| Architecture | Fragmentee, multi-DB | Unifiee, une DB SQLite |
| Capture | dbfresh, multiple EAs | TCP unifie, un serveur |
| Chaine cognitive | Epars, non connectee | 5 couches sequentielles |
| Orchestration | Manuelle/cron | Automatique (live) |
| Tests | Peu | 139 automatises |
| Monitoring | Absent | Dashboard + calibration + replay |
| Anti-replay | Aucun | Index UNIQUE sur bar_time |
| Dette technique | Enorme (V6/V7/V8) | Zero |

## 9. Pendant l attente (3h credits Claude Code)

1. Le serveur V9 tourne (PID 34292) - laisse-le capturer au market open
2. Tu peux manuellement :
   - python scripts/deploy_v9.py --status
   - python scripts/v9_dashboard.py --watch
   - python scripts/v9_calibration.py --stats
   - python scripts/v9_replay.py --list
3. A l ouverture du marche (dimanche soir 21h ou lundi matin) :
   - Le serveur capturera les forces live automatiquement
   - L orchestrateur declenchera la chaine sur chaque snapshot
   - Lancer v9_calibration.py --analyze sur les vraies donnees
