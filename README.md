# PowerFlow V9

## Nature du projet

PowerFlow V9 est une refondation cognitive propre de PowerFlow.
Ce n'est pas une extension de V8. C'est un nouveau socle, construit sur une doctrine explicite,
posé dans un dossier vide, sans héritage implicite de mémoire, de skills ou de conventions passées.

V8 reste une source de migration curée : chaque élément repris doit être audité et classé
(voir `docs/doctrine/MIGRATION_POLICY_V9.md`). V8 n'est jamais la base de travail directe de V9.

## Mission

PowerFlow V9 est un système de lecture comportementale des forces de marché.
Sa mission première n'est pas de produire un trade, mais de reconnaître fidèlement
la dynamique réelle des forces telle qu'elle est perçue par l'opérateur.

Phrase directrice : **ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.**

## Ordre cognitif officiel

1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

Aucune couche aval ne peut court-circuiter une couche amont.

## Arborescence

```
PowerFlow_V9/
├── README.md                  — ce fichier
├── AGENT.md                   — document racine, rôle et routing du système
├── docs/
│   ├── PERPLEXITY.md          — rôle Perplexity dans l'orchestration
│   ├── STATE.md               — état exécutif du chantier
│   ├── CACHE_BOARD.md         — tableau de bord compact de reprise
│   ├── checkpoints/           — jalons structurants
│   ├── doctrine/              — charte cognitive, politiques mémoire/orchestration/migration
│   ├── architecture/          — roadmap d'implémentation
│   └── lexicon/               — vocabulaire natif V9
├── memory/                    — memory.md / memory_temp.md / exchange.md
├── assets/                    — loop / reading / windows / scenes / behaviors
├── skills/                    — scene-reader, behavior-reader, window-evaluator, replay-confronter, doctrine-keeper
├── agents/                    — orchestrator, force-reader, scene-builder, behavior-analyst, window-gate, reviewer
├── runtime/                   — state / reports / logs / snapshots
├── scripts/
└── archive/
```

## Reprise de session

En début de session, lire dans l'ordre :
1. `docs/CACHE_BOARD.md`
2. `docs/STATE.md`
3. le dernier fichier de `docs/checkpoints/`
4. uniquement les documents de doctrine utiles à la tâche en cours

## Interdits fondateurs

- Ne pas hériter implicitement de V8, de Hermes legacy, ou de workflows non audités.
- Ne pas introduire d'outillage (RAG, scoring, agentisation, multi-IA) avant d'avoir localisé
  sa place exacte dans la chaîne cognitive.
- Ne pas confondre lecture et décision, comportement et signal, scène et trade.

Voir `AGENT.md` et `docs/doctrine/CHARTE_COGNITIVE_V9.md` pour le détail complet.
