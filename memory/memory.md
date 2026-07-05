# memory.md — Mémoire persistante PowerFlow V9

## Statut
Mémoire durable. N'y entre que ce qui a été validé (voir `docs/doctrine/MEMORY_POLICY_V9.md`).

## Doctrine stable

### Mission
PowerFlow V9 lit le comportement des forces de marché avant toute logique d'exploitabilité.
Phrase directrice : ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.

### Ordre cognitif officiel
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle.

### Origine
V9 est parti d'un dossier vide le 2026-07-05. Aucun héritage implicite de V8/Hermes.
V8 est une source de migration curée, jamais une base de travail directe.

## Conventions validées
(Aucune convention technique validée à ce stade — fondation en cours.)

## Comportements confirmés
(Vide — aucun comportement de marché encore observé/confronté dans V9.)

## Décisions structurelles
- GitHub = source de vérité absolue.
- Toute migration V8 → V9 passe par audit + classification A/B/C/D.
- Reprise de session obligatoire : CACHE_BOARD.md → STATE.md → dernier checkpoint.
