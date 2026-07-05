# MEMORY_POLICY_V9.md

## But
Construire une mémoire propre, utile, non toxique, non héritée passivement.

## Principe cardinal
On ne migre pas une mémoire.
On migre uniquement des connaissances validées, reformulées et reclassées.

## Types de mémoire

### 1. memory.md
Mémoire persistante du système.
Contient :
- doctrine stable
- conventions validées
- comportements confirmés
- définitions durables
- décisions structurelles

### 2. memory_temp.md
Journal de travail temporaire.
Contient :
- hypothèses
- essais
- ambiguïtés
- pistes
- erreurs
- décisions de session

### 3. exchange.md
Mémoire de coordination inter-agents.
Contient :
- demandes
- statuts
- handoffs
- retours
- arbitrages

### 4. CACHE_BOARD.md
Mémoire ultra-compacte de reprise de session.
Doit rester lisible en 2 minutes.

## Interdits mémoire
- Ne pas copier de mémoire V8/Hermes sans audit.
- Ne pas stocker dans memory.md une hypothèse non validée.
- Ne pas laisser memory_temp.md devenir une décharge permanente.
- Ne pas mélanger doctrine, expérimentation et runtime.

## Cycle de vie
1. Une idée naît dans memory_temp.md
2. Elle est confrontée aux données / replay / doctrine
3. Si validée, elle entre dans memory.md
4. Sinon, elle est archivée ou supprimée du temp après journalisation

## Politique de reprise
À chaque session :
1. lire CACHE_BOARD.md
2. lire STATE.md
3. lire dernier checkpoint
4. lire uniquement la doctrine utile
5. ne pas recharger toute l'histoire du projet si inutile

## Test de qualité mémoire
Une mémoire est saine si :
- elle réduit les répétitions
- elle n'impose pas de vieux biais
- elle conserve la perception centrale
- elle aide à décider sans enfermer