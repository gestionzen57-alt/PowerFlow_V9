"""Tests — scripts/v9_dashboard.py (Phase 8, dashboard de monitoring).

Teste uniquement les fonctions de formatage pures (aucune I/O DB) : tableau
des forces, détection marché ouvert/fermé, âge d'un snapshot, badges de
couleur stale/OK, formatage comportement et formatage fenêtre.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.v9_dashboard import (
    format_age,
    format_behavior_block,
    format_forces_table,
    format_window_block,
    market_status_line,
    snapshot_age_seconds,
    stale_badge,
)


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ── format_forces_table ───────────────────────────────────
class TestFormatForcesTable:
    def test_empty_rows_returns_placeholder(self):
        result = format_forces_table({}, use_color=False)
        assert "aucune force" in result.lower()

    def test_single_timeframe_row_contains_values(self):
        rows = {
            "M5": {
                "force_usd": 62.4, "force_gbp": 48.1, "force_eur": 55.2, "force_jpy": 41.0,
                "force_cad": 38.5, "force_chf": 44.2, "force_aud": 35.8, "force_nzd": 50.1,
                "stale": False,
            }
        }
        result = format_forces_table(rows, use_color=False)
        assert "M5" in result
        assert "62.4" in result
        assert "50.1" in result
        # Header lists devises in FORMAT_FORCES.md order.
        assert "USD" in result and "NZD" in result

    def test_timeframes_ordered_natively(self):
        rows = {
            "H1": {"force_usd": 1.0, "stale": False},
            "M1": {"force_usd": 2.0, "stale": False},
            "M5": {"force_usd": 3.0, "stale": False},
        }
        result = format_forces_table(rows, use_color=False)
        lines = [l for l in result.splitlines() if l.strip().startswith(("M1", "M5", "H1"))]
        assert [l.strip()[:2] for l in lines] == ["M1", "M5", "H1"]

    def test_missing_force_value_shown_as_placeholder(self):
        rows = {"M5": {"force_usd": 10.0, "stale": False}}
        result = format_forces_table(rows, use_color=False)
        assert "--" in result


# ── détection marché ouvert / fermé ───────────────────────
class TestMarketStatusLine:
    def test_saturday_is_closed(self):
        # 2026-07-04 est un samedi.
        line = market_status_line(_utc(2026, 7, 4, 12), use_color=False)
        assert "FERMÉ" in line

    def test_midweek_is_open_with_session(self):
        # 2026-07-08 est un mercredi, 10h UTC -> session Londres.
        line = market_status_line(_utc(2026, 7, 8, 10), use_color=False)
        assert "OUVERT" in line
        assert "Londres" in line

    def test_overlap_session_labelled(self):
        line = market_status_line(_utc(2026, 7, 8, 14), use_color=False)
        assert "OUVERT" in line
        assert "Chevauchement" in line

    def test_closed_without_recent_snapshot_unchanged(self):
        # Comportement inchangé quand aucun snapshot récent n'est fourni.
        line = market_status_line(_utc(2026, 7, 4, 12), use_color=False, last_snapshot=None)
        assert line == "Marché : FERMÉ"

    def test_closed_with_recent_live_activity_warns_dst(self):
        # Dimanche 20h30 UTC (DST US) : calendrier DST-aware dit FERME
        # (ouverture à 21h00 UTC = 17h00 NY EDT), mais un snapshot très frais
        # et non-stale indique une activité live réelle (pré-ouverture anticipée
        # ou activité précoce, voir scripts/v9_supervisor.py).
        now = _utc(2026, 7, 5, 20, 30)
        fresh = {"created_at": (now - timedelta(seconds=40)).isoformat(), "stale": False}
        line = market_status_line(now, use_color=False, last_snapshot=fresh)
        assert "FERMÉ" in line
        assert "DST" in line

    def test_closed_with_stale_snapshot_no_warning(self):
        now = _utc(2026, 7, 5, 20, 30)
        stale = {"created_at": (now - timedelta(seconds=40)).isoformat(), "stale": True}
        line = market_status_line(now, use_color=False, last_snapshot=stale)
        assert line == "Marché : FERMÉ"


# ── âge d'un snapshot ──────────────────────────────────────
class TestSnapshotAge:
    def test_age_seconds_computed_correctly(self):
        now = _utc(2026, 7, 5, 12, 0)
        ts = (now - timedelta(seconds=45)).isoformat()
        age = snapshot_age_seconds(ts, now)
        assert abs(age - 45) < 0.001

    def test_age_handles_zulu_suffix(self):
        now = _utc(2026, 7, 5, 12, 0)
        ts = "2026-07-05T11:59:30Z"
        age = snapshot_age_seconds(ts, now)
        assert abs(age - 30) < 0.001

    def test_format_age_seconds(self):
        assert format_age(2) == "il y a 2s"

    def test_format_age_minutes(self):
        assert format_age(125) == "il y a 2min"

    def test_format_age_hours(self):
        assert format_age(3 * 3600 + 60) == "il y a 3h"


# ── badge stale / OK ───────────────────────────────────────
class TestStaleBadge:
    def test_stale_badge_no_color(self):
        assert stale_badge(True, use_color=False) == "STALE"
        assert stale_badge(False, use_color=False) == "OK"

    def test_stale_badge_with_color_wraps_ansi(self):
        badge = stale_badge(True, use_color=True)
        assert badge.startswith("\033[")
        assert "STALE" in badge

    def test_ok_badge_with_color_wraps_ansi(self):
        badge = stale_badge(False, use_color=True)
        assert badge.startswith("\033[")
        assert "OK" in badge


# ── formatage comportement ────────────────────────────────
class TestFormatBehaviorBlock:
    def test_none_behavior(self):
        result = format_behavior_block(None)
        assert "aucun comportement" in result.lower()

    def test_full_behavior_block(self):
        behavior = {
            "qualification": "bascule",
            "intensite": "forte",
            "phase": "developpement",
            "confiance_qualification": 74,
            "symbol": "GBPUSD",
            "timeframe": "M5",
            "description_courte": "Bascule USD->GBP apres contraction",
        }
        result = format_behavior_block(behavior)
        assert "bascule" in result
        assert "forte" in result
        assert "developpement" in result
        assert "74/100" in result
        assert "GBPUSD M5" in result
        assert "Bascule USD->GBP apres contraction" in result


# ── formatage fenêtre ──────────────────────────────────────
class TestFormatWindowBlock:
    def test_none_window(self):
        result = format_window_block(None)
        assert "aucune fenêtre" in result.lower()

    def test_open_window_block(self):
        window = {
            "statut": "ouverte",
            "type_fenetre": "retournement",
            "niveau_confiance": 68,
            "fragilite_detectee": False,
        }
        result = format_window_block(window)
        assert "ouverte" in result
        assert "retournement" in result
        assert "68/100" in result
        assert "non" in result

    def test_fragile_window_block(self):
        window = {
            "statut": "fragile",
            "type_fenetre": "continuation",
            "niveau_confiance": 40,
            "fragilite_detectee": True,
        }
        result = format_window_block(window)
        assert "Fragilité     : oui" in result

    def test_absente_window_type_fenetre_null(self):
        window = {
            "statut": "absente",
            "type_fenetre": None,
            "niveau_confiance": 12,
            "fragilite_detectee": False,
        }
        result = format_window_block(window)
        assert "Type          : -" in result
