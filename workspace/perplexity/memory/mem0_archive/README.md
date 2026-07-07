# mem0_archive — Sauvegarde mem0 locale

## Contexte
- Date d'archivage : 2026-07-07
- Décision : désactiver le MCP mem0 d'Hermes (cloud quota épuisé, dépendance externe).
- Source sauvegardée : `D:\hermes\profiles\powerflow\federation_memory.db` (DB SQLite locale, taille 0 octet au moment de l'archive — aucune mémoire persistée côté profile powerflow).
- Remplaçant : mémoire interne V9 → `workspace/perplexity/memory/*.md` + `workspace/perplexity/JOURNAL.md` (versionnés Git, traçables, zéro dépendance externe).

## Convention
- Toute archive mem0 future = `<nom>_<YYYYMMDD>.db` ou `.json`.
- Ne JAMAIS rebrancher mem0 dans `~/.hermes/config.yaml` sans décision explicite consignée dans `DECISIONS_LOG.md`.
- La mémoire V9 est dans `memory.md`, `MEMORY_CANON.md`, `DECISIONS_LOG.md`, `LESSONS_LEARNED.md`, `JOURNAL.md`.

## Restauration (procédure de rollback, à n'utiliser que sur incident grave)
1. Stopper Hermes.
2. `cp workspace/perplexity/memory/mem0_archive/<fichier> /d/hermes/profiles/powerflow/federation_memory.db`
3. Référencer dans `DECISIONS_LOG.md` avec date + raison.
4. Reconfigurer `mcp_servers` dans `config.yaml` (sortie du gel par Søn uniquement).

## Inventaire
- `mem0_federation_memory_20260707.db` (0 octet — coquille vide, archive de principe).