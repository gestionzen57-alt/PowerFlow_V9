"""Tests — branching HITL confiance 40-65 (Brief O3, 2026-07-12).

Couvre core/v9/decision_logger.py :
  - conf > 65        -> inchangé
  - 40 <= conf <= 65  -> notification Telegram best-effort, rate-limitée
  - conf < 40         -> low_confidence_block=1, pas de Telegram
  - kill switch V9_HITL_BRANCHING_ENABLED
  - rate-limit 1/5min/(symbol x TF) + compteur agrégé
  - jamais bloquant (échec Telegram -> pipeline survit, règle 6)

IMPORTANT sécurité tests : config/telegram.json contient de VRAIES
credentials (gitignored, local). Tous les tests qui touchent le chemin
Telegram monkeypatchent `_load_telegram_config_safe` et/ou
`scripts.v9_telegram_notifier.send_telegram` — AUCUN test ne doit
déclencher un envoi réseau réel.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import decision_logger  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.decision_logger import DecisionLogger, HITL_BRANCHING_ENABLED_ENV  # noqa: E402
from tests.test_decision_logger import build_full_chain, db_path  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """État process-global — reset entre chaque test pour éviter les
    interférences (ordre des tests non garanti)."""
    decision_logger._telegram_rate_state.clear()
    yield
    decision_logger._telegram_rate_state.clear()


@pytest.fixture(autouse=True)
def _no_real_telegram_config(monkeypatch: pytest.MonkeyPatch):
    """Garde-fou par défaut : aucune config Telegram trouvée, donc même en
    cas de bug, aucun test ne peut envoyer un message réel. Les tests qui
    veulent simuler un envoi réussi surchargent explicitement ce mock."""
    monkeypatch.setattr(decision_logger, "_load_telegram_config_safe", lambda: None)


def _get_decision_row(db_path: Path, snapshot_id: str) -> dict:
    conn = get_connection(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        row = conn.execute(
            "SELECT * FROM decisions WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


# ---------- conf > 65 : inchangé ----------


def test_conf_above_65_low_confidence_block_zero_no_notification(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    snap_id = build_full_chain(db_path, signal_confiance=80, signal_direction="haussiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)

    assert dec["low_confidence_block"] == 0
    assert calls == []
    row = _get_decision_row(db_path, snap_id)
    assert row["low_confidence_block"] == 0


# ---------- 40 <= conf <= 65 : notification informative ----------


def test_conf_in_informative_band_triggers_notification_not_block(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    snap_id = build_full_chain(db_path, signal_confiance=50, signal_direction="haussiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)

    assert dec["low_confidence_block"] == 0  # informatif, PAS bloqué
    assert len(calls) == 1
    symbol, timeframe, direction, confiance, principes = calls[0]
    assert symbol == "GBPUSD" and direction == "haussiere" and confiance == 50


@pytest.mark.parametrize("conf", [40, 65])
def test_conf_informative_band_bounds_inclusive(db_path: Path, monkeypatch: pytest.MonkeyPatch, conf: int):
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    snap_id = build_full_chain(db_path, signal_confiance=conf, signal_direction="haussiere")
    DecisionLogger(db_path=db_path).log(snap_id)
    assert len(calls) == 1


def test_notify_low_confidence_builds_expected_message_and_sends(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Vérifie le format du message ET qu'aucun réseau réel n'est utilisé
    (send_telegram mocké)."""
    monkeypatch.setattr(decision_logger, "_load_telegram_config_safe",
                        lambda: {"token": "FAKE", "chat_id": "FAKE"})
    sent = []

    def fake_send_telegram(text, config, timeout=15):
        sent.append((text, config, timeout))
        return True

    import scripts.v9_telegram_notifier as tg_module
    monkeypatch.setattr(tg_module, "send_telegram", fake_send_telegram)

    decision_logger._notify_low_confidence_telegram(
        "GBPUSD", "M15", "haussiere", 55, ["ZONE_RETEST", "PRICE_LAG_AT_NODE_BIRTH"],
    )

    assert len(sent) == 1
    text, config, timeout = sent[0]
    assert "GBPUSD" in text and "M15" in text and "haussiere" in text and "conf=55" in text
    assert "ZONE_RETEST" in text and "informatif" in text and "bloquée par RiskManager si <70" in text
    assert config == {"token": "FAKE", "chat_id": "FAKE"}
    assert timeout == decision_logger.HITL_TELEGRAM_TIMEOUT_SECONDS


# ---------- conf < 40 : block, pas de Telegram ----------


def test_conf_below_40_sets_low_confidence_block_no_notification(
    db_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
):
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    with caplog.at_level(logging.INFO, logger="v9.decision_logger"):
        snap_id = build_full_chain(db_path, signal_confiance=30, signal_direction="haussiere")
        dec = DecisionLogger(db_path=db_path).log(snap_id)

    assert dec["low_confidence_block"] == 1
    assert calls == []  # pas de Telegram
    row = _get_decision_row(db_path, snap_id)
    assert row["low_confidence_block"] == 1
    assert any("low_confidence_block" in r.message for r in caplog.records)


