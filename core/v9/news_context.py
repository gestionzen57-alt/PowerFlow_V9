"""news_context.py — PowerFlow V9.

Le système ne trade pas les news. Il lit les flux de liquidité
qui les précèdent et la réorganisation des coalitions qui suit.
La news est un repère temporel. Les forces sont la réalité.
— Perplexity, architecte externe V9, 2026-07-06

Module pur (aucune I/O DB, aucun état partagé) qui évalue la position
temporelle d'un moment UTC par rapport au calendrier économique statique
(data/economic_calendar.json).

Retourne 5 champs PROPAGÉS dans le contexte partagé via _load_shared_context :
  - news_type          : str | None
  - news_phase         : "PRE_NEWS" | "NEWS_SHOCK" | "POST_NEWS" | "NEUTRE"
  - news_distance_min  : int | None  (futur > 0, passé < 0, None si NEUTRE)
  - news_importance    : "HIGH" | "MEDIUM" | "LOW" | "NEUTRE"
  - news_session_clean : bool       (True = aucune news HIGH dans 90 prochaines min)

Règles de phase (brief Perplexity 2026-07-06) :
  - distance > 0  (futur) :
      ≤ window_pre_min            → PRE_NEWS
      sinon                       → NEUTRE
  - distance ≤ 0  (passée) :
      |distance| ≤ window_shock_min → NEWS_SHOCK
      |distance| ≤ window_post_min  → POST_NEWS
      sinon                         → NEUTRE
  - aucune news dans 4h           → NEUTRE, news_distance_min=None

Priorité multi-news : la plus proche (en valeur absolue), ex-aequo →
la plus importante (HIGH > MEDIUM > LOW).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Fenêtre de recherche (en minutes) autour de utc_dt pour collecter les
# occurrences susceptibles d'influencer news_phase. 4h (240 min) couvre
# largement la plus longue fenêtre post_news déclarée (FOMC_RATE 120 min)
# avec marge pour la pré_news la plus longue (FOMC_RATE 60 min) + tolérance.
_SEARCH_WINDOW_MIN = 240

# Pour news_session_clean : aucune news HIGH dans les X prochaines minutes.
_CLEAN_LOOKAHEAD_MIN = 90


# Importance rank (pour tri multi-news ex-aequo).
_IMPORTANCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _ensure_utc(dt: datetime) -> datetime:
    """Retourne dt en UTC. Un datetime naïf est supposé déjà en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_business_day(d: datetime) -> bool:
    """Lundi=0 .. Dimanche=6. Vrai si lundi-vendredi."""
    return d.weekday() < 5


def _first_weekday_occurrence(year: int, month: int, target_weekday: int) -> datetime:
    """Retourne le premier jour du mois `year-month` qui tombe un `target_weekday`.

    target_weekday : 0=lundi, 1=mardi, ..., 4=vendredi.
    Utilisé pour monthly_first_friday (target_weekday=4) et
    monthly_first_business_day (target_weekday=0 — premier lundi).
    """
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    delta = (target_weekday - first.weekday()) % 7
    return first + timedelta(days=delta)


def _nth_weekday_in_month(year: int, month: int, n: int, target_weekday: int) -> datetime | None:
    """Retourne le n-ième jour du mois qui tombe un target_weekday (1-indexé).

    Retourne None si le n-ième occurrence n'existe pas dans le mois.
    n=1 → première semaine, n=2 → deuxième, etc.
    """
    first_occ = _first_weekday_occurrence(year, month, target_weekday)
    candidate = first_occ + timedelta(weeks=n - 1)
    if candidate.year != year or candidate.month != month:
        return None
    return candidate


