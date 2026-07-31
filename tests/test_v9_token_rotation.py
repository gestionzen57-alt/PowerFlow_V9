"""tests/test_v9_token_rotation.py — Phase 19 motion CEO « EDGE FUND MAX »."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def workspace_tokens(tmp_path, monkeypatch):
    """Setup workspace avec env file + history."""
    env_file = tmp_path / "v9_tokens.env"
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=40)).isoformat()  # 40 jours = expired
    warn_ts = (now - timedelta(days=20)).isoformat()  # 20 jours = warning
    ok_ts = (now - timedelta(days=5)).isoformat()    # 5 jours = OK

    env_file.write_text(f"""# V9 tokens test
TELEGRAM_BOT_TOKEN_BALANCE=1234567890:ABC_BALANCE_LAST4
TELEGRAM_BOT_TOKEN_BALANCE_LAST_ROTATED={old_ts}
TELEGRAM_BOT_TOKEN_RISK=9876543210:XYZ_RISK_LAST4
TELEGRAM_BOT_TOKEN_RISK_LAST_ROTATED={warn_ts}
TELEGRAM_BOT_TOKEN_SAFE=5555555555:DEF_SAFE_LAST4
TELEGRAM_BOT_TOKEN_SAFE_LAST_ROTATED={ok_ts}
""", encoding="utf-8")

    history = tmp_path / "v9_token_history.json"
    history.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("scripts.v9_token_rotation.TOKEN_ENV_FILE", env_file)
    monkeypatch.setattr("scripts.v9_token_rotation.TOKEN_HISTORY_FILE", history)
    return tmp_path, env_file, history


def test_parse_token_env_returns_3_tokens(workspace_tokens):
    """parse_token_env retourne 3 tokens (ignore _LAST_ROTATED metadata)."""
    from scripts.v9_token_rotation import parse_token_env
    tokens = parse_token_env()
    names = [t["name"] for t in tokens]
    assert "TELEGRAM_BOT_TOKEN_BALANCE" in names
    assert "TELEGRAM_BOT_TOKEN_RISK" in names
    assert "TELEGRAM_BOT_TOKEN_SAFE" in names
    assert "TELEGRAM_BOT_TOKEN_BALANCE_LAST_ROTATED" not in names


def test_compute_age_days_valid():
    """compute_age_days retourne age correct."""
    from scripts.v9_token_rotation import compute_age_days
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=10)).isoformat()
    age = compute_age_days(ts)
    assert age == 10


def test_compute_age_days_invalid():
    """compute_age_days retourne None si date invalide."""
    from scripts.v9_token_rotation import compute_age_days
    assert compute_age_days(None) is None
    assert compute_age_days("not-a-date") is None


def test_compute_age_days_missing():
    """compute_age_days retourne None si pas de date."""
    from scripts.v9_token_rotation import compute_age_days
    assert compute_age_days(None) is None


def test_check_rotation_status_expired_warning_ok(workspace_tokens):
    """check_rotation_status : 1 expired + 1 warning + 1 ok."""
    from scripts.v9_token_rotation import check_rotation_status
    status = check_rotation_status()
    assert status["n_total"] == 3
    assert status["n_expired"] == 1
    assert status["n_warning"] == 1
    assert status["n_ok"] == 1
    assert status["recommendation"] == "ROTATE_URGENT"


def test_check_rotation_status_all_ok(tmp_path, monkeypatch):
    """check_rotation_status : 3 tokens recents."""
    from scripts.v9_token_rotation import check_rotation_status
    env_file = tmp_path / "v9_tokens.env"
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=3)).isoformat()
    env_file.write_text(f"""# OK
