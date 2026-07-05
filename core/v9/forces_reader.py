"""ForcesReader — transforme le JSON brut de l'EA MT4 en format V9.

Aligné sur docs/architecture/formats/FORMAT_FORCES.md. Ne contient aucune
logique de trading. Applique le STALE_GATE (core.v9.stale_gate) et garde
en mémoire l'état précédent par (devise, timeframe) pour calculer les
champs dérivés (direction, vitesse, croisement, recroisement,
rejet_repulsion, compression_extension).

Convention de correspondance pair -> devises : le symbole MT4 reçu
(ex: "GBPUSD") est décomposé en devise de base ("GBP") et devise de
contrepartie ("USD"). Les champs direction/vitesse/croisement/
recroisement/rejet_repulsion de la ligne retournée décrivent la devise
de base, ce qui correspond à la lecture naturelle du graphique observé
par la sonde EA (1 instance par timeframe sur un symbole donné).
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from core.v9.config import (
    COMPRESSION_RATIO,
    COMPRESSION_WINDOW_BARS,
    DEVISES,
    EXTENSION_RATIO,
    FORCE_KEYS,
    RECROISEMENT_LOOKBACK_BARS,
    REJET_EXTREME_WINDOW_BARS,
    REJET_MIN_REBOUND,
    SCHEMA_VERSION,
    TIMEFRAME_TICK,
    TIMEFRAMES_CANDLE,
)
from core.v9.stale_gate import StaleGate, to_epoch_ms

REQUIRED_FIELDS = ["symbol", "timeframe"] + FORCE_KEYS


@dataclass
class ForceState:
    intensite: float
    time_ref_s: float


class ForcesReaderError(ValueError):
    """Erreur de validation du JSON brut reçu de l'EA."""


