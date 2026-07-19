# Axe 7 — Audit des tokens Telegram exposés dans git

> **Audit edgefund V9 — Axe 7/8** · OPUS Claude Code · 2026-07-19 · lecture seule.
> ⚠️ **Sécurité** — action CEO requise (rotation BotFather).

## Constat : 4 tokens de bots exposés

Recherche `git log --all -p | grep -E '[0-9]{9,10}:AA...'` :

| Token (préfixe) | Présent dans HEAD (fichiers trackés) | Historique |
|---|---|---|
| `8656365767:AAHU…` | `DECISIONS_LOG.md` | oui |
| `8790798269:AAETtvT…` | `docs/STATE.md`, `PROMPT_OPUS_AUDIT_EDGEFUND…`, `DECISIONS_LOG.md` | oui |
| `8932306765:AAEP7_UF…` | **7 fichiers** : `JOURNAL_PHASES.md`, `CHECKPOINT_2026-07-13…`, `logs/telegram_report_20260713_status.txt`, `POINT_GENERAL_20260713_48H.md`, `ROADMAP_CLAUDE_CODE.md`, `DECISIONS_LOG.md`, `LESSONS_LEARNED.md` | oui |
| `8948930478:AAGptDt…` | `config/telegram.json.bak.20260717`, `DECISIONS_LOG.md` | oui |

**Le commit `d1edf86` (« rédige token exposé ») n'a caviardé qu'une occurrence.** Les 4
tokens restent lisibles en clair dans des fichiers **trackés du HEAD actuel** (donc aussi
dans tout l'historique). Un token dans git = **compromis définitivement**, quelle que soit
la suite.

### Bonne nouvelle : les secrets runtime sont protégés

- `.env` et `config/telegram.json` sont **non trackés** (couverts par `.gitignore`) ✅.
- **Exception** : `config/telegram.json.bak.20260717` **est tracké** et contient le token
  `8948930478` en clair → à désindexer (`git rm --cached`), comme l'avait fait `c6ff200`
  pour un autre `.bak`.

## Remédiation — priorité et recommandation chiffrée

### P0 — ROTATION (seule vraie remédiation) · action CEO · ~5 min

Les 4 tokens sont publics dans git : **il faut les révoquer**, pas les cacher. Via
@BotFather → `/revoke` (ou `/token`) pour chacun des 4 bots. Après rotation, les tokens
exposés deviennent **inertes** — le risque tombe à zéro **indépendamment** de tout nettoyage
d'historique. **C'est l'action unique qui compte.**

### P1 — Housekeeping HEAD · 1 commit · faible risque

Une fois les tokens révoqués (donc inertes) :
1. `git rm --cached config/telegram.json.bak.20260717` (fichier `.bak` porteur de token).
2. Caviarder les 4 tokens dans les ~10 docs trackés (`REDACTED_TOKEN_<n>`) pour que
   `git grep` soit propre à l'avenir.
→ Rend le HEAD sain sans toucher à l'historique.

### P2 — Réécriture d'historique (`git filter-repo`) · **NON recommandé**

| Pour | Contre |
|---|---|
| Purge les tokens de tout l'historique | Réécrit **tous** les SHA → casse le remote (force-push), tous les clones, la traçabilité R14 |
| — | Nécessite motion CEO R28 explicite + fenêtre de coordination multi-IA |
| — | **Inutile après rotation** : les tokens inertes n'ont plus de valeur |

**Recommandation** : **NE PAS** réécrire l'historique. Le ratio risque/bénéfice est
défavorable dès lors que les tokens sont révoqués. Réserver `filter-repo` au seul scénario
où le repo deviendrait **public** (là, purge obligatoire, sous motion CEO dédiée).

## Décision proposée

1. **Maintenant (CEO)** : révoquer les 4 tokens BotFather. ← *seule action bloquante*
2. **Ensuite (1 commit)** : `git rm --cached` du `.bak` + caviardage HEAD.
3. **Ne pas** faire `filter-repo` (sauf passage public futur).

## Score Axe 7

| Critère | Cible | Résultat |
|---|---|---|
| Liste exhaustive | tokens + commits | ✅ 4 tokens localisés (HEAD + historique) |
| Recommandation chiffrée | filter-repo ou non | ✅ **rotation P0 + housekeeping P1, PAS de filter-repo** |
