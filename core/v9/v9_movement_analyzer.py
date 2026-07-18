"""v9_movement_analyzer — analyse statistique des mouvements haussiers vs baissiers.

Mission 1/2 de l'audit cognition baissier (CEO 2026-07-18) :
quantifier la vitesse, l'amplitude et la durée des mouvements directionnels
par symbole × timeframe, détecter les biais de perception temporelle et
recommander une configuration de timing (TP/SL/TimeExit) adaptée au baissier.

R6 (try/except défensif), R18 (Python stdlib + sqlite3 only).

CLI :
    python core/v9/v9_movement_analyzer.py --symbol GBPUSD --timeframe M5
    python core/v9/v9_movement_analyzer.py --symbol GBPUSD --report

Ne mute jamais la DB. Lecture seule (R18).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Iterable


# ── Constantes ────────────────────────────────────────────────────────────
PIP_FACTOR_FOREX_5 = 10000.0  # 0.0001 → 1 pip (paires en quote 5 decimales)
PIP_FACTOR_FOREX_3 = 100.0    # 0.01   → 1 pip (paires JPY en quote 3 decimales)

# Devises quote en 3 decimales (JPY pour l'instant, seul cas couvert)
_QUOTE_3_DECIMAL_CURRENCIES = {"JPY"}

# Bornes de durée / amplitude pour la qualification des runs
DEFAULT_RUN_LOOKBACK = 1000  # bougies max chargées pour analyse run


# ── Dataclasses ──────────────────────────────────────────────────────────
@dataclass
class DirectionSpeedStats:
    """Statistiques de vitesse/amplitude/durée par direction."""

    symbol: str
    timeframe: str
    n_up: int
    n_down: int
    n_neutral: int
    avg_duration_up: float       # bougies
    avg_duration_down: float
    avg_amplitude_up_pips: float
    avg_amplitude_down_pips: float
    median_duration_up: float
    median_duration_down: float
    p90_duration_up: float
    p90_duration_down: float
    p90_amplitude_up_pips: float
    p90_amplitude_down_pips: float
    drift_up_pips: float          # somme deltas UP
    drift_down_pips: float        # somme (abs) deltas DOWN
    drift_ratio: float            # |drift_up| / |drift_down|

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerceptionBiasReport:
    """Rapport de biais de perception temporelle par timeframe."""

    symbol: str
    timeframe: str
    timeframe_avg_duration_up: float
    timeframe_avg_duration_down: float
    duration_asymmetry_ratio: float       # up / down (>1 = haussier plus lent)
    amplitude_asymmetry_ratio: float      # up_amp / down_amp
    timeframes_analyzed: list[str] = field(default_factory=list)
    bias_per_timeframe: dict[str, dict[str, float]] = field(default_factory=dict)
    recommended_timeframe: str = ""       # celui qui voit les runs baissiers les plus longs
    recommendation_reason: str = ""
    bias_severity: str = "low"            # low / medium / high

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BearishTimingConfig:
    """Configuration de timing recommandée pour les trades baissiers."""

    symbol: str
    preferred_timeframe: str
    tp_pips: float
    sl_pips: float
    time_bars: int
    risk_reward_ratio: float
    session_filter: list[str] = field(default_factory=list)
    rationale: str = ""
    supporting_stats: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Utilitaires DB ───────────────────────────────────────────────────────
def _get_quote_decimals(symbol: str) -> int:
    """Retourne 3 pour les paires JPY (0.01 → 1 pip), 5 sinon (0.0001 → 1 pip)."""
    upper = symbol.upper()
    # Format standard FX : 6 chars, 3 chars devise base + 3 chars devise quote
    if len(upper) == 6:
        quote = upper[3:]
        if quote in _QUOTE_3_DECIMAL_CURRENCIES:
            return 3
    return 5


def _price_to_pips(delta_price: float, symbol: str) -> float:
    factor = PIP_FACTOR_FOREX_3 if _get_quote_decimals(symbol) == 3 else PIP_FACTOR_FOREX_5
    return delta_price * factor


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _safe_close(conn: sqlite3.Connection | None) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


# ── Analyse run-length (direction-consécutive bougies) ──────────────────
def _compute_runs(rows: list[sqlite3.Row], symbol: str) -> tuple[list[int], list[int], list[float], list[float]]:
    """Calcule les runs haussiers/baissiers sur une liste ordonnée de bougies.

    Retourne : (run_lens_up, run_lens_down, amps_up_pips, amps_down_pips).
    """
    if not rows:
        return [], [], [], []
    pip_factor = PIP_FACTOR_FOREX_3 if _get_quote_decimals(symbol) == 3 else PIP_FACTOR_FOREX_5

    runs_up: list[int] = []
    runs_dn: list[int] = []
    amps_up: list[float] = []
    amps_dn: list[float] = []

    cur_dir = 0
    cur_len = 0
    cur_amp_sum = 0.0

    def _flush(direction: int, length: int, amp_sum: float) -> None:
        if direction == 1 and length > 0:
            runs_up.append(length)
            amps_up.append(amp_sum / length)
        elif direction == -1 and length > 0:
            runs_dn.append(length)
            amps_dn.append(amp_sum / length)

    for r in rows:
        try:
            o = float(r["open"]) if r["open"] is not None else None
            c = float(r["close"]) if r["close"] is not None else None
            h = float(r["high"]) if r["high"] is not None else None
            l = float(r["low"]) if r["low"] is not None else None
        except (KeyError, TypeError, ValueError):
            continue
        if o is None or c is None or h is None or l is None:
            continue
        delta = c - o
        amp = (h - l) * pip_factor
        if delta > 0:
            new_dir = 1
        elif delta < 0:
            new_dir = -1
        else:
            new_dir = 0
        if new_dir == 0:
            # Bougie plate : ne casse pas le run, mais ne l'allonge pas
            cur_amp_sum += amp
            continue
        if cur_dir == 0:
            cur_dir = new_dir
            cur_len = 1
            cur_amp_sum = amp
        elif new_dir == cur_dir:
            cur_len += 1
            cur_amp_sum += amp
        else:
            _flush(cur_dir, cur_len, cur_amp_sum)
            cur_dir = new_dir
            cur_len = 1
            cur_amp_sum = amp

    if cur_dir != 0 and cur_len > 0:
        _flush(cur_dir, cur_len, cur_amp_sum)
    return runs_up, runs_dn, amps_up, amps_dn


def _percentile(values: list[float | int], pct: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    if pct <= 0:
        return float(sorted_v[0])
    if pct >= 100:
        return float(sorted_v[-1])
    k = (len(sorted_v) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return float(sorted_v[f])
    return float(sorted_v[f]) + (k - f) * (sorted_v[c] - sorted_v[f])


# ── MovementAnalyzer ────────────────────────────────────────────────────
class MovementAnalyzer:
    """Analyse statistique des mouvements haussiers vs baissiers."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"DB introuvable : {self.db_path}")

    # ── Méthode principale : vitesse/amplitude/durée ─────────────────
    def analyze_direction_speed(
        self, *, symbol: str, timeframe: str = "M5", limit: int = DEFAULT_RUN_LOOKBACK
    ) -> DirectionSpeedStats:
        """Compare vitesse/amplitude/durée des mouvements haussiers vs baissiers.

        Charge les N dernières bougies (par défaut 1000) du (symbol, timeframe),
        calcule :
        - runs haussiers/baissiers (durée en bougies consécutives)
        - amplitude moyenne/p90 par direction (en pips)
        - drift cumulé par direction (somme des deltas)

        Args:
            symbol: ex. "GBPUSD"
            timeframe: ex. "M5", "M1", "H1"
            limit: nombre max de bougies à charger (défaut 1000)

        Returns:
            DirectionSpeedStats avec statistiques comparatives.
        """
        conn = _connect(self.db_path)
        try:
            try:
                rows = conn.execute(
                    "SELECT open, close, high, low FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1 AND stale = 0 "
                    "ORDER BY bar_time DESC LIMIT ?",
                    (symbol.upper(), timeframe.upper(), int(limit)),
                ).fetchall()
            except sqlite3.Error as e:
                raise RuntimeError(f"Erreur SQLite analyze_direction_speed: {e}") from e
            # On veut l'ordre chronologique pour les runs
            rows = list(reversed(rows))

            runs_up, runs_dn, amps_up, amps_dn = _compute_runs(rows, symbol)

            # Bougies unitaires pour drift + n_up/n_down/n_neutral
            pip_factor = PIP_FACTOR_FOREX_3 if _get_quote_decimals(symbol) == 3 else PIP_FACTOR_FOREX_5
            n_up = n_down = n_neutral = 0
            drift_up_pips = 0.0
            drift_down_pips = 0.0
            for r in rows:
                try:
                    o = r["open"]
                    c = r["close"]
                except (KeyError, IndexError):
                    continue
                if o is None or c is None:
                    n_neutral += 1
                    continue
                delta = (c - o) * pip_factor
                if delta > 0:
                    n_up += 1
                    drift_up_pips += delta
                elif delta < 0:
                    n_down += 1
                    drift_down_pips += delta  # négatif
                else:
                    n_neutral += 1

            avg_dur_up = mean(runs_up) if runs_up else 0.0
            avg_dur_dn = mean(runs_dn) if runs_dn else 0.0
            avg_amp_up = mean(amps_up) if amps_up else 0.0
            avg_amp_dn = mean(amps_dn) if amps_dn else 0.0

            med_dur_up = median(runs_up) if runs_up else 0
            med_dur_dn = median(runs_dn) if runs_dn else 0

            p90_dur_up = _percentile(runs_up, 90)
            p90_dur_dn = _percentile(runs_dn, 90)
            p90_amp_up = _percentile(amps_up, 90)
            p90_amp_dn = _percentile(amps_dn, 90)

            # Ratio drift (drift_up absolu / drift_down absolu)
            drift_ratio = (
                abs(drift_up_pips) / abs(drift_down_pips)
                if abs(drift_down_pips) > 1e-9
                else float("inf") if abs(drift_up_pips) > 1e-9 else 1.0
            )

            return DirectionSpeedStats(
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
                n_up=n_up,
                n_down=n_down,
                n_neutral=n_neutral,
                avg_duration_up=round(avg_dur_up, 3),
                avg_duration_down=round(avg_dur_dn, 3),
                avg_amplitude_up_pips=round(avg_amp_up, 3),
                avg_amplitude_down_pips=round(avg_amp_dn, 3),
                median_duration_up=float(med_dur_up),
                median_duration_down=float(med_dur_dn),
                p90_duration_up=round(p90_dur_up, 2),
                p90_duration_down=round(p90_dur_dn, 2),
                p90_amplitude_up_pips=round(p90_amp_up, 2),
                p90_amplitude_down_pips=round(p90_amp_dn, 2),
                drift_up_pips=round(drift_up_pips, 2),
                drift_down_pips=round(drift_down_pips, 2),
                drift_ratio=round(drift_ratio, 3) if drift_ratio != float("inf") else 999.0,
            )
        finally:
            _safe_close(conn)

    # ── Détection biais de perception temporelle ───────────────────
    def detect_perception_bias(
        self, *, symbol: str = "GBPUSD", timeframes: Iterable[str] | None = None,
    ) -> PerceptionBiasReport:
        """Identifie les TF où la perception temporelle lisse les mouvements rapides.

        Compare la durée et l'amplitude moyennes des runs haussiers vs
        baissiers sur tous les TF fournis. Le TF « biaisé » est celui où
        la durée du run baissier est nettement plus courte (typiquement
        le TF lent qui moyennise les spikes baissiers rapides).

        Returns:
            PerceptionBiasReport avec TF biaisés et recommandation.
        """
        tfs = list(timeframes) if timeframes is not None else ["M1", "M5", "M15", "H1", "H4"]
        bias_per_tf: dict[str, dict[str, float]] = {}
        for tf in tfs:
            try:
                s = self.analyze_direction_speed(symbol=symbol, timeframe=tf)
            except Exception:
                continue
            dur_ratio = (
                s.avg_duration_up / s.avg_duration_down
                if s.avg_duration_down > 0 else float("inf") if s.avg_duration_up > 0 else 1.0
            )
            amp_ratio = (
                s.avg_amplitude_up_pips / s.avg_amplitude_down_pips
                if s.avg_amplitude_down_pips > 0 else float("inf") if s.avg_amplitude_up_pips > 0 else 1.0
            )
            bias_per_tf[tf] = {
                "avg_dur_up": s.avg_duration_up,
                "avg_dur_down": s.avg_duration_down,
                "dur_asymmetry_ratio": round(dur_ratio, 3) if dur_ratio != float("inf") else 999.0,
                "avg_amp_up_pips": s.avg_amplitude_up_pips,
                "avg_amp_down_pips": s.avg_amplitude_down_pips,
                "amp_asymmetry_ratio": round(amp_ratio, 3) if amp_ratio != float("inf") else 999.0,
                "n_up": s.n_up,
                "n_down": s.n_down,
            }

        # TF où le run baissier est le plus long relativement
        # (plus dur_down est grand par rapport à dur_up, plus le baissier
        # est visible).
        best_tf = ""
        best_score = -1.0
        for tf, m in bias_per_tf.items():
            # Score : durée down absolue (on veut un TF où down dure longtemps)
            # minoré par le ratio (on veut down pas trop écrasé par up)
            dn = m["avg_dur_down"]
            ratio = m["dur_asymmetry_ratio"]
            # ratio < 1 : down plus long que up → bien
            score = dn * (1.0 / max(ratio, 0.5))
            if score > best_score:
                best_score = score
                best_tf = tf

        # Sévérité globale : sur le TF principal de référence (M5), comparer
        ref = bias_per_tf.get("M5", {})
        ref_ratio = ref.get("dur_asymmetry_ratio", 1.0)
        if ref["dur_asymmetry_ratio"] != 999.0:
            if ref_ratio >= 1.5:
                severity = "high"
            elif ref_ratio >= 1.2:
                severity = "medium"
            else:
                severity = "low"
        else:
            severity = "unknown"

        # TF globaux (référence = timeframe moyen d'analyse)
        ref_tf_stats = bias_per_tf.get("M5") or (next(iter(bias_per_tf.values())) if bias_per_tf else {})
        return PerceptionBiasReport(
            symbol=symbol.upper(),
            timeframe="M5",
            timeframe_avg_duration_up=float(ref_tf_stats.get("avg_dur_up", 0.0)),
            timeframe_avg_duration_down=float(ref_tf_stats.get("avg_dur_down", 0.0)),
            duration_asymmetry_ratio=float(ref_tf_stats.get("dur_asymmetry_ratio", 1.0)),
            amplitude_asymmetry_ratio=float(ref_tf_stats.get("amp_asymmetry_ratio", 1.0)),
            timeframes_analyzed=list(bias_per_tf.keys()),
            bias_per_timeframe=bias_per_tf,
            recommended_timeframe=best_tf,
            recommendation_reason=(
                f"TF {best_tf} maximise la durée visible des runs baissiers "
                f"tout en minimisant le biais asymétrique (ratio {bias_per_tf.get(best_tf, {}).get('dur_asymmetry_ratio', 0)})"
                if best_tf else ""
            ),
            bias_severity=severity,
        )

    # ── Recommandation timing baissier ─────────────────────────────
    def recommend_bearish_timing(
        self, *, symbol: str = "GBPUSD", reference_timeframe: str = "M5",
    ) -> BearishTimingConfig:
        """Recommande TP/SL/TimeExit optimaux pour le baissier selon la vitesse détectée.

        Heuristique :
        - TP = max(p90_amplitude_down_pips × 0.8, 6 pips) — cible 80% de
          l'amplitude p90 pour ne pas dépendre des queues extrêmes
        - SL = max(amplitude médiane × 1.5, 4 pips) — serré mais pas
          stop-out sur bruit normal
        - time_bars = ceil(p90_duration_down × 1.2) — laisse 20% de marge
          au-dessus de la durée p90
        - preferred_timeframe = TF avec le plus de runs baissiers détectés
          (via detect_perception_bias)
        - session_filter = sessions où le drift baissier est le plus
          prononcé (overlap/new_york pour GBPUSD empiriquement)
        """
        try:
            stats = self.analyze_direction_speed(symbol=symbol, timeframe=reference_timeframe)
        except Exception:
            stats = None
        try:
            bias = self.detect_perception_bias(symbol=symbol)
        except Exception:
            bias = None

        if stats is None or stats.n_down == 0:
            # Fallback conservateur
            return BearishTimingConfig(
                symbol=symbol.upper(),
                preferred_timeframe=reference_timeframe,
                tp_pips=8.0,
                sl_pips=6.0,
                time_bars=6,
                risk_reward_ratio=round(8.0 / 6.0, 3),
                session_filter=["overlap", "new_york"],
                rationale="Fallback conservateur (pas de données baissières détectées)",
                supporting_stats={},
            )

        tp = max(stats.p90_amplitude_down_pips * 0.8, 6.0)
        sl = max(stats.avg_amplitude_down_pips * 1.5, 4.0)
        time_bars = max(int(round(stats.p90_duration_down * 1.2)), 2)
        rr = round(tp / sl, 3) if sl > 0 else 0.0

        pref_tf = bias.recommended_timeframe if bias and bias.recommended_timeframe else reference_timeframe

        # Session filter : pour GBPUSD on sait empiriquement que
        # overlap/new_york concentrent les mouvements. Lecture DB.
        sessions = self._session_drift_ranking(symbol=symbol, reference_timeframe=reference_timeframe)

        return BearishTimingConfig(
            symbol=symbol.upper(),
            preferred_timeframe=pref_tf,
            tp_pips=round(tp, 2),
            sl_pips=round(sl, 2),
            time_bars=time_bars,
            risk_reward_ratio=rr,
            session_filter=sessions[:2] if sessions else ["overlap", "new_york"],
            rationale=(
                f"Basé sur {stats.n_down} bougies baissières M{reference_timeframe[1:] if reference_timeframe[0]=='M' else '?'} "
                f"du symbole {symbol} (p90 amplitude={stats.p90_amplitude_down_pips:.2f} pips, "
                f"p90 durée={stats.p90_duration_down:.1f} bougies). "
                f"TF préféré={pref_tf} (cf. detect_perception_bias)."
            ),
            supporting_stats={
                "p90_amp_down": stats.p90_amplitude_down_pips,
                "p90_dur_down": stats.p90_duration_down,
                "avg_amp_down": stats.avg_amplitude_down_pips,
                "avg_dur_down": stats.avg_duration_down,
                "drift_ratio_up_down": stats.drift_ratio,
            },
        )

    # ── Helper : drift par session UTC ─────────────────────────────
    def _session_drift_ranking(
        self, *, symbol: str, reference_timeframe: str, top_n: int = 4
    ) -> list[str]:
        """Classe les sessions UTC par drift baissier moyen (plus négatif = mieux)."""
        conn = _connect(self.db_path)
        try:
            try:
                rows = conn.execute(
                    "SELECT bar_time, open, close FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1 AND stale = 0",
                    (symbol.upper(), reference_timeframe.upper()),
                ).fetchall()
            except sqlite3.Error:
                return []
            pip_factor = PIP_FACTOR_FOREX_3 if _get_quote_decimals(symbol) == 3 else PIP_FACTOR_FOREX_5
            session_drift: dict[str, float] = {
                "asie": 0.0, "london": 0.0, "overlap": 0.0, "new_york": 0.0,
            }
            session_count: dict[str, int] = {k: 0 for k in session_drift}
            for r in rows:
                try:
                    o = r["open"]
                    c = r["close"]
                    bt = int(r["bar_time"])
                except (KeyError, TypeError, ValueError):
                    continue
                if o is None or c is None:
                    continue
                dt = datetime.fromtimestamp(bt, tz=timezone.utc)
                h = dt.hour
                if 0 <= h < 7:
                    s = "asie"
                elif 7 <= h < 12:
                    s = "london"
                elif 12 <= h < 16:
                    s = "overlap"
                else:
                    s = "new_york"
                delta_pips = (c - o) * pip_factor
                session_drift[s] += delta_pips
                session_count[s] += 1
            avg_drift = {s: (session_drift[s] / session_count[s] if session_count[s] else 0.0) for s in session_drift}
            # Tri par drift moyen croissant (le plus baissier en premier)
            return sorted(avg_drift, key=lambda k: avg_drift[k])[:top_n]
        finally:
            _safe_close(conn)


