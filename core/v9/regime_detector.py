"""RegimeDetector — comble le gap V8 `regime_snapshots` (Phase 9, bonus).

docs/audit_v8_v9_migration.md §2.2/§6 : `regime_snapshots` (327 112
lignes en V8, le plus gros volume de données V8) n'avait aucun
équivalent V9. La machine à états (palier -> cassure -> extension ->
retour_equilibre, + rejet §18 grammaire) est portée depuis
`core/pf_regime_detector.py` (V8), adaptée au modèle événementiel V9 :
au lieu d'un batch sur tout l'historique, elle tourne à chaque nouveau
snapshot sur une fenêtre glissante (`REGIME_LOOKBACK_BARS`) du même
symbol+timeframe, et ne persiste que le régime du snapshot courant (une
ligne par devise, comme les autres couches V9 — un événement, une
ligne).

V9 n'a pas encore de couche tick (`tick_aggregated_5s` en V8) — la
qualification de cassure (CONFIRMEE/FAUSSE) reste donc toujours
INDETERMINEE, exactement la dégradation que V8 applique déjà quand
cette table ne couvre pas la fenêtre (voir `qualify_cassure` V8).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from core.v9.config import (
    DB_PATH,
    DEVISES,
    REGIME_K_REJET,
    REGIME_LOOKBACK_BARS,
    REGIME_MR_HIGH,
    REGIME_MR_LOW,
    REGIME_N_MIN,
    REGIME_TIMEFRAME_OVERRIDES,
    SCHEMA_VERSION,
    SEUIL_CASSURE,
    SEUIL_PALIER,
    SEUIL_REJET,
)
from core.v9.db_schema import get_connection
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db

NEUTRE = "NEUTRE"
PALIER = "PALIER"
CASSURE = "CASSURE"
EXTENSION = "EXTENSION"
RETOUR_EQUILIBRE = "RETOUR_EQUILIBRE"
REJET = "REJET"

INDETERMINEE = "INDETERMINEE"


class RegimeDetectorError(ValueError):
    """Erreur de détection de régime (snapshot introuvable)."""


@dataclass
class _Bar:
    bar_time: int
    timestamp: str
    force: float | None


def _rejet_direction(series: list[_Bar], i: int, mr_low: float, mr_high: float,
                      seuil_rejet: float, k_rejet: int) -> str | None:
    """Renversement violent au contact d'un extrême (§18 grammaire V8) —
    voir core/pf_regime_detector.py::_rejet_direction (logique identique)."""
    if i < 1 + k_rejet:
        return None
    f_cur, f_prev, f_ref = series[i].force, series[i - 1].force, series[i - 1 - k_rejet].force
    if f_cur is None or f_prev is None or f_ref is None:
        return None
    in_high = f_prev > mr_high or f_cur > mr_high
    in_low = f_prev < mr_low or f_cur < mr_low
    if not (in_high or in_low):
        return None
    approach = f_prev - f_ref
    reversal = f_cur - f_prev
    if abs(reversal) < seuil_rejet:
        return None
    if in_high and approach >= 0 and reversal <= -seuil_rejet:
        return "DOWN"
    if in_low and approach <= 0 and reversal >= seuil_rejet:
        return "UP"
    return None


class RegimeDetector:
    """Détecte le régime de force courant (par devise) et le persiste dans
    `regime_snapshots`."""

    def __init__(self, db_path: Path | str | None = None, config: dict | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_regime_db(self.db_path)

        cfg = dict(config) if config else {}
        self._explicit_cfg_keys = set(cfg.keys())
        self.lookback_bars = cfg.get("lookback_bars", REGIME_LOOKBACK_BARS)
        self.seuil_palier = cfg.get("seuil_palier", SEUIL_PALIER)
        self.seuil_cassure = cfg.get("seuil_cassure", SEUIL_CASSURE)
        self.n_min = cfg.get("n_min", REGIME_N_MIN)
        self.mr_low = cfg.get("mr_low", REGIME_MR_LOW)
        self.mr_high = cfg.get("mr_high", REGIME_MR_HIGH)
        self.seuil_rejet = cfg.get("seuil_rejet", SEUIL_REJET)
        self.k_rejet = cfg.get("k_rejet", REGIME_K_REJET)

    def _effective_thresholds(self, timeframe: str) -> tuple[float, float, int]:
        """Seuils palier/cassure/n_min pour `timeframe` — applique
        REGIME_TIMEFRAME_OVERRIDES (H1/H4, cf config.py) sauf si l'appelant
        a explicitement surchargé le paramètre via `config` au constructeur
        (R2 additif : la config explicite reste prioritaire)."""
        overrides = REGIME_TIMEFRAME_OVERRIDES.get(timeframe, {})
        seuil_palier = self.seuil_palier if "seuil_palier" in self._explicit_cfg_keys else overrides.get("seuil_palier", self.seuil_palier)
        seuil_cassure = self.seuil_cassure if "seuil_cassure" in self._explicit_cfg_keys else overrides.get("seuil_cassure", self.seuil_cassure)
        n_min = self.n_min if "n_min" in self._explicit_cfg_keys else overrides.get("n_min", self.n_min)
        return seuil_palier, seuil_cassure, n_min

    def _connect(self):
        conn = get_connection(self.db_path)
        import sqlite3
        conn.row_factory = sqlite3.Row
        return conn

    def _load_history(self, conn, symbol: str, timeframe: str, upto_bar_time: int) -> list:
        rows = conn.execute(
            "SELECT bar_time, timestamp FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = ? AND bar_time <= ? "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol, timeframe, upto_bar_time, self.lookback_bars),
        ).fetchall()
        return list(reversed(rows))

    def _detect_series(
        self,
        series: list[_Bar],
        seuil_palier: float | None = None,
        seuil_cassure: float | None = None,
        n_min: int | None = None,
    ) -> dict:
        """Machine à états, retourne uniquement le régime de la DERNIÈRE
        barre de `series` (le snapshot courant). Portage direct de
        `pf_regime_detector.detect_single_currency` (V8), sans la
        qualification tick (absente en V9).

        `seuil_palier`/`seuil_cassure`/`n_min` permettent au caller
        (`detect()`) d'injecter les seuils adaptés au timeframe courant
        (REGIME_TIMEFRAME_OVERRIDES) sans muter l'état de l'instance ;
        par défaut, retombe sur les seuils de l'instance (comportement
        historique, utilisé aussi par les tests unitaires)."""
        seuil_palier = self.seuil_palier if seuil_palier is None else seuil_palier
        seuil_cassure = self.seuil_cassure if seuil_cassure is None else seuil_cassure
        n_min = self.n_min if n_min is None else n_min

        palier_start_idx: int | None = None
        palier_established = False
        ext_dir: str | None = None

        last: dict = {
            "regime_type": NEUTRE, "cassure_direction": None,
            "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
            "mean_reversion_zone": False,
        }

        for i in range(len(series)):
            force = series[i].force
            mrz = force is not None and (force > self.mr_high or force < self.mr_low)

            if i == 0 or force is None or series[i - 1].force is None:
                last = {"regime_type": RETOUR_EQUILIBRE if mrz else NEUTRE, "cassure_direction": None,
                        "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                        "mean_reversion_zone": mrz}
                continue

            f_prev = series[i - 1].force

            rejet_dir = _rejet_direction(series, i, self.mr_low, self.mr_high, self.seuil_rejet, self.k_rejet)
            if rejet_dir is not None:
                last = {"regime_type": REJET, "cassure_direction": rejet_dir,
                        "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                        "mean_reversion_zone": mrz}
                ext_dir = None
                palier_established = False
                palier_start_idx = None
                continue

            if ext_dir is not None:
                cont = ((force - f_prev) > 0 and ext_dir == "UP") or ((force - f_prev) < 0 and ext_dir == "DOWN")
                if cont:
                    last = {"regime_type": EXTENSION, "cassure_direction": ext_dir,
                            "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                            "mean_reversion_zone": mrz}
                    continue
                ext_dir = None

            step = abs(force - f_prev)
            if step < seuil_palier:
                if palier_start_idx is None:
                    palier_start_idx = i - 1
                run_len = i - palier_start_idx + 1
                if run_len >= n_min:
                    palier_established = True
                    last = {"regime_type": PALIER if not mrz else RETOUR_EQUILIBRE, "cassure_direction": None,
                            "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                            "mean_reversion_zone": mrz}
                else:
                    last = {"regime_type": RETOUR_EQUILIBRE if mrz else NEUTRE, "cassure_direction": None,
                            "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                            "mean_reversion_zone": mrz}
                continue

            if palier_established and palier_start_idx is not None:
                anchor = series[palier_start_idx].force
                if anchor is not None and abs(force - anchor) > seuil_cassure:
                    direction = "UP" if force > anchor else "DOWN"
                    levels = [b.force for b in series[palier_start_idx:i] if b.force is not None]
                    p_level = round(mean(levels), 4) if levels else None
                    p_start_ts = series[palier_start_idx].timestamp
                    p_dur = max(1, i - palier_start_idx)
                    last = {"regime_type": CASSURE, "cassure_direction": direction,
                            "palier_start_ts": p_start_ts, "palier_duration_bars": p_dur, "palier_level": p_level,
                            "mean_reversion_zone": mrz}
                    ext_dir = direction
                    palier_established = False
                    palier_start_idx = None
                    continue
                palier_established = False
                palier_start_idx = None
                last = {"regime_type": RETOUR_EQUILIBRE if mrz else NEUTRE, "cassure_direction": None,
                        "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                        "mean_reversion_zone": mrz}
                continue

            palier_start_idx = None
            palier_established = False
            last = {"regime_type": RETOUR_EQUILIBRE if mrz else NEUTRE, "cassure_direction": None,
                    "palier_start_ts": None, "palier_duration_bars": None, "palier_level": None,
                    "mean_reversion_zone": mrz}

        last["force_value"] = series[-1].force if series else None
        return last

    def detect(self, snapshot_id: str) -> list[dict[str, Any]]:
        """Détecte le régime courant pour les 8 devises d'un snapshot et le
        persiste dans `regime_snapshots`. Retourne la liste des régimes
        produits (un dict par devise)."""
        conn = self._connect()
        try:
            current = conn.execute(
                "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if current is None:
                raise RegimeDetectorError(f"snapshot de forces introuvable: {snapshot_id!r}")

            symbol, timeframe = current["symbol"], current["timeframe"]
            history_rows = self._load_history(conn, symbol, timeframe, current["bar_time"])
            timestamps_by_bar_time = {r["bar_time"]: r["timestamp"] for r in history_rows}
            # S'assure que le snapshot courant termine bien la fenêtre, même
            # si un replay l'insère hors ordre strict.
            if not history_rows or history_rows[-1]["bar_time"] != current["bar_time"]:
                timestamps_by_bar_time[current["bar_time"]] = current["timestamp"]

            bar_times = sorted(timestamps_by_bar_time)
            results = []
            now = datetime.now(timezone.utc).isoformat()
            seuil_palier, seuil_cassure, n_min = self._effective_thresholds(timeframe)

            for currency in DEVISES:
                col = f"force_{currency.lower()}"
                rows_full = conn.execute(
                    f"SELECT bar_time, {col} AS force FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = ? AND bar_time IN "
                    f"({','.join('?' for _ in bar_times)}) ",
                    (symbol, timeframe, *bar_times),
                ).fetchall() if bar_times else []
                forces_by_bar_time = {r["bar_time"]: r["force"] for r in rows_full}
                if current["bar_time"] not in forces_by_bar_time:
                    forces_by_bar_time[current["bar_time"]] = current[col]

                series = [
                    _Bar(bt, timestamps_by_bar_time[bt], forces_by_bar_time.get(bt))
                    for bt in bar_times
                ]
                regime = self._detect_series(series, seuil_palier, seuil_cassure, n_min)
                evaluation = {
                    "regime_id": _generate_regime_id(symbol, timeframe, currency),
                    "schema_version": SCHEMA_VERSION,
                    "timestamp": now,
                    "forces_snapshot_ref": snapshot_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "currency": currency,
                    "force_value": regime["force_value"],
                    "regime_type": regime["regime_type"],
                    "cassure_type": INDETERMINEE if regime["regime_type"] in (CASSURE, REJET) else None,
                    "cassure_direction": regime["cassure_direction"],
                    "palier_start_ts": regime["palier_start_ts"],
                    "palier_duration_bars": regime["palier_duration_bars"],
                    "palier_level": regime["palier_level"],
                    "tick_freq_hz": None,
                    "spread_mean": None,
                    "delta_vol": None,
                    "mean_reversion_zone": regime["mean_reversion_zone"],
                    "stale": bool(current["stale"]),
                    "source_type": self.source_type,
                    "created_at": now,
                }
                results.append(evaluation)

            self._write_to_db(conn, results)
            return results
        finally:
            conn.close()

    def _write_to_db(self, conn, results: list[dict]) -> None:
        columns = ", ".join(REGIME_SNAPSHOTS_COLUMNS)
        placeholders = ", ".join("?" for _ in REGIME_SNAPSHOTS_COLUMNS)
        conn.executemany(
            f"INSERT OR REPLACE INTO regime_snapshots ({columns}) VALUES ({placeholders})",
            [[r[c] for c in REGIME_SNAPSHOTS_COLUMNS] for r in results],
        )
        conn.commit()


def _generate_regime_id(symbol: str, timeframe: str, currency: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"regime_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{currency.lower()}_{uuid.uuid4().hex[:6]}"