TELEGRAM_TOKEN_A=xxx_LAST4
TELEGRAM_TOKEN_A_LAST_ROTATED={ts}
""", encoding="utf-8")
    monkeypatch.setattr("scripts.v9_token_rotation.TOKEN_ENV_FILE", env_file)
    status = check_rotation_status()
    assert status["n_total"] == 1
    assert status["n_ok"] == 1
    assert status["recommendation"] == "ALL_OK"


def test_check_rotation_status_env_missing(tmp_path, monkeypatch):
    """check_rotation_status : env absent → 0 tokens, recommendation ALL_OK."""
    from scripts.v9_token_rotation import check_rotation_status
    monkeypatch.setattr("scripts.v9_token_rotation.TOKEN_ENV_FILE",
                        tmp_path / "absent.env")
    status = check_rotation_status()
    assert status["n_total"] == 0
    assert status["recommendation"] == "ALL_OK"


def test_log_rotation_appends_history(workspace_tokens):
    """log_rotation ajoute une entree."""
    from scripts.v9_token_rotation import log_rotation, load_history
    log_rotation("TELEGRAM_TOKEN_X", "OLD", "NEW", 30)
    history = load_history()
    assert len(history) == 1
    assert history[0]["token_name"] == "TELEGRAM_TOKEN_X"
    assert history[0]["age_before_days"] == 30


def test_load_history_handles_corrupted(workspace_tokens):
    """load_history gere fichier corrompu."""
    tmp_path, env_file, history = workspace_tokens
    history.write_text("{not json", encoding="utf-8")
    from scripts.v9_token_rotation import load_history
    h = load_history()
    assert h == []


def test_save_history_creates_file(tmp_path, monkeypatch):
    """save_history cree le fichier."""
    history = tmp_path / "history.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("scripts.v9_token_rotation.TOKEN_HISTORY_FILE", history)
    from scripts.v9_token_rotation import save_history
    save_history([{"id": 1}, {"id": 2}])
    assert history.exists()
    data = json.loads(history.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_main_check_expired_returns_nonzero(workspace_tokens, monkeypatch, capsys):
    """CLI --check : exit 1 si expired."""
    from scripts.v9_token_rotation import main
    exit_code = main(["--check"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ROTATE_URGENT" in captured.out


def test_main_history_empty(workspace_tokens, capsys):
    """CLI --history : empty history."""
    from scripts.v9_token_rotation import main
    exit_code = main(["--history"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Historique" in captured.out


def test_main_status_output(workspace_tokens, capsys):
    """CLI --status : output complet."""
    from scripts.v9_token_rotation import main
    exit_code = main(["--status"])
    captured = capsys.readouterr()
    assert exit_code == 1  # 1 expired
    assert "PHASE 19" in captured.out
    assert "Procedure de rotation" in captured.out


# Tests v9_mirror_auto_activate
def test_count_human_trades_zero(tmp_path):
    """count_human_trades degrade propre sur fichier vide/invalide."""
    from scripts.v9_mirror_auto_activate import count_human_trades
    db = tmp_path / "v9.db"
    db.write_bytes(b"")  # pas un fichier SQLite valide
    assert count_human_trades(db) == 0


def test_count_human_trades_db_missing(tmp_path):
    """count_human_trades degrade propre sur DB absente."""
    from scripts.v9_mirror_auto_activate import count_human_trades
    assert count_human_trades(tmp_path / "absent.db") == 0


def test_count_human_trades_with_db(tmp_path):
    """count_human_trades avec DB contenant la table."""
    import sqlite3
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""CREATE TABLE v9_human_trades (
            id INTEGER PRIMARY KEY, ts TEXT
        )""")
        for i in range(15):
            conn.execute(
                "INSERT INTO v9_human_trades (ts) VALUES (?)",
                (f"2026-07-31T11:{i:02d}:00",),
            )
        conn.commit()
    from scripts.v9_mirror_auto_activate import count_human_trades
    assert count_human_trades(db) == 15