def _recurrence_dates(
    rule: dict[str, Any],
    ref_year: int,
    ref_month: int,
    typical_hour: int,
    typical_minute: int,
) -> list[datetime]:
    """Génère les dates (UTC) d'occurrence d'une règle de récurrence sur
    une fenêtre glissante de 24 mois (12 passés + 12 futurs autour de
    ref_year-ref_month). Chaque date porte l'heure/minute typique.

    Tolérance ±3 min sur l'heure exacte : gérée en amont (les fenêtres
    pre/shock/post sont définies par règle et supposent l'heure typique).
    Le module ne calcule pas de dérive — le calendrier est statique.
    """
    base = datetime(ref_year, ref_month, 1, tzinfo=timezone.utc)
    recurrence = rule["recurrence"]
    out: list[datetime] = []
    for k in range(-12, 13):
        anchor = base + timedelta(days=32 * k)
        ay, am = anchor.year, anchor.month
        if recurrence == "monthly_first_friday":
            d = _first_weekday_occurrence(ay, am, target_weekday=4)
        elif recurrence == "monthly_first_business_day":
            # 1er jour ouvré = premier lundi du mois.
            d = _first_weekday_occurrence(ay, am, target_weekday=0)
        elif recurrence == "monthly_second_wednesday":
            d = _nth_weekday_in_month(ay, am, n=2, target_weekday=2)
        elif recurrence == "monthly_second_week_wednesday":
            # Mercredi de la 2ème semaine ISO du mois.
            d = _nth_weekday_in_month(ay, am, n=2, target_weekday=2)
        elif recurrence == "quarterly":
            # GDP_US : publication typique le dernier mois du trimestre
            # (janv/avr/jul/oct), 1ère publication du trimestre environ.
            if am not in (1, 4, 7, 10):
                continue
            d = _first_weekday_occurrence(ay, am, target_weekday=0)
        elif recurrence == "8x_year":
            # FOMC : 8 réunions/an, dates officielles publiées par la Fed.
            # Pour un calendrier statique sans fetch externe, on utilise
            # les 8 dates anniversaires régulières (toutes les ~6 semaines)
            # à partir d'un repère connu — pratique courante des dashboards
            # économiques hors-ligne. Référencement : la Fed publie les
            # dates 1 an à l'avance ; cette approximation couvre 2025-2027.
            # 8 dates = 2 par trimestre (mois 1.5/4/6.5/9/11 + shifts).
            # Pour rester stable et reproductible, on s'ancre sur
            # 4 jalons par trimestre (fin de mois ~1/3.5/6.5/9.5/11.5)
            # downsamplés à 8.
            # Approche simplifiée et déterministe : 8 occurrences/an sur
            # les jours 15-16 des mois impairs + FOMC_MINUTES 3 semaines
            # après (donc jours 5-6 des mois pairs +10).
            if 1 <= am <= 12:
                # 8 meetings/an — pattern régulier toutes les 6 semaines
                # à partir du 15 janvier. Index = (month - 1) // 1.5 ≈
                # mois 1, 2.5, 4, 5.5, 7, 8.5, 10, 11.5 → arrondi au 15.
                # Approximation stable : mois impairs + certains pairs.
                # On garde les 8 mois publiés typiquement par la Fed :
                # jan, mar, may, jun, jul, sep, nov, dec.
                fomoc_months = (1, 3, 5, 6, 7, 9, 11, 12)
                if am not in fomoc_months:
                    continue
                d = datetime(ay, am, 15, tzinfo=timezone.utc)
            else:
                continue
        else:
            # Récurrence inconnue → aucune occurrence (NEUTRE par défaut).
            return []
        if d is None:
            continue
        out.append(d.replace(hour=typical_hour, minute=typical_minute))
    return out