class ForcesReader:
    """Transforme un message brut EA en ligne prête pour forces_snapshots."""

    def __init__(self, stale_gate: StaleGate | None = None) -> None:
        self.stale_gate = stale_gate or StaleGate()
        self._last_force: dict[tuple[str, str], ForceState] = {}
        self._croisement_history: dict[tuple[str, str, str], deque[str]] = {}
        self._force_history: dict[tuple[str, str], deque[float]] = {}
        self._amplitude_history: dict[str, deque[float]] = {}
        self._tick_windows: dict[tuple[str, str], list[int]] = {}

    # ── Validation ────────────────────────────────────────
    @staticmethod
    def validate(raw: dict) -> None:
        missing = [f for f in REQUIRED_FIELDS if f not in raw]
        if missing:
            raise ForcesReaderError(f"champs obligatoires manquants: {missing}")

        timeframe = str(raw["timeframe"])
        if timeframe not in TIMEFRAMES_CANDLE and timeframe not in TIMEFRAME_TICK:
            raise ForcesReaderError(f"timeframe inconnu: {timeframe!r}")

        if "timestamp" not in raw and "capture_time" not in raw:
            raise ForcesReaderError(
                "aucun horodatage exploitable (timestamp ou capture_time requis)"
            )

    @staticmethod
    def _extract_pair(symbol: str) -> tuple[str | None, str | None]:
        letters = "".join(ch for ch in symbol.upper() if ch.isalpha())
        if len(letters) < 6:
            return None, None
        base, quote = letters[:3], letters[3:6]
        if base in DEVISES and quote in DEVISES:
            return base, quote
        return None, None

    @staticmethod
    def _capture_timestamp(raw: dict) -> str | int | float:
        return raw.get("timestamp") or raw["capture_time"]

    # ── Transformation ────────────────────────────────────
    def transform(self, raw: dict, now_ms: int | None = None) -> dict:
        """Transforme un message brut EA en dict prêt pour insertion DB.

        Retourne {"row": {...colonnes forces_snapshots...},
                   "format_forces_entry": {...entrée FORMAT_FORCES.md...}}.
        """
        self.validate(raw)
        timeframe = str(raw["timeframe"])
        if timeframe in TIMEFRAME_TICK:
            return self._transform_tick(raw, timeframe, now_ms)
        return self._transform_candle(raw, timeframe, now_ms)

    def _base_row(self, raw: dict, timeframe: str, freshness: dict) -> dict:
        forces = {d: float(raw[f"force_{d.lower()}"]) for d in DEVISES}
        capture_ts = self._capture_timestamp(raw)
        now = (
            datetime.now(timezone.utc).isoformat()
        )
        return {
            "snapshot_id": raw.get("snapshot_id") or f"v9-{uuid.uuid4()}",
            "schema_version": raw.get("schema_version", SCHEMA_VERSION),
            "timestamp": raw.get("timestamp") or _ms_to_iso(to_epoch_ms(capture_ts)),
            "source": raw.get("source", "MT4_SDI"),
            "symbol": raw["symbol"],
            "timeframe": timeframe,
            "bar_time": raw.get("bar_time"),
            "bar_close_time": raw.get("bar_close_time"),
            "server_time": raw.get("server_time"),
            "capture_time": raw.get("capture_time"),
            "shift": raw.get("shift"),
            "is_closed_bar": bool(raw.get("is_closed_bar", timeframe not in TIMEFRAME_TICK)),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "close": raw.get("close"),
            "tick_volume": raw.get("tick_volume"),
            "spread_points": raw.get("spread_points"),
            "spread_price": raw.get("spread_price"),
            "bid": raw.get("bid"),
            "ask": raw.get("ask"),
            "mid": raw.get("mid"),
            "force_usd": forces["USD"],
            "force_gbp": forces["GBP"],
            "force_eur": forces["EUR"],
            "force_jpy": forces["JPY"],
            "force_cad": forces["CAD"],
            "force_chf": forces["CHF"],
            "force_aud": forces["AUD"],
            "force_nzd": forces["NZD"],
            "direction": "neutre",
            "vitesse": 0.0,
            "croisement_detecte": False,
            "croisement_partenaire": None,
            "croisement_direction": None,
            "recroisement_detecte": False,
            "recroisement_contexte": None,
            "rejet_repulsion_detecte": False,
            "rejet_intensite": None,
            "compression_extension_etat": "neutre",
            "compression_extension_intensite": 0.0,
            "stale": freshness["stale"],
            "age_ms": freshness["age_ms"],
            "stale_threshold_ms": freshness["stale_threshold_ms"],
            "created_at": now,
        }, forces

    def _transform_candle(self, raw: dict, timeframe: str, now_ms: int | None) -> dict:
        capture_ts = self._capture_timestamp(raw)
        freshness = self.stale_gate.check_freshness(capture_ts, timeframe, now_ms=now_ms)
        row, forces = self._base_row(raw, timeframe, freshness)

        symbol = raw["symbol"]
        base, quote = self._extract_pair(symbol)
        bar_time = raw.get("bar_time")
        time_ref_s = float(bar_time) if bar_time is not None else to_epoch_ms(capture_ts) / 1000.0

        prev_base = self._last_force.get((base, timeframe)) if base else None
        prev_quote = self._last_force.get((quote, timeframe)) if quote else None

        # direction + vitesse (devise de base du symbole)
        if base and prev_base is not None:
            current_val = forces[base]
            delta = current_val - prev_base.intensite
            delta_t = time_ref_s - prev_base.time_ref_s
            row["direction"] = _direction_from_delta(delta)
            row["vitesse"] = delta / delta_t if delta_t > 0 else 0.0

        # croisement (base vs quote)
        croisement_direction = None
        if base and quote and prev_base is not None and prev_quote is not None:
            prev_diff = prev_base.intensite - prev_quote.intensite
            curr_diff = forces[base] - forces[quote]
            if prev_diff != 0 and curr_diff != 0 and (prev_diff > 0) != (curr_diff > 0):
                croisement_direction = "haussiere" if curr_diff > 0 else "baissiere"
                row["croisement_detecte"] = True
                row["croisement_partenaire"] = quote
                row["croisement_direction"] = croisement_direction

        # recroisement : un croisement inverse à un croisement récent
        if base and quote:
            pair_key = (base, quote, timeframe)
            history = self._croisement_history.setdefault(
                pair_key, deque(maxlen=RECROISEMENT_LOOKBACK_BARS)
            )
            if croisement_direction is not None:
                for past_direction in history:
                    if past_direction != croisement_direction:
                        row["recroisement_detecte"] = True
                        row["recroisement_contexte"] = (
                            f"recroisement {croisement_direction} apres croisement "
                            f"{past_direction} recent entre {base} et {quote}"
                        )
                        break
                history.append(croisement_direction)

        # rejet_repulsion : rebond depuis un extrême local de la devise de base
        if base:
            fhist_key = (base, timeframe)
            fhist = self._force_history.setdefault(
                fhist_key, deque(maxlen=REJET_EXTREME_WINDOW_BARS)
            )
            current_val = forces[base]
            if len(fhist) >= 2:
                prev_val = fhist[-1]
                window_max = max(fhist)
                window_min = min(fhist)
                rebound = current_val - prev_val
                if prev_val >= window_max and rebound <= -REJET_MIN_REBOUND:
                    row["rejet_repulsion_detecte"] = True
                    row["rejet_intensite"] = abs(rebound)
                elif prev_val <= window_min and rebound >= REJET_MIN_REBOUND:
                    row["rejet_repulsion_detecte"] = True
                    row["rejet_intensite"] = abs(rebound)
            fhist.append(current_val)

        # compression_extension : amplitude des 8 forces vs moyenne mobile
        amplitude = max(forces.values()) - min(forces.values())
        amp_hist = self._amplitude_history.setdefault(
            timeframe, deque(maxlen=COMPRESSION_WINDOW_BARS)
        )
        avg = sum(amp_hist) / len(amp_hist) if amp_hist else amplitude
        if avg > 0 and amplitude > avg * EXTENSION_RATIO:
            etat = "extension"
        elif avg > 0 and amplitude < avg * COMPRESSION_RATIO:
            etat = "compression"
        else:
            etat = "neutre"
        row["compression_extension_etat"] = etat
        row["compression_extension_intensite"] = round(abs(amplitude - avg), 4)
        amp_hist.append(amplitude)

        # mise à jour de l'état mémoire pour les 8 devises de ce timeframe
        for devise in DEVISES:
            self._last_force[(devise, timeframe)] = ForceState(
                intensite=forces[devise], time_ref_s=time_ref_s
            )

        entry = _build_format_forces_entry_candle(row, base or symbol)
        return {"row": row, "format_forces_entry": entry}

    def _transform_tick(self, raw: dict, timeframe: str, now_ms: int | None) -> dict:
        capture_ts = self._capture_timestamp(raw)
        freshness = self.stale_gate.check_freshness(capture_ts, timeframe, now_ms=now_ms)
        row, forces = self._base_row(raw, timeframe, freshness)

        symbol = raw["symbol"]
        base, _quote = self._extract_pair(symbol)
        time_ref_s = to_epoch_ms(capture_ts) / 1000.0
        now_ms_ts = to_epoch_ms(capture_ts)

        prev_base = self._last_force.get((base, timeframe)) if base else None
        if base and prev_base is not None:
            current_val = forces[base]
            delta = current_val - prev_base.intensite
            delta_t = time_ref_s - prev_base.time_ref_s
            row["direction"] = _direction_from_delta(delta)
            row["vitesse"] = delta / delta_t if delta_t > 0 else 0.0

        for devise in DEVISES:
            self._last_force[(devise, timeframe)] = ForceState(
                intensite=forces[devise], time_ref_s=time_ref_s
            )

        fenetre_ms = row["stale_threshold_ms"]
        window_key = (base or symbol, timeframe)
        window = self._tick_windows.setdefault(window_key, [])
        window.append(now_ms_ts)
        cutoff = now_ms_ts - fenetre_ms
        while window and window[0] < cutoff:
            window.pop(0)
        nb_ticks_fenetre = len(window)

        entry = _build_format_forces_entry_tick(row, base or symbol, nb_ticks_fenetre)
        return {"row": row, "format_forces_entry": entry}

    # ── Export FORMAT_FORCES.md ───────────────────────────
    def to_snapshot(self, result: dict) -> dict:
        """Construit un snapshot complet aligné sur FORMAT_FORCES.md."""
        row = result["row"]
        entry = result["format_forces_entry"]
        freshness = {
            "captured_at": row["created_at"],
            "age_ms": row["age_ms"],
            "stale": row["stale"],
            "stale_threshold_ms": row["stale_threshold_ms"],
        }
        snapshot = {
            "schema_version": row["schema_version"],
            "snapshot_id": row["snapshot_id"],
            "timestamp": row["timestamp"],
            "source": row["source"],
            "freshness": freshness,
        }
        if row["timeframe"] in TIMEFRAME_TICK:
            snapshot["forces"] = []
            snapshot["m1"] = [entry]
        else:
            snapshot["forces"] = [entry]
            snapshot["m1"] = []
        return snapshot

    def stale_stats(self) -> dict:
        return self.stale_gate.stale_stats()


