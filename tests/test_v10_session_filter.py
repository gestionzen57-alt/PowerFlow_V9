"""V10 Session Filter — tests unitaires (Phase 14 Edge Fund).

Obligations Phase 14 :
  1. test_session_quality_eurusd_london_overlap
  2. test_session_quality_usdjpy_london
  3. test_session_quality_audusd_asian
  4. test_session_quality_usdcad_ny
  5. test_session_quiet_low_score
  6. test_is_optimal_for_pair_only_top_score
  7. test_a1_eligible_threshold_080
  8. test_apply_session_downgrade_a1_quiet
  9. test_apply_session_conserves_a1_optimal
 10. test_default_timestamp_now_utc

Bonus : helpers, audit, serialization, R2, R10.
"""
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_session_filter import (  # noqa: E402
    SessionName,
    SessionQuality,
    SESSION_HOURS_UTC,
    PAIR_SESSION_MATRIX,
    get_session_quality,
    apply_session_to_signal,
    _session_at_hour,
    _matrix_for,
)


# ─────────────────────────────────────────────────────────────────────
# 1. test_session_quality_eurusd_london_overlap
# ─────────────────────────────────────────────────────────────────────
def test_session_quality_eurusd_london_overlap():
    """EURUSD à 12:30 UTC = OVERLAP, score=1.0."""
    q = get_session_quality("EURUSD", timestamp="2026-08-04T12:30:00Z")
    assert q.session_now == SessionName.OVERLAP
    assert q.quality_score == 1.00
    assert q.is_optimal_for_pair is True
    assert q.a1_eligible is True


def test_session_quality_eurusd_london():
    """EURUSD à 09:00 UTC = LONDON, score=0.85 → is_optimal."""
    q = get_session_quality("EURUSD", timestamp="2026-08-04T09:00:00Z")
    assert q.session_now == SessionName.LONDON
    assert q.quality_score == 0.85
    assert q.is_optimal_for_pair is True


# ─────────────────────────────────────────────────────────────────────
# 2. test_session_quality_usdjpy_london
# ─────────────────────────────────────────────────────────────────────
def test_session_quality_usdjpy_london():
    """USDJPY à 09:00 UTC = LONDON, score=0.85."""
    q = get_session_quality("USDJPY", timestamp="2026-08-04T09:00:00Z")
    assert q.session_now == SessionName.LONDON
    assert q.quality_score == 0.85


# ─────────────────────────────────────────────────────────────────────
# 3. test_session_quality_audusd_asian
# ─────────────────────────────────────────────────────────────────────
def test_session_quality_audusd_asian():
    """AUDUSD à 03:00 UTC = ASIAN, score=0.85."""
    q = get_session_quality("AUDUSD", timestamp="2026-08-04T03:00:00Z")
    assert q.session_now == SessionName.ASIAN
    assert q.quality_score == 0.85


def test_session_quality_nzdusd_asian_optimal():
    """NZDUSD à 02:00 UTC = ASIAN, score=0.90 → A1 eligible."""
    q = get_session_quality("NZDUSD", timestamp="2026-08-04T02:00:00Z")
    assert q.session_now == SessionName.ASIAN
    assert q.quality_score == 0.90


# ─────────────────────────────────────────────────────────────────────
# 4. test_session_quality_usdcad_ny
# ─────────────────────────────────────────────────────────────────────
def test_session_quality_usdcad_ny():
    """USDCAD à 17:00 UTC = NY, score=1.0."""
    q = get_session_quality("USDCAD", timestamp="2026-08-04T17:00:00Z")
    assert q.session_now == SessionName.NY
    assert q.quality_score == 1.00


# ─────────────────────────────────────────────────────────────────────
# 5. test_session_quiet_low_score
# ─────────────────────────────────────────────────────────────────────
def test_session_quiet_low_score():
    """Tous les paires ont score < 0.5 en QUIET (21:00-00:00)."""
    for sym in ["EURUSD", "USDJPY", "AUDUSD", "USDCAD"]:
        q = get_session_quality(sym, timestamp="2026-08-04T22:00:00Z")
        assert q.session_now == SessionName.QUIET
        assert q.quality_score < 0.5
        assert q.a1_eligible is False
        assert q.is_optimal_for_pair is False


# ─────────────────────────────────────────────────────────────────────
# 6. test_is_optimal_for_pair_only_top_score
# ─────────────────────────────────────────────────────────────────────
def test_is_optimal_for_pair_only_top_score():
    """is_optimal_for_pair = True ssi session_now >= 0.85."""
    # EURUSD NY (score 0.75) : pas optimal
    q = get_session_quality("EURUSD", timestamp="2026-08-04T19:00:00Z")
    assert q.session_now == SessionName.NY
    assert q.is_optimal_for_pair is False  # 0.75 < 0.85
    # EURUSD OVERLAP (score 1.0) : optimal
    q = get_session_quality("EURUSD", timestamp="2026-08-04T13:00:00Z")
    assert q.is_optimal_for_pair is True