def test_activate_mirror_blocking_adds_env(tmp_path, monkeypatch):
    """activate_mirror_blocking ajoute V9_HUMAN_MIRROR_BLOCKING=1 si absent."""
    env_file = tmp_path / "v9_kill_switches.env"
    env_file.write_text("# Other flags\nV9_FOO=1\n", encoding="utf-8")
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.ENV_FILE", env_file)
    from scripts.v9_mirror_auto_activate import activate_mirror_blocking
    ok = activate_mirror_blocking()
    assert ok is True
    content = env_file.read_text(encoding="utf-8")
    assert "V9_HUMAN_MIRROR_BLOCKING=1" in content


def test_activate_mirror_blocking_updates_existing(tmp_path, monkeypatch):
    """activate_mirror_blocking remplace valeur existante."""
    env_file = tmp_path / "v9_kill_switches.env"
    env_file.write_text("V9_HUMAN_MIRROR_BLOCKING=0\n", encoding="utf-8")
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.ENV_FILE", env_file)
    from scripts.v9_mirror_auto_activate import activate_mirror_blocking
    activate_mirror_blocking()
    content = env_file.read_text(encoding="utf-8")
    assert "V9_HUMAN_MIRROR_BLOCKING=1" in content


def test_activate_mirror_blocking_env_missing(tmp_path, monkeypatch):
    """activate_mirror_blocking degrade propre sur env absent."""
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.ENV_FILE",
                        tmp_path / "absent.env")
    from scripts.v9_mirror_auto_activate import activate_mirror_blocking
    ok = activate_mirror_blocking()
    assert ok is False


def test_log_motion_appends(tmp_path, monkeypatch):
    """log_motion append si motion log existe deja."""
    motion_log = tmp_path / "v9_motion_log.json"
    motion_log.parent.mkdir(parents=True, exist_ok=True)
    motion_log.write_text(json.dumps([
        {"id": "prev", "type": "ROLLBACK", "ts": "2026-07-30T12:00:00"},
    ]), encoding="utf-8")
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.MOTION_LOG", motion_log)
    from scripts.v9_mirror_auto_activate import log_motion
    log_motion("new reason")
    data = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["id"] == "prev"
    assert data[1]["type"] == "MIRROR_BLOCKING_ACTIVATED"


def test_log_motion_creates_file(tmp_path, monkeypatch):
    """log_motion cree le fichier motion log."""
    motion_log = tmp_path / "v9_motion_log.json"
    motion_log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.MOTION_LOG", motion_log)
    from scripts.v9_mirror_auto_activate import log_motion
    log_motion("test reason")
    assert motion_log.exists()
    data = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["type"] == "MIRROR_BLOCKING_ACTIVATED"


def test_log_motion_handles_corrupted(tmp_path, monkeypatch):
    """log_motion reset si motion log corrompu."""
    motion_log = tmp_path / "v9_motion_log.json"
    motion_log.parent.mkdir(parents=True, exist_ok=True)
    motion_log.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.MOTION_LOG", motion_log)
    from scripts.v9_mirror_auto_activate import log_motion
    log_motion("reason")
    data = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_main_check_wait_more_trades(monkeypatch, capsys):
    """CLI --check : n<20 → WAIT_MORE_TRADES."""
    from scripts.v9_mirror_auto_activate import main
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.count_human_trades",
                        lambda db: 5)
    exit_code = main(["--check"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "WAIT_MORE_TRADES" in captured.out


def test_main_activate_ready(monkeypatch, capsys):
    """CLI --activate : n>=20 → activation OK."""
    from scripts.v9_mirror_auto_activate import main
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.count_human_trades",
                        lambda db: 25)
    exit_code = main(["--activate"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "active OK" in captured.out


def test_main_force_force_activation(monkeypatch, capsys):
    """CLI --force : active sans check."""
    from scripts.v9_mirror_auto_activate import main
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.count_human_trades",
                        lambda db: 0)
    monkeypatch.setattr("scripts.v9_mirror_auto_activate.activate_mirror_blocking",
                        lambda: True)
    exit_code = main(["--force"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "FORCE" in captured.out