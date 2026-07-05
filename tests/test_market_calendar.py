"""Tests — core/v9/market_calendar.py (Phase 7, calendrier de marché)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.v9.market_calendar import MarketCalendar


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ── is_market_open ────────────────────────────────────────
class TestIsMarketOpen:
    def test_saturday_closed(self):
        # 2026-07-04 est un samedi
        assert MarketCalendar.is_market_open(_utc(2026, 7, 4, 12)) is False

    def test_sunday_before_open_closed(self):
        # 2026-07-05 est un dimanche
        assert MarketCalendar.is_market_open(_utc(2026, 7, 5, 21)) is False

    def test_sunday_at_open_open(self):
        assert MarketCalendar.is_market_open(_utc(2026, 7, 5, 22)) is True

    def test_friday_before_close_open(self):
        # 2026-07-03 est un vendredi
        assert MarketCalendar.is_market_open(_utc(2026, 7, 3, 21)) is True

    def test_friday_after_close_closed(self):
        assert MarketCalendar.is_market_open(_utc(2026, 7, 3, 23)) is False

    def test_naive_datetime_treated_as_utc(self):
        assert MarketCalendar.is_market_open(datetime(2026, 7, 4, 12)) is False

    def test_midweek_open(self):
        # 2026-07-08 est un mercredi
        assert MarketCalendar.is_market_open(_utc(2026, 7, 8, 15)) is True


# ── current_session ───────────────────────────────────────
class TestCurrentSession:
    def test_10h_utc_is_london(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 8, 10)) == "london"

    def test_14h_utc_is_overlap(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 8, 14)) == "overlap_london_ny"

    def test_3h_utc_is_tokyo(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 8, 3)) == "tokyo"

    def test_18h_utc_is_new_york(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 8, 18)) == "new_york"

    def test_22h_utc_is_sydney(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 8, 22)) == "sydney"

    def test_closed_market_returns_closed(self):
        assert MarketCalendar.current_session(_utc(2026, 7, 4, 12)) == "closed"


# ── next_open ──────────────────────────────────────────────
class TestNextOpen:
    def test_from_saturday_returns_next_sunday_22h(self):
        result = MarketCalendar.next_open(_utc(2026, 7, 4, 12))
        assert result == _utc(2026, 7, 5, 22)

    def test_from_open_market_returns_following_week(self):
        result = MarketCalendar.next_open(_utc(2026, 7, 5, 23))
        assert result == _utc(2026, 7, 12, 22)

    def test_result_is_strictly_after_input(self):
        ts = _utc(2026, 7, 5, 22)
        result = MarketCalendar.next_open(ts)
        assert result > ts


# ── broker_to_utc / utc_to_broker ─────────────────────────
class TestBrokerConversion:
    def test_broker_to_utc_subtracts_offset(self):
        broker_dt = datetime(2026, 7, 8, 15, 0)  # heure broker (naive, GMT+3)
        result = MarketCalendar.broker_to_utc(broker_dt)
        assert result == _utc(2026, 7, 8, 12)

    def test_utc_to_broker_adds_offset(self):
        utc_dt = _utc(2026, 7, 8, 12)
        result = MarketCalendar.utc_to_broker(utc_dt)
        assert result == _utc(2026, 7, 8, 15)

    def test_roundtrip(self):
        utc_dt = _utc(2026, 7, 8, 9, 30)
        broker_dt = MarketCalendar.utc_to_broker(utc_dt)
        back = MarketCalendar.broker_to_utc(broker_dt)
        assert back == utc_dt


# ── paris_to_utc ───────────────────────────────────────────
class TestParisToUtc:
    def test_summer_cest_is_utc_plus_2(self):
        # 2026-07-08 : heure d'été (CEST, UTC+2)
        paris_dt = datetime(2026, 7, 8, 14, 0)
        result = MarketCalendar.paris_to_utc(paris_dt)
        assert result == _utc(2026, 7, 8, 12)

    def test_winter_cet_is_utc_plus_1(self):
        # 2026-01-08 : heure d'hiver (CET, UTC+1)
        paris_dt = datetime(2026, 1, 8, 14, 0)
        result = MarketCalendar.paris_to_utc(paris_dt)
        assert result == _utc(2026, 1, 8, 13)

    def test_market_open_sunday_23h_paris_cest(self):
        # Dimanche 23h Paris (CEST, UTC+2) = 21h UTC -> marche encore ferme.
        # L'ouverture reelle a lieu a 23h Paris seulement en heure d'hiver
        # (22h UTC = 23h CET). En ete, 22h UTC = minuit Paris (CEST).
        paris_dt = datetime(2026, 1, 4, 23, 0)  # dimanche hiver
        result = MarketCalendar.paris_to_utc(paris_dt)
        assert result == _utc(2026, 1, 4, 22)
        assert MarketCalendar.is_market_open(result) is True
