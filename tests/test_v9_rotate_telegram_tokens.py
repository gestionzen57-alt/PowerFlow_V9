"""Tests unitaires pour scripts/v9_rotate_telegram_tokens.py.

Couvre :
- _validate_token_format : format BotFather valide/invalide
- _call_telegram_getme : mock reseau (URLError, HTTPError, success)
- _md5 : determinisme + fichiers binaires
- read_config_telegram / read_env : presence, parsing, robustness
- write_config_telegram : round-trip JSON + metadata rotation
- write_env : ordre preserve + header_comment
- backup_files : MD5 + copie (R8)
- main() : dry-run n'ecrit rien, --apply ecrit, --validate-only sans token,
  --no-validate skip reseau, format invalide = exit 2
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

SCRIPT_PATH = _ROOT / "scripts" / "v9_rotate_telegram_tokens.py"


@pytest.fixture
def rot_module():
    """Import le module via importlib (pas dans sys.path)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("v9_rotate_telegram_tokens", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_config_files(tmp_path, monkeypatch):
    """Cree config/telegram.json + .env temporaires et patche les paths du module."""
    cfg = {
        # Tokens factices construits par concaténation (jamais de token réel
        # en clair — guard no-secrets v9_guards.py, R8).
        "BOT_TOKEN": "1111111111:" + "A" * 35,
        "CHAT_ID": "1401055223",
        "bot_name": "Ipspx_bot",
        "created_at": "2026-07-18T10:30:00+02:00",
    }
    cfg_path = tmp_path / "config" / "telegram.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    env_path = tmp_path / ".env"
    env_path.write_text(
        "# Header commentaire prealable\n"
        "TELEGRAM_BOT_TOKEN=" + "2222222222:" + "B" * 35 + "\n"
        "TELEGRAM_CHAT_ID=1401055223\n"
        "TELEGRAM_BOT_NAME=Hiphopvps_bot\n"
        "TELEGRAM_BOT_TOKEN_IPSPX=CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\n"
        "AUTRE_VAR=foo\n",
        encoding="utf-8",
    )

    return cfg_path, env_path


# ---------------------------------------------------------------------------
# Tests _validate_token_format
# ---------------------------------------------------------------------------

def test_validate_token_format_valid(rot_module):
    """Format BotFather valide (bot_id:35-45 chars base64-url)."""
    assert rot_module._validate_token_format("1234567890:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk", "label") is True
    assert rot_module._validate_token_format("12345678:" + "A" * 35, "label") is True
    assert rot_module._validate_token_format("1234567890:" + "A" * 45, "label") is True


def test_validate_token_format_invalid(rot_module):
    """Format invalide."""
    assert rot_module._validate_token_format("not_a_token", "label") is False
    assert rot_module._validate_token_format("123:short", "label") is False
    assert rot_module._validate_token_format("1234567890:" + "A" * 30, "label") is False  # trop court
    assert rot_module._validate_token_format("1234567890:" + "A" * 50, "label") is False  # trop long
    assert rot_module._validate_token_format("", "label") is False


# ---------------------------------------------------------------------------
# Tests _call_telegram_getme (mock reseau)
# ---------------------------------------------------------------------------

def test_call_telegram_getme_success(rot_module):
    """Mock urlopen success → ok=True avec username."""
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({
        "ok": True, "result": {"id": 123, "username": "TestBot", "first_name": "Test"}
    }).encode()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)
    with patch.object(rot_module, "urlopen", return_value=fake_response):
        res = rot_module._call_telegram_getme("123:fake")
    assert res["ok"] is True
    assert res["result"]["username"] == "TestBot"


def test_call_telegram_getme_urlerror(rot_module):
    """Mock urlopen URLError → ok=False avec description."""
    from urllib.error import URLError
    with patch.object(rot_module, "urlopen", side_effect=URLError("DNS fail")):
        res = rot_module._call_telegram_getme("123:fake")
    assert res["ok"] is False
    assert "DNS" in res["description"] or "URLError" in res["description"]


def test_call_telegram_getme_http_error(rot_module):
    """Mock urlopen HTTPError (401 unauthorized)."""
    from urllib.error import HTTPError
    with patch.object(rot_module, "urlopen", side_effect=HTTPError("url", 401, "Unauthorized", {}, None)):
        res = rot_module._call_telegram_getme("123:fake")
    assert res["ok"] is False
    assert res["error_code"] == 401


def test_call_telegram_getme_timeout(rot_module):
    """Mock urlopen TimeoutError → ok=False."""
    with patch.object(rot_module, "urlopen", side_effect=TimeoutError("timeout")):
        res = rot_module._call_telegram_getme("123:fake")
    assert res["ok"] is False


# ---------------------------------------------------------------------------
# Tests read_config_telegram / read_env
# ---------------------------------------------------------------------------

