"""Tests — core/v9/market_calendar.py (Phase 7, calendrier de marché).

DST-aware depuis 2026-07-07 : is_market_open() ancre sur 17h00
America/New_York. En DST US (EDT, UTC-4) l'ouverture est à 21h UTC ;
en heure standard (EST, UTC-5) elle est à 22h UTC.
"""

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
        # 2026-07-05 est un dimanche, DST US actif (EDT, UTC-4)
        # Ouverture réelle = 17h NY = 21h UTC en EDT
        # 20h UTC = toujours fermé (avant 21h EDT ou avant 22h EST)
        assert MarketCalendar.is_market_open(_utc(2026, 7, 5, 20)) is False

    def test_sunday_at_open_open_dst(self):
        # 2026-07-05 DST US actif (EDT, UTC-4) : ouverture à 21h UTC
        assert MarketCalendar.is_market_open(_utc(2026, 7, 5, 21)) is True

    def test_sunday_at_open_open_standard(self):
        # 2026-01-04 heure standard US (EST, UTC-5) : ouverture à 22h UTC
        assert MarketCalendar.is_market_open(_utc(2026, 1, 4, 22)) is True

    def test_sunday_before_open_standard(self):
        # 2026-01-04 heure standard US (EST, UTC-5) : 21h UTC encore fermé
        assert MarketCalendar.is_market_open(_utc(2026, 1, 4, 21)) is False

    def test_friday_before_close_open(self):
        # 2026-07-03 est un vendredi, DST US (EDT) : fermeture à 21h UTC
        # 20h UTC = encore ouvert
        assert MarketCalendar.is_market_open(_utc(2026, 7, 3, 20)) is True

    def test_friday_after_close_closed_dst(self):
        # 2026-07-03 vendredi DST (EDT, UTC-4) : fermeture à 21h UTC
        assert MarketCalendar.is_market_open(_utc(2026, 7, 3, 21)) is False

    def test_friday_after_close_closed_standard(self):
        # 2026-01-02 vendredi heure standard (EST, UTC-5) : fermeture à 22h UTC
        assert MarketCalendar.is_market_open(_utc(2026, 1, 2, 22)) is False

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
    def test_from_saturday_returns_next_sunday_dst_correct_hour(self):
        # 2026-07-04 samedi DST US (EDT, UTC-4) : next_open = dimanche 21h UTC
        result = MarketCalendar.next_open(_utc(2026, 7, 4, 12))
        assert result.weekday() == 6  # dimanche
        assert result.hour in {21, 22}  # 21h EDT ou 22h EST selon période
        assert result.minute == 0
        # En DST US (juillet) : doit être 21h UTC
        assert result.hour == 21

    def test_from_saturday_returns_next_sunday_standard_correct_hour(self):
        # 2026-01-03 samedi heure standard US (EST, UTC-5) : next_open = dimanche 22h UTC
        result = MarketCalendar.next_open(_utc(2026, 1, 3, 12))
        assert result.weekday() == 6  # dimanche
        assert result.hour == 22
        assert result.minute == 0

    def test_from_open_market_returns_following_week(self):
        # 2026-07-05 dimanche 22h UTC (marché déjà ouvert) -> dimanche suivant
        result = MarketCalendar.next_open(_utc(2026, 7, 5, 22))
        assert result.weekday() == 6
        assert result > _utc(2026, 7, 5, 22)

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
        # Dimanche 23h Paris (CEST, UTC+2) = 21h UTC
        # En DST US (EDT, UTC-4) : 21h UTC = heure d'ouverture exacte -> ouvert
        paris_dt = datetime(2026, 7, 5, 23, 0)  # dimanche été
        result = MarketCalendar.paris_to_utc(paris_dt)
        assert result == _utc(2026, 7, 5, 21)
        assert MarketCalendar.is_market_open(result) is True

    def test_market_open_sunday_winter(self):
        # Dimanche 23h Paris (CET, UTC+1) = 22h UTC
        # En EST (UTC-5) : 22h UTC = heure d'ouverture -> ouvert
        paris_dt = datetime(2026, 1, 4, 23, 0)  # dimanche hiver
        result = MarketCalendar.paris_to_utc(paris_dt)
        assert result == _utc(2026, 1, 4, 22)
        assert MarketCalendar.is_market_open(result) is True
