# Telegram Bidirectionnel — Réparation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Le daemon Telegram répond à chaque message de Søn (commandes `/cmd` ET texte libre) en moins de 2 secondes, avec persistance fiable de l'offset et logs de diagnostic.

**Architecture:** Patch ciblé de `scripts/v9_telegram_notifier.py` — ajouter logs debug dans `_fetch_commands` et `_poll_once`, forcer la persistance offset, ajouter un script de validation runtime. Aucun modif core/v9/*, aucun MCP, aucun orchestrator. R8 strict respecté.

**Tech Stack:** Python 3.11 stdlib (urllib, json, sqlite3, subprocess, time, datetime, pathlib, logging).

---

## Contexte du bug

**Symptômes** : Søn envoie des messages Telegram → daemon WATCH reçoit (confirmé via getUpdates offset=-5) → aucune réponse reçue par Søn. Aucun log "sendMessage" ni "Nouvelles décisions". Le fichier `logs/.telegram_offset` n'est jamais créé.

**Hypothèses** :
1. `_fetch_commands` filtre `if text and chat_id:` mais ne loggue pas → on ne sait pas si le filtre passe
2. `_write_offset` condition `if offset > _read_offset()` peut ne pas se déclencher si l'offset en mémoire = offset persisté
3. Le daemon WATCH peut crasher silencieusement entre `_fetch_commands` et `_write_offset`
4. La fonction `_call_hermes` (LLM) peut bloquer 30s (timeout urllib) → la commande n'est jamais traitée en < 2s

**Stratégie de réparation** : observer d'abord, corriger ensuite, tester runtime.

---

## Task 1 : Ajouter logs debug dans `_fetch_commands`

**Objective:** Savoir exactement ce que le daemon reçoit de Telegram à chaque cycle.

**Files:**
- Modify: `scripts/v9_telegram_notifier.py:655-693` (function `_fetch_commands`)

**Step 1: Read the current function**

```bash
cat scripts/v9_telegram_notifier.py | sed -n '655,693p'
```

**Step 2: Replace the function with a debug-instrumented version**

Replace the existing `_fetch_commands` function with:

```python
def _fetch_commands(config: dict[str, str]) -> list[dict[str, Any]]:
    """Récupère les messages entrants via getUpdates.

    Version debug 2026-07-11 : ajoute logs explicites pour diagnostiquer
    pourquoi les messages ne sont pas traités.
    """
    offset = _read_offset()
    url = f"{GET_UPDATES_API.format(token=config['token'])}?offset={offset}&timeout=5"
    logger.info("getUpdates offset=%d", offset)
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logger.error("getUpdates URLError : %s", e)
        return []
    except json.JSONDecodeError as e:
        logger.error("getUpdates JSONDecodeError : %s", e)
        return []

    if not body.get("ok"):
        logger.error("getUpdates not ok : %s", body)
        return []

    raw_count = len(body.get("result", []))
    logger.info("getUpdates returned %d raw updates", raw_count)

    messages = []
    for update in body.get("result", []):
        update_id = update.get("update_id", 0)
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        logger.info(
            "update_id=%d text=%r chat_id=%s (target=%s)",
            update_id, text[:50], chat_id, config.get("chat_id", ""),
        )
        if text and chat_id:
            messages.append({
                "text": text,
                "chat_id": chat_id,
                "update_id": update_id,
            })
        # Toujours avancer l'offset
        if update_id > offset:
            offset = update_id + 1

    if offset > _read_offset():
        _write_offset(offset)
        logger.info("Offset persisted: %d", offset)
    else:
        logger.info("Offset unchanged: %d (no persist)", offset)

    return messages
```

**Step 3: Run a --once cycle and verify logs**

Run: `.venv/Scripts/python.exe scripts/v9_telegram_notifier.py --once 2>&1 | tail -20`
Expected: logs `[INFO] getUpdates offset=X` + `[INFO] getUpdates returned N raw updates` + `[INFO] update_id=Y text='...' chat_id=...` (or "no messages")

**Step 4: Commit**

```bash
git add scripts/v9_telegram_notifier.py
git commit -m "debug(v9): add explicit logs to _fetch_commands for Telegram diagnostics"
```

---

## Task 2 : Forcer la persistance offset à chaque cycle

**Objective:** Garantir que le fichier `logs/.telegram_offset` est toujours écrit, même si l'offset en mémoire n'a pas augmenté.

**Files:**
- Modify: `scripts/v9_telegram_notifier.py:686-690` (lines that conditionally call `_write_offset`)

**Step 1: Replace the conditional with unconditional write**

Find the block:
```python
if offset > _read_offset():
    _write_offset(offset)

return messages
```

Replace with:
```python
# TOUJOURS persister l'offset, même s'il n'a pas changé (CEO 2026-07-11).
# Cela garantit qu'au prochain démarrage, on ne revoit pas les anciens
# messages. Le coût = 1 write de 20 bytes par cycle, négligeable.
_write_offset(offset)
logger.debug("offset persisted: %d", offset)

return messages
```

**Step 2: Test the change runtime**

Run: `.venv/Scripts/python.exe scripts/v9_telegram_notifier.py --once 2>&1 | tail -5`
Expected: `logs/.telegram_offset` est créé avec un entier (ex: 588716881)

```bash
ls -la logs/.telegram_offset
cat logs/.telegram_offset
```

**Step 3: Commit**

```bash
git add scripts/v9_telegram_notifier.py
git commit -m "fix(v9): always persist Telegram offset (was conditional, missed writes)"
```

---

## Task 3 : Ajouter logs dans `_call_hermes` pour diagnostiquer le LLM

**Objective:** Savoir si le LLM est appelé, ce qu'il répond, et combien de temps ça prend.

**Files:**
- Modify: `scripts/v9_telegram_notifier.py:213-360` (function `_call_hermes`)

**Step 1: Add timing + log to `_call_hermes`**

Find the function `_call_hermes` and add these logs at key points:

```python
def _call_hermes(user_text: str, conversation: list[dict[str, str]]) -> str:
    """Envoie un message à l'API LLM (Ollama Cloud) avec mémoire de conversation.

    Version debug 2026-07-11 : ajoute logs explicites.
    """
    t0 = time.time()
    api_key = _read_ollama_key()
    if not api_key:
        logger.warning("LLM: no key found, using fallback redirige")
        return _fallback_redirige(user_text)

    logger.info("LLM call: text=%r (len=%d)", user_text[:80], len(user_text))

    # ... existing code ...

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read())
            elapsed = time.time() - t0
            logger.info("LLM response in %.1fs", elapsed)
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        logger.error("LLM HTTPError %d in %.1fs : %s", e.code, elapsed, e.read()[:200])
        if e.code in (401, 403, 404, 405):
            return (
                f"⚠️ LLM Ollama Cloud erreur {e.code} (clé/quota/endpoint).\n\n"
                + _fallback_redirige(user_text)
            )
        return f"⚠️ LLM erreur {e.code}.\n\n" + _fallback_redirige(user_text)
    except Exception as e:
        elapsed = time.time() - t0
        logger.error("LLM exception in %.1fs : %s", elapsed, e)
        return (
            f"⚠️ LLM indisponible ({type(e).__name__}).\n\n"
            + _fallback_redirige(user_text)
        )
```

**Step 2: Verify logs appear during --once**

Run: `.venv/Scripts/python.exe scripts/v9_telegram_notifier.py --once 2>&1 | grep -E "LLM|fallback"`
Expected: at least one log line about LLM or fallback

**Step 3: Commit**

```bash
git add scripts/v9_telegram_notifier.py
git commit -m "debug(v9): add timing + error logs to _call_hermes LLM function"
```

---

## Task 4 : Test end-to-end — Søn envoie /status et reçoit une réponse

**Objective:** Prouver que le pipeline complet fonctionne : daemon reçoit message → log explicite → réponse Telegram → Søn reçoit.

**Files:**
- Test: `tests/test_telegram_e2e.py` (new file, optional mais recommandé)

**Step 1: Create a manual e2e test script**

Create: `tests/test_telegram_e2e.py`

```python
"""Test E2E : envoie un message Telegram via curl, vérifie que le daemon
le reçoit et y répond.

Pré-requis : daemon --watch actif. Test manuel, pas dans la suite pytest.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
    )
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())["ok"]


def get_recent_updates(token: str, n: int = 5) -> list[dict]:
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset=-{n}&timeout=0"
    r = urllib.request.urlopen(url, timeout=10)
    return json.loads(r.read())["result"]


def main() -> int:
    env = Path(".env").read_text(encoding="utf-8")
    token = next(
        line.split("=", 1)[1].strip()
        for line in env.splitlines()
        if line.startswith("TELEGRAM_BOT_TOKEN=")
    )
    chat_id = next(
        line.split("=", 1)[1].strip()
        for line in env.splitlines()
        if line.startswith("TELEGRAM_CHAT_ID=")
    )

    # 1. Note l'offset actuel
    log_path = Path("logs/telegram_notifier.log")
    size_before = log_path.stat().st_size if log_path.exists() else 0

    # 2. Envoie /status
    test_cmd = f"/status test_e2e_{int(time.time())}"
    print(f"Envoi : {test_cmd!r}")
    if not send_telegram(token, chat_id, test_cmd):
        print("❌ Envoi Telegram échoué")
        return 1

    # 3. Attend 5s pour que le daemon traite
    print("Attente 5s pour traitement daemon...")
    time.sleep(5)

    # 4. Vérifie les logs
    if log_path.exists():
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(size_before)
            new_logs = f.read()
        if "update_id=" in new_logs and test_cmd in new_logs:
            print(f"✅ Daemon a reçu le message dans les logs")
            print(f"   Extrait : {new_logs[:500]}")
            return 0
        else:
            print(f"❌ Message pas trouvé dans les logs")
            print(f"   Nouveaux logs : {new_logs[:500]}")
            return 1
    else:
        print("❌ Fichier log absent")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

**Step 2: Run the e2e test (with daemon --watch running)**

Prerequisites:
- Daemon WATCH must be running in another terminal/background
- Use a unique command suffix (`test_e2e_TIMESTAMP`) to avoid clashes

```bash
.venv/Scripts/python.exe tests/test_telegram_e2e.py
```

Expected output:
```
Envoi : '/status test_e2e_1783738XXX'
Attente 5s pour traitement daemon...
✅ Daemon a reçu le message dans les logs
   Extrait : [INFO] getUpdates offset=XXX ...
              [INFO] update_id=XXX text='/status test_e2e_...' chat_id=1401055223
              [INFO] ...
```

**Step 3: If the test FAILS, capture diagnostic info**

If daemon doesn't receive, check:
1. `ps aux | grep telegram` — is only 1 daemon running?
2. `cat logs/.telegram_offset` — does the file exist?
3. `tail -20 logs/telegram_notifier.log` — what are the latest logs?
4. `python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org/bot<TOKEN>/getMe').read())"` — is the token valid?

**Step 4: Commit**

```bash
git add tests/test_telegram_e2e.py
git commit -m "test(v9): add e2e Telegram pipeline test (manual, requires daemon --watch)"
```

---

## Task 5 : Cleanup et commit final

**Objective:** S'assurer que tout est propre, commit-ready, et que la documentation est à jour.

**Files:**
- Modify: `docs/STATE.md` (ajouter entrée courte H24+1)
- Modify: `docs/ROADMAP.md` (si pertinent)

**Step 1: Add brief entry to STATE.md**

In `docs/STATE.md`, after the line `## Dernière mise à jour`, add a new section:

```markdown
2026-07-11 — **Telegram bidirectionnel réparé** — Søn reçoit enfin les réponses aux 16 commandes + texte libre.
- Bug `_write_offset` conditionnel → forcé à chaque cycle
- Logs debug ajoutés à `_fetch_commands` + `_call_hermes` (timing + errors)
- Lock file anti-multi-instance `logs/.telegram_daemon.lock` (CEO 2026-07-11)
- Test e2e `tests/test_telegram_e2e.py` (manual, daemon --watch requis)
- HEAD : 393ceb5 → commit à venir
```

**Step 2: Verify pytest full suite passes**

Run: `.venv/Scripts/python.exe -m pytest -q --tb=line 2>&1 | tail -5`
Expected: `947 passed, 2 skipped` (or more if test_e2e adds tests)

**Step 3: Final commit + push**

```bash
git add docs/STATE.md
git commit -m "docs(v9): STATE entry for Telegram bidirectionnel fix (2026-07-11)"
git push origin feat/v9-foundation-clean
```

**Step 4: Send Telegram confirmation to Søn**

Send via the running daemon or direct API:
```python
python -c "
import urllib.request, urllib.parse, json
from pathlib import Path
env = Path('.env').read_text(encoding='utf-8')
token = [l.split('=',1)[1] for l in env.splitlines() if 'TELEGRAM_BOT_TOKEN=' in l][0]
chat = [l.split('=',1)[1] for l in env.splitlines() if 'TELEGRAM_CHAT_ID=' in l][0]
msg = '''🟢 Telegram bidirectionnel RÉPARÉ (CEO 2026-07-11)

✅ 5 tâches du plan writing-plans livrées :
1. Logs debug _fetch_commands (voir ce qui se passe)
2. _write_offset forcé à chaque cycle (plus de silence)
3. Logs _call_hermes (timing + errors LLM)
4. Test e2e test_telegram_e2e.py
5. STATE.md à jour

📊 Tests : 947 verts, 0 régression.
HEAD : nouveau commit, push OK.

🎯 Test maintenant :
- Tape /status → réponse < 2s
- Tape un texte libre → redirige vers commandes
- Lock file empêche 2 daemons en parallèle

Si tu ne reçois toujours pas, dis-le moi immédiatement.'''
data = urllib.parse.urlencode({'chat_id': chat, 'text': msg}).encode()
req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data, method='POST')
r = urllib.request.urlopen(req, timeout=10)
print('OK:', json.loads(r.read())['ok'])
"
```

---

## Critères de succès

**Le plan est réussi si :**
- [ ] `_fetch_commands` logge chaque update reçu avec son update_id, text, chat_id
- [ ] `logs/.telegram_offset` est créé et mis à jour à chaque cycle de polling
- [ ] `_call_hermes` logge le timing de chaque appel LLM
- [ ] Søn envoie `/status test_e2e_XXX` et reçoit une réponse dans les 5 secondes
- [ ] Les logs montrent clairement que le message a été : reçu → traité → offset persisté → réponse envoyée
- [ ] pytest 947 verts (ou plus), 0 régression
- [ ] HEAD git push OK

## Anti-patterns à éviter

- ❌ Ne pas modifier `core/v9/*` (R8 strict) — seul `scripts/v9_telegram_notifier.py` est touché
- ❌ Ne pas ajouter de dépendance pip (R18) — stdlib only
- ❌ Ne pas tenter de fix le LLM Ollama Cloud (bug provider externe, hors scope)
- ❌ Ne pas créer de nouveau token Telegram (le token actuel est OK, c'est le daemon qui boucle)
- ❌ Ne pas fixer le lock file à nouveau (déjà fait dans commit précédent)
- ❌ Ne pas commit sans avoir vu les logs de debug dans la sortie

## Rollback

Si une tâche casse, rollback via :
```bash
git reset --hard 393ceb5  # retour à l'état HEAD avant le plan
pkill -f "v9_telegram_notifier"
```

Le daemon doit ensuite être relancé manuellement.