def test_read_config_telegram(rot_module, fake_config_files):
    """Lecture config/telegram.json reussie."""
    cfg_path, _ = fake_config_files
    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path):
        cfg = rot_module.read_config_telegram()
    assert cfg["BOT_TOKEN"].startswith("1111111111")
    assert cfg["bot_name"] == "Ipspx_bot"


def test_read_config_telegram_missing(rot_module, tmp_path):
    """Fichier absent → {} (R6)."""
    fake = tmp_path / "absent.json"
    with patch.object(rot_module, "CONFIG_TELEGRAM", fake):
        cfg = rot_module.read_config_telegram()
    assert cfg == {}


def test_read_config_telegram_corrupt(rot_module, tmp_path):
    """JSON corrompu → {} (R6, log error)."""
    fake = tmp_path / "corrupt.json"
    fake.write_text("{invalid json", encoding="utf-8")
    with patch.object(rot_module, "CONFIG_TELEGRAM", fake):
        cfg = rot_module.read_config_telegram()
    assert cfg == {}


def test_read_env(rot_module, fake_config_files):
    """Lecture .env preserve les cles/valeurs (commentaires ignores)."""
    _, env_path = fake_config_files
    with patch.object(rot_module, "ENV_FILE", env_path):
        env = rot_module.read_env()
    assert env["TELEGRAM_BOT_TOKEN"].startswith("2222222222")
    assert env["TELEGRAM_CHAT_ID"] == "1401055223"
    assert env["TELEGRAM_BOT_NAME"] == "Hiphopvps_bot"
    assert env["TELEGRAM_BOT_TOKEN_IPSPX"].startswith("CCC")
    assert env["AUTRE_VAR"] == "foo"


def test_read_env_missing(rot_module, tmp_path):
    """.env absent → {}."""
    fake = tmp_path / "absent.env"
    with patch.object(rot_module, "ENV_FILE", fake):
        env = rot_module.read_env()
    assert env == {}


# ---------------------------------------------------------------------------
# Tests write_env / write_config_telegram
# ---------------------------------------------------------------------------

def test_write_env_roundtrip(rot_module, tmp_path):
    """Ecriture + relecture .env (avec header_comment)."""
    fake = tmp_path / ".env"
    with patch.object(rot_module, "ENV_FILE", fake):
        rot_module.write_env(
            {"KEY1": "val1", "KEY2": "val2"},
            header_comment="Test rotation"
        )
    text = fake.read_text(encoding="utf-8")
    assert "# Test rotation" in text
    assert "KEY1=val1" in text
    assert "KEY2=val2" in text


def test_write_config_telegram_adds_metadata(rot_module, tmp_path):
    """Ecriture config/telegram.json ajoute last_rotated_at."""
    fake = tmp_path / "telegram.json"
    with patch.object(rot_module, "CONFIG_TELEGRAM", fake):
        rot_module.write_config_telegram({"BOT_TOKEN": "x", "bot_name": "y"})
    cfg = json.loads(fake.read_text(encoding="utf-8"))
    assert cfg["BOT_TOKEN"] == "x"
    assert "last_rotated_at" in cfg
    assert cfg["last_rotated_at"].endswith("Z")


# ---------------------------------------------------------------------------
# Tests _md5
# ---------------------------------------------------------------------------

def test_md5_deterministic(rot_module, tmp_path):
    """MD5 deterministe sur le meme contenu."""
    f = tmp_path / "f.txt"
    f.write_text("hello world", encoding="utf-8")
    d1 = rot_module._md5(f)
    d2 = rot_module._md5(f)
    assert d1 == d2
    assert len(d1) == 32


def test_md5_changes_with_content(rot_module, tmp_path):
    """MD5 change quand le contenu change."""
    f = tmp_path / "f.txt"
    f.write_text("v1", encoding="utf-8")
    d1 = rot_module._md5(f)
    f.write_text("v2", encoding="utf-8")
    d2 = rot_module._md5(f)
    assert d1 != d2


# ---------------------------------------------------------------------------
# Tests backup_files (R8)
# ---------------------------------------------------------------------------

def test_backup_files_creates_copy(rot_module, fake_config_files, tmp_path):
    """Backup cree copies + MD5 files (R8)."""
    cfg_path, env_path = fake_config_files
    backup_dir = tmp_path / "backups" / "test"
    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path):
        md5s = rot_module.backup_files(backup_dir)
    assert "telegram.json" in md5s
    assert ".env" in md5s
    assert (backup_dir / "telegram.json.bak").exists()
    assert (backup_dir / "telegram.json.bak.md5").exists()
    assert (backup_dir / ".env.bak").exists()
    assert (backup_dir / ".env.bak.md5").exists()


# ---------------------------------------------------------------------------
# Tests main() CLI
# ---------------------------------------------------------------------------