def _direction_from_delta(delta: float) -> str:
    if delta > 0:
        return "haussiere"
    if delta < 0:
        return "baissiere"
    return "neutre"


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def _build_format_forces_entry_candle(row: dict, devise: str) -> dict:
    return {
        "devise": devise,
        "timeframe": row["timeframe"],
        "intensite": row.get(f"force_{devise.lower()}"),
        "direction": row["direction"],
        "vitesse": row["vitesse"],
        "croisement": {
            "detecte": row["croisement_detecte"],
            "devise_partenaire": row["croisement_partenaire"],
            "direction": row["croisement_direction"],
        },
        "recroisement": {
            "detecte": row["recroisement_detecte"],
            "contexte": row["recroisement_contexte"],
        },
        "rejet_repulsion": {
            "detecte": row["rejet_repulsion_detecte"],
            "intensite": row["rejet_intensite"],
        },
        "compression_extension": {
            "etat": row["compression_extension_etat"],
            "intensite": row["compression_extension_intensite"],
        },
        "freshness": {
            "timestamp": row["timestamp"],
            "age_ms": row["age_ms"],
            "stale": row["stale"],
            "stale_threshold_ms": row["stale_threshold_ms"],
        },
    }


def _build_format_forces_entry_tick(row: dict, devise: str, nb_ticks_fenetre: int) -> dict:
    return {
        "devise": devise,
        "mode": "tick_velocity",
        "dernier_tick_timestamp": row["timestamp"],
        "intensite_instantanee": row.get(f"force_{devise.lower()}"),
        "direction": row["direction"],
        "vitesse_tick": row["vitesse"],
        "nb_ticks_fenetre": nb_ticks_fenetre,
        "fenetre_ms": row["stale_threshold_ms"],
        "freshness": {
            "timestamp": row["timestamp"],
            "age_ms": row["age_ms"],
            "stale": row["stale"],
            "stale_threshold_ms": row["stale_threshold_ms"],
        },
    }