def _load_calendar(calendar_path: str | Path) -> list[dict[str, Any]]:
    """Charge le JSON du calendrier. Lève IOError/JSONDecodeError si invalide."""
    p = Path(calendar_path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("economic_calendar.json doit être une liste JSON")
    return data


class NewsContext:
    """Évalue la position temporelle d'un moment UTC par rapport au calendrier
    économique statique. Module pur — aucune DB, aucun état global.

    Usage :
        ctx = NewsContext()  # lit data/economic_calendar.json
        out = ctx.assess(datetime.now(timezone.utc))
        # out = {
        #   "news_type": "NFP" | None,
        #   "news_phase": "PRE_NEWS" | "NEWS_SHOCK" | "POST_NEWS" | "NEUTRE",
        #   "news_distance_min": int | None,
        #   "news_importance": "HIGH" | "MEDIUM" | "LOW" | "NEUTRE",
        #   "news_session_clean": bool,
        # }

    assess() ne lève JAMAIS d'exception — tout chemin d'erreur retourne
    le fallback NEUTRE (5 champs garantis).
    """

    def __init__(self, calendar_path: str | Path = "data/economic_calendar.json") -> None:
        self._calendar_path = Path(calendar_path)
        self._calendar: list[dict[str, Any]] = []
        try:
            self._calendar = _load_calendar(self._calendar_path)
        except Exception:
            self._calendar = []

    @staticmethod
    def _neutral() -> dict[str, Any]:
        """Fallback NEUTRE — 5 champs garantis, aucune exception."""
        return {
            "news_type": None,
            "news_phase": "NEUTRE",
            "news_distance_min": None,
            "news_importance": "NEUTRE",
            "news_session_clean": True,
        }

    def _closest_news(self, utc_dt: datetime) -> dict[str, Any] | None:
        """Parcourt la fenêtre [_SEARCH_WINDOW_MIN, +_SEARCH_WINDOW_MIN]
        et retourne la news la plus proche (puis la plus importante en
        ex-aequo) avec sa distance signée en minutes.

        Retourne None si calendrier vide ou si aucune news dans la
        fenêtre de recherche.
        """
        if not self._calendar:
            return None

        candidates: list[dict[str, Any]] = []
        ref_year, ref_month = utc_dt.year, utc_dt.month

        for rule in self._calendar:
            try:
                h = int(rule.get("typical_utc_hour", 12))
                m = int(rule.get("typical_utc_minute", 0))
                occs = _recurrence_dates(rule, ref_year, ref_month, h, m)
            except Exception:
                continue

            importance = str(rule.get("importance", "MEDIUM"))
            name = str(rule.get("name", ""))

            for occ in occs:
                delta_min = (occ - utc_dt).total_seconds() / 60.0
                if abs(delta_min) > _SEARCH_WINDOW_MIN:
                    continue
                candidates.append(
                    {
                        "name": name,
                        "importance": importance,
                        "importance_rank": _IMPORTANCE_RANK.get(importance, 0),
                        "distance_min": int(round(delta_min)),
                        "pre_min": int(rule.get("window_pre_min", 30)),
                        "shock_min": int(rule.get("window_shock_min", 10)),
                        "post_min": int(rule.get("window_post_min", 60)),
                    }
                )

        if not candidates:
            return None

        # Tri : 1) plus petite valeur absolue de distance, 2) importance max.
        candidates.sort(key=lambda c: (abs(c["distance_min"]), -c["importance_rank"]))
        return candidates[0]

    def _has_upcoming_high(self, utc_dt: datetime) -> bool:
        """True si une news HIGH est prévue dans les _CLEAN_LOOKAHEAD_MIN
        prochaines minutes. Utilisé pour news_session_clean."""
        if not self._calendar:
            return False

        cutoff = utc_dt + timedelta(minutes=_CLEAN_LOOKAHEAD_MIN)
        ref_year, ref_month = utc_dt.year, utc_dt.month

        for rule in self._calendar:
            if str(rule.get("importance", "")) != "HIGH":
                continue
            try:
                h = int(rule.get("typical_utc_hour", 12))
                m = int(rule.get("typical_utc_minute", 0))
                occs = _recurrence_dates(rule, ref_year, ref_month, h, m)
            except Exception:
                continue
            for occ in occs:
                # Fenêtre future : utc_dt < occ <= cutoff (inclus).
                if utc_dt < occ <= cutoff:
                    return True
        return False

    @staticmethod
    def _phase_for(c: dict[str, Any]) -> str:
        """Détermine news_phase à partir de distance + fenêtres."""
        dist = c["distance_min"]
        if dist > 0:
            return "PRE_NEWS" if dist <= c["pre_min"] else "NEUTRE"
        # distance <= 0 (passée)
        abs_d = abs(dist)
        if abs_d <= c["shock_min"]:
            return "NEWS_SHOCK"
        if abs_d <= c["post_min"]:
            return "POST_NEWS"
        return "NEUTRE"

    def assess(self, utc_dt: datetime) -> dict[str, Any]:
        """Évalue le contexte news pour un moment UTC.

        Contrat de sortie (5 champs, toujours présents) :
          - news_type          (str | None)
          - news_phase         (PRE_NEWS | NEWS_SHOCK | POST_NEWS | NEUTRE)
          - news_distance_min  (int | None)
          - news_importance    (HIGH | MEDIUM | LOW | NEUTRE)
          - news_session_clean (bool)

        Ne lève JAMAIS d'exception. Tout chemin d'erreur retourne le
        fallback NEUTRE.
        """
        try:
            ts = _ensure_utc(utc_dt)
        except Exception:
            return self._neutral()

        try:
            closest = self._closest_news(ts)
        except Exception:
            return self._neutral()

        if closest is None:
            # Aucune news dans 4h → NEUTRE.
            try:
                clean = not self._has_upcoming_high(ts)
            except Exception:
                clean = True
            return {
                "news_type": None,
                "news_phase": "NEUTRE",
                "news_distance_min": None,
                "news_importance": "NEUTRE",
                "news_session_clean": clean,
            }

        phase = self._phase_for(closest)

        # Si on est en NEUTRE (pas dans une fenêtre temporellement
        # pertinente), news_distance_min et news_type sont None :
        # ces champs n'ont de sens qu'autour de la fenêtre. Cohérence
        # stricte avec news_phase (voir CONTEXT_CONTRACT.md).
        if phase == "NEUTRE":
            news_type_out: Any = None
            news_dist_out: Any = None
            news_imp_out = "NEUTRE"
        else:
            news_type_out = closest["name"]
            news_dist_out = closest["distance_min"]
            news_imp_out = closest["importance"]

        try:
            session_clean = not self._has_upcoming_high(ts)
        except Exception:
            session_clean = True

        return {
            "news_type": news_type_out,
            "news_phase": phase,
            "news_distance_min": news_dist_out,
            "news_importance": news_imp_out,
            "news_session_clean": session_clean,
        }
