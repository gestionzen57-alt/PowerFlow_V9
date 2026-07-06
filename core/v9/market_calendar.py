"""market_calendar.py — Calendrier de marché Forex, couche Forces (Phase 7).

Utilitaires purs (aucune I/O, aucune DB) pour déterminer si le marché Forex
est ouvert, quelle session est active, et convertir entre les trois
référentiels temporels du projet : UTC (référentiel DB), heure broker
(Tickmill/FTMO, GMT+3, envoyée brute par l'EA) et heure locale Paris
(CET/CEST, pour affichage opérateur).

Couche cognitive : ce module ne fait aucune lecture de forces, aucune
décision. Il sert uniquement de référentiel temporel partagé par
capture_server.py, les scripts de déploiement et les tests d'intégration.

DST-aware (2026-07-07) : is_market_open() et next_open() calculent
dynamiquement l'heure d'ouverture/fermeture UTC en ancrant sur 17h00
heure de New York (America/New_York, zoneinfo). Cela couvre
automatiquement le passage EST (UTC-5, hiver) / EDT (UTC-4, DST US,
~mi-mars à début novembre). Les constantes MARKET_OPEN_UTC_HOUR /
MARKET_CLOSE_UTC_HOUR de config.py sont conservées pour l'affichage
(runbook, dashboard) mais ne pilotent plus la logique booléenne.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.v9.config import (
    BROKER_UTC_OFFSET_HOURS,
    LOCAL_TIMEZONE,
    MARKET_CLOSE_UTC_DAY,
    MARKET_OPEN_UTC_DAY,
)

# Fuseau de référence pour l'heure d'ouverture/fermeture du marché Forex.
# Le marché ouvre et ferme à 17h00 heure de New York (invariant DST).
_NY_TZ = ZoneInfo("America/New_York")
_MARKET_OPEN_NY_HOUR = 17   # 17h00 NY = heure d'ouverture/fermeture réelle
_MARKET_OPEN_NY_WEEKDAY = 6  # Dimanche (Python: Monday=0 ... Sunday=6)
_MARKET_CLOSE_NY_WEEKDAY = 4  # Vendredi

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


def _market_open_utc_hour(date_utc: datetime) -> int:
    """Retourne l'heure UTC d'ouverture du marché pour une date donnée.

    Ancre sur 17h00 America/New_York : retourne 21 en DST US (EDT, UTC-4)
    ou 22 en heure standard US (EST, UTC-5).
    """
    # On construit un datetime NY à 17h00 le même jour que date_utc
    # pour obtenir l'offset DST correct.
    ny_dt = datetime(date_utc.year, date_utc.month, date_utc.day,
                     _MARKET_OPEN_NY_HOUR, 0, 0, tzinfo=_NY_TZ)
    utc_dt = ny_dt.astimezone(timezone.utc)
    return utc_dt.hour


class MarketCalendar:
    """Calendrier de marché Forex — ouverture, session active, conversions."""

    @staticmethod
    def is_market_open(timestamp_utc: datetime) -> bool:
        """Le marché Forex est fermé le samedi, avant l'ouverture du dimanche
        soir (17h00 NY, DST-aware) et après la fermeture du vendredi soir
        (17h00 NY, DST-aware)."""
        ts = _ensure_utc(timestamp_utc)
        weekday = ts.weekday()  # Monday=0 ... Sunday=6
        hour = ts.hour

        if weekday == 5:  # Samedi : toujours fermé
            return False

        open_utc_hour = _market_open_utc_hour(ts)

        if weekday == _MARKET_OPEN_NY_WEEKDAY and hour < open_utc_hour:
            return False  # Dimanche avant l'heure d'ouverture NY
        if weekday == _MARKET_CLOSE_NY_WEEKDAY and hour >= open_utc_hour:
            return False  # Vendredi après l'heure de fermeture NY
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
        """Retourne le prochain horaire d'ouverture (dimanche 17h00 NY,
        DST-aware), strictement après timestamp_utc."""
        ts = _ensure_utc(timestamp_utc)
        days_ahead = (_MARKET_OPEN_NY_WEEKDAY - ts.weekday()) % 7
        # Construire le candidat : dimanche de la semaine courante ou suivante
        candidate_date = ts.date() + timedelta(days=days_ahead)
        # 17h00 NY ce dimanche-là, avec offset DST correct
        candidate_ny = datetime(
            candidate_date.year, candidate_date.month, candidate_date.day,
            _MARKET_OPEN_NY_HOUR, 0, 0, tzinfo=_NY_TZ
        )
        candidate = candidate_ny.astimezone(timezone.utc)
        if candidate <= ts:
            candidate_ny_next = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                _MARKET_OPEN_NY_HOUR, 0, 0, tzinfo=_NY_TZ
            ) + timedelta(days=7)
            # Reconstruire avec le bon offset DST de la semaine suivante
            next_date = candidate_date + timedelta(days=7)
            candidate_ny_next = datetime(
                next_date.year, next_date.month, next_date.day,
                _MARKET_OPEN_NY_HOUR, 0, 0, tzinfo=_NY_TZ
            )
            candidate = candidate_ny_next.astimezone(timezone.utc)
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
