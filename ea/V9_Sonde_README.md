# V9_Sonde — Déploiement EA MT4 (PowerFlow V9, Phase 2A)

## Rôle

Ces EA sont la couche de capture brute des forces (couche 1 de la chaîne cognitive
V9 : Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution).
Ils lisent l'indicateur SDI et transmettent les valeurs brutes en TCP, sans
aucune logique de trading, aucun ordre, aucune décision.

Deux fichiers :

| Fichier | Rôle | Mode |
|---|---|---|
| `V9_Sonde_TF.mq4` | Candle-close, 1 instance par timeframe | Timer (`OnTimer`) |
| `V9_Sonde_M1.mq4` | M1 dédié, tick/vélocité | Réactif (`OnTick`), pas de timer |

## 1. Compilation dans MetaEditor

1. Ouvrir MetaEditor (F4 depuis MT4, ou lancer directement).
2. Copier `V9_Sonde_TF.mq4` et `V9_Sonde_M1.mq4` dans `MQL4/Experts/` du
   terminal MT4 cible (dossier données du terminal → `MQL4/Experts/`).
3. Ouvrir chaque fichier dans MetaEditor → **Compiler** (F7).
4. Vérifier dans l'onglet "Erreurs" : 0 erreur attendu. Les avertissements sur
   des variables non utilisées sont sans conséquence.
5. Le `.ex4` compilé apparaît à côté du `.mq4`, prêt à glisser sur un chart.

**Prérequis indispensable** : l'indicateur `SDI TCSWL 600+` (fichier `.ex4` +
DLL `Hawkeye2012MT.dll`) doit déjà être installé et fonctionnel sur le
terminal — ces EA ne font que le lire via `iCustom()`, ils ne le remplacent
pas.

## 2. Déploiement — 1 instance par timeframe

Sur le même symbole (ex. GBPUSD), ouvrir un chart par timeframe et y glisser
l'EA correspondant :

| Chart | EA à utiliser | Paramètres recommandés |
|---|---|---|
| GBPUSD **M1** | `V9_Sonde_M1.mq4` | `VelocityWindowMs=5000`, `MinForceDelta=0.05`, `ReplayOnInit=true`, `ReplayBars=600` |
| GBPUSD **M5** | `V9_Sonde_TF.mq4` | `ShiftIndex=1`, `RefreshSeconds=1`, `ReplayOnInit=true`, `ReplayBars=600` |
| GBPUSD **M15** | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD **M30** | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD **H1** | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD **H4** | `V9_Sonde_TF.mq4` | idem M5 |
| GBPUSD **D1** | `V9_Sonde_TF.mq4` | idem M5, `ReplayBars` peut être réduit (ex. 200) |

Chaque instance de `V9_Sonde_TF.mq4` lit **son propre timeframe** via
`Period()` — jamais un timeframe recalculé depuis M1. C'est la correction du
bug V8/V7 documenté ci-dessous (section 5.2).

**Paramètre critique à vérifier avant tout déploiement** : `BrokerUTCOffsetHours`.
Ce doit être le décalage actuel (heure été/hiver comprise) entre l'heure
serveur du broker et l'UTC réel. Exemple : broker en UTC+3 l'été →
`BrokerUTCOffsetHours=3`. Une valeur fausse décale silencieusement tous les
timestamps ISO8601 envoyés — cf. bug V8 section 5.1.

Ne jamais lancer `V9_Sonde_TF.mq4` en mode M1 en production : le paramètre
existe pour compatibilité/secours mais ne calcule pas la vélocité — utiliser
`V9_Sonde_M1.mq4` pour ce rôle.

## 3. Vérifier que l'EA envoie bien les données

1. Activer `DebugPrint=true` temporairement sur l'instance à vérifier.
2. Onglet **Experts** du terminal MT4 → chercher les lignes
   `[V9 Sonde TF] Sent | ...` ou `[V9 Sonde M1] Sent | ...`.
3. Si `ReplayOnInit=true`, un message `[V9 Sonde ... REPLAY] Termine | N shifts
   envoyes` doit apparaître peu après le lancement.
4. Côté réception : le pont Python doit accepter des connexions TCP sur le
   port `31685` en local (`127.0.0.1`) — vérifier ses logs pour confirmer la
   réception des lignes JSON (`bridge_version":"V9_SONDE_TF"` ou
   `"V9_SONDE_M1"`).
5. En l'absence de réception : vérifier qu'aucun pare-feu ne bloque la
   boucle locale, et qu'un seul process écoute sur `31685`.