# ---------- Non-directionnel : pas d'effet ----------


def test_non_directional_decision_no_branching_effect(db_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    snap_id = build_full_chain(
        db_path, signal_confiance=0, signal_direction=None,
        raison_absence="aucun_principe_actif_declenche",
    )
    dec = DecisionLogger(db_path=db_path).log(snap_id)
    assert dec["low_confidence_block"] == 0
    assert calls == []


# ---------- Kill switch ----------


def test_kill_switch_disables_branching_entirely(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(HITL_BRANCHING_ENABLED_ENV, "0")
    calls = []
    monkeypatch.setattr(decision_logger, "_notify_low_confidence_telegram",
                        lambda *a, **kw: calls.append(a))
    snap_id = build_full_chain(db_path, signal_confiance=30, signal_direction="haussiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)
    assert dec["low_confidence_block"] == 0  # kill switch -> comportement désactivé
    assert calls == []


# ---------- Rate limit + compteur agrégé ----------


def test_rate_limit_check_allows_first_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(decision_logger.time, "monotonic", lambda: 1000.0)
    should_send, suppressed = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    assert should_send is True
    assert suppressed == 0


def test_rate_limit_check_suppresses_within_window(monkeypatch: pytest.MonkeyPatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(decision_logger.time, "monotonic", lambda: t["now"])
    should_send1, _ = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    assert should_send1 is True

    t["now"] = 1010.0  # 10s plus tard, < 300s -> supprimé
    should_send2, _ = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    assert should_send2 is False

    t["now"] = 1020.0
    should_send3, _ = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    assert should_send3 is False


def test_rate_limit_check_reports_aggregated_suppressed_count_after_window(
    monkeypatch: pytest.MonkeyPatch,
):
    t = {"now": 1000.0}
    monkeypatch.setattr(decision_logger.time, "monotonic", lambda: t["now"])
    decision_logger._hitl_rate_limit_check("GBPUSD|M15")  # 1er envoi, t=1000

    t["now"] = 1010.0
    decision_logger._hitl_rate_limit_check("GBPUSD|M15")  # supprimé #1
    t["now"] = 1020.0
    decision_logger._hitl_rate_limit_check("GBPUSD|M15")  # supprimé #2

    t["now"] = 1301.0  # > 300s après le dernier envoi (1000) -> nouvel envoi autorisé
    should_send, suppressed = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    assert should_send is True
    assert suppressed == 2


def test_rate_limit_is_per_symbol_timeframe_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(decision_logger.time, "monotonic", lambda: 1000.0)
    should_send_a, _ = decision_logger._hitl_rate_limit_check("GBPUSD|M15")
    should_send_b, _ = decision_logger._hitl_rate_limit_check("GBPUSD|H1")
    assert should_send_a is True
    assert should_send_b is True  # clé différente -> pas de rate-limit croisé


def test_decision_logger_rate_limits_repeated_informative_notifications(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """2 décisions coup sur coup (même symbol/TF, bande 40-65) via
    _apply_hitl_branching() -> 1 seule notification effective (rate-limit).
    Appel direct de la méthode (pas log()/build_full_chain) pour éviter la
    contrainte UNIQUE(symbol,timeframe,bar_time) de forces_snapshots, hors
    sujet ici — le rate-limit lui-même est déjà couvert unitairement
    ci-dessus ; ce test vérifie l'intégration avec DecisionLogger."""
    monkeypatch.setattr(decision_logger, "_load_telegram_config_safe",
                        lambda: {"token": "FAKE", "chat_id": "FAKE"})
    sent = []
    import scripts.v9_telegram_notifier as tg_module
    monkeypatch.setattr(tg_module, "send_telegram",
                        lambda text, config, timeout=15: sent.append(text) or True)

    logger_ = DecisionLogger(db_path=db_path)
    logger_._apply_hitl_branching(
        direction="haussiere", confiance=45, symbol="GBPUSD", timeframe="M15", principes=["P1"],
    )
    logger_._apply_hitl_branching(
        direction="haussiere", confiance=60, symbol="GBPUSD", timeframe="M15", principes=["P1"],
    )

    assert len(sent) == 1  # 2e supprimé par le rate-limit


# ---------- Jamais bloquant (règle 6) ----------


def test_telegram_failure_never_raises_pipeline_survives(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(decision_logger, "_load_telegram_config_safe",
                        lambda: {"token": "FAKE", "chat_id": "FAKE"})
    import scripts.v9_telegram_notifier as tg_module

    def boom(*args, **kwargs):
        raise RuntimeError("réseau HS")

    monkeypatch.setattr(tg_module, "send_telegram", boom)

    snap_id = build_full_chain(db_path, signal_confiance=50, signal_direction="haussiere")
    # Ne doit PAS lever malgré l'exception dans send_telegram.
    dec = DecisionLogger(db_path=db_path).log(snap_id)
    assert dec["snapshot_id"] == snap_id
    assert dec["low_confidence_block"] == 0
