#!/bin/bash
cd /c/projet/V9
PROMPT=$(< /c/projet/V9/logs/nuit_20260720/brief_inline.txt)
exec "/c/Users/Administrateur/AppData/Local/hermes/node/claude" \
  -p "$PROMPT" \
  --model sonnet \
  --permission-mode acceptEdits \
  --output-format text \
  --continue \
  > /c/projet/V9/logs/nuit_20260720/claude_session.log 2>&1