## 4. Procédure de diagnostic — ordre des buffers SDI (AUD, etc.)

L'audit du code V8 (voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2A.md`)
a montré que l'ordre des buffers `0=AUD, 1=GBP, 2=JPY, 3=USD, 4=CAD, 5=EUR,
6=CHF, 7=NZD` est une propriété vérifiée de l'indicateur **SDI TCSWL 600+**
lui-même (confirmée par la légende de couleurs MT4 et l'outil de diagnostic
V8), pas un bug de lecture de la sonde. Aucune inversion confirmée du buffer
AUD n'a été trouvée dans le code EA V8 : les mentions "AUD inversé" et
"polarité AUD/NZD inversée" trouvées dans les archives V8 concernent soit une
période de données corrompue antérieure (EA legacy qui recalculait sur M1
pour tous les timeframes), soit une interprétation comportementale en aval
(mapping direction de trade, pas la valeur brute). Voir le détail dans le
checkpoint de phase.

Si, malgré tout, un doute apparaît sur le mapping buffer ↔ devise après
déploiement V9 :

1. Glisser l'EA de diagnostic V8 `SDI_Diagnostic_EA.mq4` (ou un équivalent)
   sur le chart concerné pour dumper les 8 buffers bruts dans l'onglet
   Experts.
2. Comparer chaque buffer à la couleur/légende affichée directement par
   l'indicateur SDI sur le chart (clic droit → Propriétés → onglet Niveaux
   ou Couleurs, selon la version de l'indicateur).
3. Si un buffer ne correspond pas à la devise attendue, **ne pas modifier le
   code** : ajuster uniquement l'input correspondant (`BufIdx_AUD`,
   `BufIdx_GBP`, etc.) sur l'instance concernée, dans les propriétés de l'EA
   (onglet Entrées), sans recompilation.
4. Documenter le changement dans un nouveau checkpoint avant de le propager
   aux autres instances.

## 5. Bugs V8 connus et correction appliquée en V9

### 5.1 Décalage horaire broker → UTC non appliqué
V8 stockait des timestamps en heure broker sans conversion, silencieusement
interprétés comme UTC en aval. V9 introduit `BrokerUTCOffsetHours` et calcule
explicitement `timestamp` (ISO8601 UTC) à partir de ce décalage. À vérifier à
chaque changement d'heure été/hiver du broker.

### 5.2 EA HTF lisant PERIOD_M1 pour tous les timeframes
Une ancienne version de l'EA V8 (`V8_HTF`, avant `Sonde_TF`) recalculait le
SDI sur M1 même quand elle prétendait envoyer des données M5/M15/M30/H1 —
toutes les forces "HTF" étaient en réalité des forces M1. `V9_Sonde_TF.mq4`
utilise systématiquement `Period()` (le TF réel du chart) pour chaque appel
`iCustom()` — ce bug ne peut pas se reproduire car il n'y a plus de mode
"multi-TF sur un seul chart" : une instance = un chart = un seul TF.

### 5.3 ShiftIndex mal aligné
V8 a connu une période où `ShiftIndex=0` (bougie en cours) était utilisé sur
des instances candle-close, cassant `is_closed_bar` en aval. V9 fixe
`ShiftIndex=1` par défaut pour `V9_Sonde_TF.mq4` (M5..D1), et sépare
complètement le mode tick (`V9_Sonde_M1.mq4`, toujours `shift=0` en live, mais
`shift` réel et `is_closed_bar=true` pendant le replay des bougies M1
fermées).

### 5.4 Buffer SDI mal lu / sur-capture intra-bar
V8 envoyait parfois plusieurs valeurs différentes pour la même bougie
(l'indicateur recalculant ses buffers intra-bar / repainting), saturant la
base en aval. V9 ne résout pas le repainting de la DLL (hors de portée d'un
EA), mais limite l'impact : anti-duplicate strict sur la sonde M1 (seuil de
variation `MinForceDelta`) et anti-duplicate par signature complète sur la
sonde TF, incluant OHLC + les 8 forces.

## 6. Rappel — ce que ces EA ne font jamais

- Aucun ordre, aucune modification de position, aucune logique de money
  management.
- Aucun calcul de scène, comportement, fenêtre ou exploitabilité — ce travail
  est fait en aval (couches Scènes et suivantes).
- Aucune donnée périmée n'est marquée comme fraîche : c'est au consommateur
  (couche Scènes) d'appliquer le STALE_GATE défini dans `FORMAT_FORCES.md`.