def test_main_no_tokens_exits_2(rot_module, fake_config_files, caplog):
    """Aucun token fourni → exit 2."""
    cfg_path, env_path = fake_config_files
    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(sys, "argv", ["v9_rotate_telegram_tokens.py"]):
        with caplog.at_level(logging.ERROR):
            rc = rot_module.main()
    assert rc == 2


def test_main_invalid_format_exits_2(rot_module, fake_config_files, caplog):
    """Format token invalide → exit 2."""
    cfg_path, env_path = fake_config_files
    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(sys, "argv", [
             "v9_rotate_telegram_tokens.py",
             "--hiphop-token", "not_a_valid_token",
             "--no-validate",
         ]):
        with caplog.at_level(logging.ERROR):
            rc = rot_module.main()
    assert rc == 2


def test_main_dry_run_does_not_modify(rot_module, fake_config_files):
    """Mode dry-run (par defaut, sans --apply) : aucun fichier modifie."""
    cfg_path, env_path = fake_config_files
    cfg_before = cfg_path.read_text()
    env_before = env_path.read_text()

    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(sys, "argv", [
             "v9_rotate_telegram_tokens.py",
             "--hiphop-token", "9999999999:" + "Z" * 35,
             "--ipspx-token", "8888888888:" + "Y" * 35,
             "--no-validate",
         ]):
        rc = rot_module.main()
    assert rc == 0
    # Aucun changement (dry-run)
    assert cfg_path.read_text() == cfg_before
    assert env_path.read_text() == env_before


def test_main_apply_modifies_files(rot_module, fake_config_files):
    """Mode --apply : ecrit config/telegram.json + .env."""
    cfg_path, env_path = fake_config_files
    new_hiphop = "9999999999:" + "Z" * 35
    new_ipspx = "8888888888:" + "Y" * 35

    # Mock urlopen pour getMe (validation pre + post)
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({
        "ok": True, "result": {"id": 1, "username": "NewBot"}
    }).encode()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(rot_module, "urlopen", return_value=fake_response), \
         patch.object(sys, "argv", [
             "v9_rotate_telegram_tokens.py",
             "--hiphop-token", new_hiphop,
             "--ipspx-token", new_ipspx,
             "--apply",
         ]):
        rc = rot_module.main()
    assert rc == 0
    # Verification ecriture
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["BOT_TOKEN"] == new_ipspx
    env_lines = env_path.read_text(encoding="utf-8").splitlines()
    env_dict = {l.split("=", 1)[0]: l.split("=", 1)[1] for l in env_lines if "=" in l and not l.startswith("#")}
    assert env_dict["TELEGRAM_BOT_TOKEN"] == new_hiphop
    assert env_dict["TELEGRAM_BOT_TOKEN_IPSPX"] == new_ipspx


def test_main_validation_failure_aborts(rot_module, fake_config_files):
    """Si la validation getMe des NOUVEAUX tokens echoue, on n'applique PAS."""
    cfg_path, env_path = fake_config_files
    cfg_before = cfg_path.read_text()
    env_before = env_path.read_text()

    # Mock urlopen retourne KO
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({"ok": False, "description": "Unauthorized"}).encode()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(rot_module, "urlopen", return_value=fake_response), \
         patch.object(sys, "argv", [
             "v9_rotate_telegram_tokens.py",
             "--hiphop-token", "9999999999:" + "Z" * 35,
             "--apply",
         ]):
        rc = rot_module.main()
    assert rc == 4  # validation failed
    # Fichiers intacts
    assert cfg_path.read_text() == cfg_before
    assert env_path.read_text() == env_before


def test_main_validate_only_no_apply(rot_module, fake_config_files):
    """--validate-only ne modifie rien."""
    cfg_path, env_path = fake_config_files
    cfg_before = cfg_path.read_text()

    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({
        "ok": True, "result": {"username": "Ipspx_bot"}
    }).encode()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(rot_module, "urlopen", return_value=fake_response), \
         patch.object(sys, "argv", ["v9_rotate_telegram_tokens.py", "--validate-only"]):
        rc = rot_module.main()
    assert rc == 0
    assert cfg_path.read_text() == cfg_before


def test_main_apply_with_no_validate_skip(rot_module, fake_config_files):
    """--no-validate skip tout appel reseau (utile CI offline)."""
    cfg_path, env_path = fake_config_files
    new_hiphop = "9999999999:" + "Z" * 35

    with patch.object(rot_module, "CONFIG_TELEGRAM", cfg_path), \
         patch.object(rot_module, "ENV_FILE", env_path), \
         patch.object(rot_module, "urlopen") as mock_urlopen, \
         patch.object(sys, "argv", [
             "v9_rotate_telegram_tokens.py",
             "--hiphop-token", new_hiphop,
             "--apply",
             "--no-validate",
         ]):
        rc = rot_module.main()
    assert rc == 0
    mock_urlopen.assert_not_called()
    # .env a ete mis a jour
    env_text = env_path.read_text(encoding="utf-8")
    assert new_hiphop in env_text