# ── CLI ──────────────────────────────────────────────────────────────────
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="V9 Movement Analyzer — audit cognition baissier (mission 1/2).",
    )
    p.add_argument("--db-path", default=None, help="Chemin DB (défaut : data/v9_forces.db du projet).")
    p.add_argument("--symbol", default="GBPUSD", help="Symbole (défaut GBPUSD).")
    p.add_argument("--timeframe", default="M5", help="Timeframe principal (défaut M5).")
    p.add_argument(
        "--report", action="store_true",
        help="Affiche le rapport complet (analyze + bias + timing) au lieu d'un seul TF.",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Sortie JSON (sinon texte formaté).",
    )
    return p


def _resolve_db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    # Défaut : data/v9_forces.db relatif à la racine projet
    return Path(__file__).resolve().parent.parent.parent / "data" / "v9_forces.db"


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    db_path = _resolve_db_path(args.db_path)
    try:
        analyzer = MovementAnalyzer(db_path)
    except FileNotFoundError as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        return 1

    try:
        if args.report:
            stats = analyzer.analyze_direction_speed(symbol=args.symbol, timeframe=args.timeframe)
            bias = analyzer.detect_perception_bias(symbol=args.symbol)
            timing = analyzer.recommend_bearish_timing(symbol=args.symbol, reference_timeframe=args.timeframe)
            if args.json:
                out = {
                    "direction_speed_stats": stats.to_dict(),
                    "perception_bias_report": bias.to_dict(),
                    "bearish_timing_config": timing.to_dict(),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
            else:
                print(f"\n=== V9 MovementAnalyzer — {args.symbol} ({args.timeframe}) ===")
                print(f"\n[1] DirectionSpeedStats")
                print(f"  Bougies: UP={stats.n_up}  DOWN={stats.n_down}  NEUTRAL={stats.n_neutral}")
                print(f"  Durée moyenne run: UP={stats.avg_duration_up:.2f}  DOWN={stats.avg_duration_down:.2f}")
                print(f"  Amplitude moyenne: UP={stats.avg_amplitude_up_pips:.2f} pips  DOWN={stats.avg_amplitude_down_pips:.2f} pips")
                print(f"  p90 durée: UP={stats.p90_duration_up:.1f}  DOWN={stats.p90_duration_down:.1f}")
                print(f"  p90 amplitude: UP={stats.p90_amplitude_up_pips:.2f} pips  DOWN={stats.p90_amplitude_down_pips:.2f} pips")
                print(f"  Drift: UP={stats.drift_up_pips:.1f} pips  DOWN={stats.drift_down_pips:.1f} pips  ratio={stats.drift_ratio:.2f}")
                print(f"\n[2] PerceptionBiasReport")
                print(f"  TF analysés: {bias.timeframes_analyzed}")
                print(f"  Sévérité (sur M5): {bias.bias_severity}")
                print(f"  TF recommandé: {bias.recommended_timeframe} ({bias.recommendation_reason})")
                for tf, m in bias.bias_per_timeframe.items():
                    print(f"    {tf}: dur ratio={m['dur_asymmetry_ratio']:.2f} amp ratio={m['amp_asymmetry_ratio']:.2f}")
                print(f"\n[3] BearishTimingConfig")
                print(f"  TF préféré: {timing.preferred_timeframe}")
                print(f"  TP={timing.tp_pips:.2f} pips  SL={timing.sl_pips:.2f} pips  R/R={timing.risk_reward_ratio:.2f}")
                print(f"  TimeExit={timing.time_bars} bougies  Sessions={timing.session_filter}")
                print(f"  Rationale: {timing.rationale}")
            return 0
        # Sinon : stats seules
        stats = analyzer.analyze_direction_speed(symbol=args.symbol, timeframe=args.timeframe)
        if args.json:
            print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"\n{stats.symbol} ({stats.timeframe})")
            print(f"  Bougies UP/DOWN/NEUTRAL: {stats.n_up}/{stats.n_down}/{stats.n_neutral}")
            print(f"  Durée run UP/DOWN: {stats.avg_duration_up:.2f} / {stats.avg_duration_down:.2f}")
            print(f"  Amplitude UP/DOWN pips: {stats.avg_amplitude_up_pips:.2f} / {stats.avg_amplitude_down_pips:.2f}")
            print(f"  p90 UP/DOWN: {stats.p90_amplitude_up_pips:.2f} / {stats.p90_amplitude_down_pips:.2f}")
            print(f"  Drift ratio UP/DOWN: {stats.drift_ratio:.2f}")
        return 0
    except Exception as e:
        print(f"ERREUR analyse: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())