# ─────────────────────────────────────────────────────────────────────
# 7. test_a1_eligible_threshold_080
# ─────────────────────────────────────────────────────────────────────
def test_a1_eligible_threshold_080():
    """A1 eligible ssi quality_score >= 0.80."""
    # GBPUSD 09:00 (LONDON 0.90) → A1 eligible
    q = get_session_quality("GBPUSD", timestamp="2026-08-04T09:00:00Z")
    assert q.a1_eligible is True
    # USDCHF 03:00 (ASIAN 0.50) → pas A1
    q = get_session_quality("USDCHF", timestamp="2026-08-04T03:00:00Z")
    assert q.a1_eligible is False


# ─────────────────────────────────────────────────────────────────────
# 8. test_apply_session_downgrade_a1_quiet
# ─────────────────────────────────────────────────────────────────────
def test_apply_session_downgrade_a1_quiet():
    """A1 pendant QUIET → downgrade A2."""
    q = get_session_quality("EURUSD", timestamp="2026-08-04T22:00:00Z")
    new_lvl, downgraded, severity = apply_session_to_signal("A1", q)
    assert new_lvl == "A2"
    assert downgraded is True
    assert severity == "soft"


def test_apply_session_downgrade_a1_low_quality():
    """A1 sans quality optimale → downgrade A2."""
    q = get_session_quality("EURUSD", timestamp="2026-08-04T19:00:00Z")  # NY 0.75
    new_lvl, downgraded, severity = apply_session_to_signal("A1", q)
    assert new_lvl == "A2"
    assert downgraded is True


# ─────────────────────────────────────────────────────────────────────
# 9. test_apply_session_conserves_a1_optimal
# ─────────────────────────────────────────────────────────────────────
def test_apply_session_conserves_a1_optimal():
    """A1 en OVERLAP EURUSD → conservé."""
    q = get_session_quality("EURUSD", timestamp="2026-08-04T13:00:00Z")
    new_lvl, downgraded, _ = apply_session_to_signal("A1", q)
    assert new_lvl == "A1"
    assert downgraded is False


def test_apply_session_no_downgrade_when_a2():
    q = get_session_quality("EURUSD", timestamp="2026-08-04T22:00:00Z")  # QUIET
    new_lvl, downgraded, _ = apply_session_to_signal("A2", q)
    assert new_lvl == "A2"
    assert downgraded is False  # pas A1 → pas de downgrade


# ─────────────────────────────────────────────────────────────────────
# 10. test_default_timestamp_now_utc
# ─────────────────────────────────────────────────────────────────────
def test_default_timestamp_now_utc():
    """Si pas de timestamp → now UTC, session valide."""
    q = get_session_quality("EURUSD")
    assert q.session_now != SessionName.UNKNOWN
    assert q.timestamp != ""


# ─────────────────────────────────────────────────────────────────────
# Bonus invariants
# ─────────────────────────────────────────────────────────────────────
def test_session_at_hour_helper():
    assert _session_at_hour(3) == SessionName.ASIAN
    assert _session_at_hour(9) == SessionName.LONDON
    assert _session_at_hour(13) == SessionName.OVERLAP
    assert _session_at_hour(17) == SessionName.NY  # 16-20 UTC = NY pur
    assert _session_at_hour(22) == SessionName.QUIET
    assert _session_at_hour(0) == SessionName.ASIAN


def test_matrix_for_known_pair():
    m = _matrix_for("EURUSD")
    assert m[SessionName.OVERLAP] == 1.00


def test_matrix_for_unknown_pair_uses_default():
    m = _matrix_for("XYZABC")
    assert m == PAIR_SESSION_MATRIX["OTHER"]


def test_session_quality_serializable():
    q = get_session_quality("EURUSD", timestamp="2026-08-04T13:00:00Z")
    j = json.dumps(q.as_dict())
    parsed = json.loads(j)
    assert "quality_score" in parsed
    assert "session_now" in parsed


def test_session_quality_audit_present():
    q = get_session_quality("USDJPY", timestamp="2026-08-04T05:00:00Z")
    assert "matrix_used" in q.audit
    assert "hour_utc" in q.audit


def test_r2_no_import_core_v9():
    src = Path(ROOT / "core" / "v10" / "v10_session_filter.py").read_text(encoding="utf-8")
    forbidden = []
    for line in src.splitlines():
        if "from core.v9" in line or "import core.v9" in line:
            forbidden.append(line)
    assert not forbidden


def test_r10_no_order_transmission():
    src = Path(ROOT / "core" / "v10" / "v10_session_filter.py").read_text(encoding="utf-8")
    forbidden = ("order_send", "positions_open", "trade_request")
    for f in forbidden:
        assert f not in src, f"R10 violation: {f}"


def test_session_quality_init():
    q = SessionQuality()
    assert q.symbol == ""
    assert q.session_now == SessionName.UNKNOWN
    assert q.quality_score == 0.0


def test_apply_session_other_setup_levels_unchanged():
    q = get_session_quality("EURUSD", timestamp="2026-08-04T22:00:00Z")
    for lvl in ["NONE", "A3", "A2"]:
        new_lvl, downgraded, _ = apply_session_to_signal(lvl, q)
        assert new_lvl == lvl
        assert downgraded is False
