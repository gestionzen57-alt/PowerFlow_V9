"""market_calendar.py — Calendrier de marché Forex, couche Forces (Phase 7).

Utilitaires purs (aucune I/O, aucune DB) pour déterminer si le marché Forex
est ouvert, quelle session est active, et convertir entre les trois
référentiels temporels du projet : UTC (référentiel DB), heure broker
(Tickmill/FTMO, GMT+3, envoyée brute par l'EA) et heure locale Paris
(CET/CEST, pour affichage opérateur).

Couche cognitive : ce module ne fait aucune lecture de forces, aucune
décision. Il sert uniquement de référentiel temporel partagé par
capture_server.py, les scripts de déploiement et les tests d'intégration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.v9.config import (
    BROKER_UTC_OFFSET_HOURS,
    LOCAL_TIMEZONE,
    MARKET_CLOSE_UTC_DAY,
    MARKET_CLOSE_UTC_HOUR,
    MARKET_OPEN_UTC_DAY,
    MARKET_OPEN_UTC_HOUR,
)

# Bornes de session, en heures UTC (bornes basses incluses, hautes exclues).
# "sydney" traverse minuit (21h -> 6h) : traité à part dans current_session.
_SYDNEY_START_HOUR = 21
_SYDNEY_END_HOUR = 6
_TOKYO_RANGE = (0, 9)
_LONDON_RANGE = (7, 16)
_NEW_YORK_RANGE = (12, 21)
_OVERLAP_LONDON_NY_RANGE = (12, 16)


def _ensure_utc(dt: datetime) -> datetime:
    """Retourne dt en UTC. Un datetime naïf est supposé déjà en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _in_range(hour: int, start: int, end: int) -> bool:
    return start <= hour < end


class MarketCalendar:
    """Calendrier de marché Forex — ouverture, session active, conversions."""

    @staticmethod
    def is_market_open(timestamp_utc: datetime) -> bool:
        """Le marché Forex est fermé le samedi, avant l'ouverture du dimanche
        soir (22h UTC) et après la fermeture du vendredi soir (22h UTC)."""
        ts = _ensure_utc(timestamp_utc)
        weekday = ts.weekday()  # Monday=0 ... Sunday=6
        hour = ts.hour

        if weekday == 5:  # Samedi : toujours fermé
            return False
        if weekday == MARKET_OPEN_UTC_DAY and hour < MARKET_OPEN_UTC_HOUR:
            return False  # Dimanche avant l'heure d'ouverture
        if weekday == MARKET_CLOSE_UTC_DAY and hour >= MARKET_CLOSE_UTC_HOUR:
            return False  # Vendredi après l'heure de fermeture
        return True

    @staticmethod
    def current_session(timestamp_utc: datetime) -> str:
        """Retourne la session active (ou "closed" si le marché est fermé).

        Priorité de résolution en cas de chevauchement (du plus spécifique au
        plus général) : overlap_london_ny > london > new_york > tokyo > sydney.
        """
        ts = _ensure_utc(timestamp_utc)

        if not MarketCalendar.is_market_open(ts):
            return "closed"

        hour = ts.hour

        if _in_range(hour, *_OVERLAP_LONDON_NY_RANGE):
            return "overlap_london_ny"
        if _in_range(hour, *_LONDON_RANGE):
            return "london"
        if _in_range(hour, *_NEW_YORK_RANGE):
            return "new_york"
        if _in_range(hour, *_TOKYO_RANGE):
            return "tokyo"
        if hour >= _SYDNEY_START_HOUR or hour < _SYDNEY_END_HOUR:
            return "sydney"
        return "closed"

    @staticmethod
    def next_open(timestamp_utc: datetime) -> datetime:
        """Retourne le prochain horaire d'ouverture (dimanche 22h UTC, ou
        l'heure configurée dans config.py), strictement après timestamp_utc."""
        ts = _ensure_utc(timestamp_utc)
        days_ahead = (MARKET_OPEN_UTC_DAY - ts.weekday()) % 7
        candidate = ts.replace(
            hour=MARKET_OPEN_UTC_HOUR, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        if candidate <= ts:
            candidate += timedelta(days=7)
        return candidate

    @staticmethod
    def broker_to_utc(broker_dt: datetime) -> datetime:
        """Convertit une heure broker (GMT+3, Tickmill/FTMO) en UTC."""
        if broker_dt.tzinfo is None:
            naive_utc = broker_dt - timedelta(hours=BROKER_UTC_OFFSET_HOURS)
            return naive_utc.replace(tzinfo=timezone.utc)
        broker_utc = broker_dt.astimezone(timezone.utc) - timedelta(
            hours=BROKER_UTC_OFFSET_HOURS
        )
        return broker_utc.replace(tzinfo=timezone.utc)

    @staticmethod
    def utc_to_broker(utc_dt: datetime) -> datetime:
        """Convertit une heure UTC en heure broker (GMT+3, Tickmill/FTMO)."""
        ts = _ensure_utc(utc_dt)
        return (ts + timedelta(hours=BROKER_UTC_OFFSET_HOURS)).replace(
            tzinfo=timezone.utc
        )

    @staticmethod
    def paris_to_utc(paris_dt: datetime) -> datetime:
        """Convertit une heure Paris (CET/CEST) en UTC, DST géré via zoneinfo."""
        paris_tz = ZoneInfo(LOCAL_TIMEZONE)
        if paris_dt.tzinfo is None:
            localized = paris_dt.replace(tzinfo=paris_tz)
        else:
            localized = paris_dt.astimezone(paris_tz)
        return localized.astimezone(timezone.utc)
