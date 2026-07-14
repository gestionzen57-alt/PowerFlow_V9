# Claude Code (Fable) — Setup Git

État actuel de la machine: opérationnel.

## Ce qui a été installé

| Élément | Statut | Détails |
|---------|--------|---------|
| Git 2.54.0 | OK | PATH |
| Node 22.23.1 + npm 10.9.8 | OK | nécessaire pour installer Claude |
| Claude Code CLI 2.1.207 | OK | `C:\Users\Administrateur\AppData\Local\hermes\node\claude.cmd` |
| Compte Anthropic | OK | `gestionzen57@gmail.com — Claude API account` |
| Auth GitHub | OK | Token `ghp_[REDACTED]` dans Windows Credential Manager |

## Pourquoi aucune manip Git supplémentaire n'a été nécessaire

Le remote `https://github.com/gestionzen57-alt/PowerFlow_V9.git` était déjà
accessible via le Windows Credential Manager (`credential.helper=manager`)
avec un token pré-enregistré. Claude Code utilise ce même helper quand il
lance `git` via son tool `Bash`, donc zéro prompt.

Vérification:
```
$ claude -p "Run git status and git remote -v" --allowedTools "Bash(git *)"
Current branch: feat/v9-foundation-clean (up to date with origin, clean)
Remote: https://github.com/gestionzen57-alt/PowerFlow_V9.git
```

## Comment utiliser Claude Code dans ce projet

### Mode non-interactif (one-shot, depuis ce terminal ou tout script)
```bash
cd /c/projet/V9
claude -p "ta tâche ici" --allowedTools "Read,Edit,Bash" --max-turns 10
```

### Mode interactif TUI
```bash
cd /c/projet/V9
claude
# puis taper la tâche à l'invocation; ">" demande confirmation pour chaque
# action, "Shift+Tab" cycle les modes de permission
```

Exemples courants:
- `claude /review` — review du diff en cours
- `claude "/commit msg: fix Y"` — commit + push
- `claude /init` — crée un CLAUDE.md projet
- `claude /security-review` — audit sécurité
- `claude --continue` — reprend la dernière session

### Pour laisser Claude toucher au git en autonomie
Flags utiles:
- `--allowedTools "Bash(git *)"` — autoriser git uniquement
- `--allowedTools "Edit,Write,Bash(git commit *)"` — edits + commit seulement
- `--permission-mode acceptEdits` — accepte les edits auto
- `--dangerously-skip-permissions` — TOUT bypass (CI/sandbox seulement)

Recommended safe: `claude -p "..." --allowedTools "Read,Bash(git status*),Bash(git diff*)"` pour qu'il lise sans toucher.

## Si l'auth expire un jour

Claude:
```
claude auth logout && claude auth login
# navigateur s'ouvre automatiquement, code affiché
```

GitHub token:
```
git credential-manager erase https://github.com
# puis prochain push redemandera username + token
# nouveau token: https://github.com/settings/tokens (scope: repo)
```

## PATH Windows — note

Claude est dans le PATH Hermes (`%LOCALAPPDATA%\hermes\node`), PAS dans
C:\Program Files\nodejs. Les shells git-bash et PowerShell voient les deux
mais cmd pur peut ne voir que Hermes. Si une commande `claude` échoue
introuvablement, ouvrir un nouveau terminal après l'install (refresh PATH).

## Limites connues (skill claude-code)

- Mode interactif REQUIRES tmux pour orchestration automatisée (absent ici).
- `--dangerously-skip-permissions` dialog default = "No, exit", il faut
  naviguer bas + Enter pour accepter (en print mode `-p`, pas de dialog).
- Context window au-dessus 70% → qualité baisse, fais `/compact` régulièrement.
