"""v9_kalman_forecast.py — P1-3 motion CEO 48h Champ libre.

Forward projection avec Kalman filter au lieu de linear regression.
Detecte les changements de pente (inflection).

Auteur : Hermes (P1-3 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.kalman")


class KalmanFilter1D:
    """Kalman filter 1D pour tracking d'un signal + sa pente."""

    def __init__(self, process_variance: float = 1e-5,
                 measurement_variance: float = 1e-2):
        self.process_var = process_variance
        self.meas_var = measurement_variance
        # State: [level, velocity]
        self.x = 0.0  # level
        self.v = 0.0  # velocity (slope)
        self.p_level = 1.0
        self.p_velocity = 1.0

    def update(self, measurement: float) -> tuple[float, float]:
        """Update avec nouvelle mesure, retourne (level, velocity)."""
        # Prediction
        x_pred = self.x + self.v
        v_pred = self.v
        p_level_pred = self.p_level + self.p_velocity + self.process_var
        p_velocity_pred = self.p_velocity + self.process_var
        # Update
        k_level = p_level_pred / (p_level_pred + self.meas_var)
        k_velocity = p_velocity_pred / (p_level_pred + self.meas_var)
        innovation = measurement - x_pred
        self.x = x_pred + k_level * innovation
        self.v = v_pred + k_velocity * innovation
        self.p_level = (1 - k_level) * p_level_pred
        self.p_velocity = (1 - k_velocity) * p_velocity_pred
        return self.x, self.v

    def forecast(self, n_steps: int) -> tuple[float, float]:
        """Forecast n steps ahead, retourne (forecast, uncertainty)."""
        forecast = self.x + self.v * n_steps
        # Uncertainty grows with sqrt(steps)
        uncertainty = (self.p_level + self.p_velocity * n_steps) ** 0.5
        return forecast, uncertainty


def kalman_projection(closes: list[float], horizon: int = 4) -> dict:
    """Projection forward avec Kalman filter."""
    if len(closes) < 5:
        return {"error": "insufficient_data"}
    kf = KalmanFilter1D()
    for c in closes:
        kf.update(c)
    forecast, uncertainty = kf.forecast(horizon)
    last = closes[-1]
    delta = forecast - last
    delta_pct = (delta / last * 100) if last != 0 else 0
    # Confidence : inverse de l'incertitude relative
    confidence = max(0.0, min(1.0, 1.0 - uncertainty / max(abs(last), 0.001)))
    direction = "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"
    # Detect inflection : compare velocity actuelle vs velocity moyenne
    kf2 = KalmanFilter1D()
    velocities = []
    for c in closes[:-1]:
        kf2.update(c)
        velocities.append(kf2.v)
    if velocities:
        avg_velocity = sum(velocities) / len(velocities)
        velocity_change = kf.v - avg_velocity
        if abs(velocity_change) > 0.001:
            inflection = ("BULLISH_INFLECTION"
                            if velocity_change > 0
                            else "BEARISH_INFLECTION")
        else:
            inflection = "NO_INFLECTION"
    else:
        inflection = "NO_DATA"
    return {
        "horizon": horizon,
        "current": round(last, 5),
        "projected": round(forecast, 5),
        "delta": round(delta, 5),
        "delta_pct": round(delta_pct, 3),
        "direction": direction,
        "uncertainty": round(uncertainty, 5),
        "confidence": round(confidence, 3),
        "velocity": round(kf.v, 6),
        "inflection": inflection,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 Kalman forecast (P1-3)",
    )
    parser.add_argument("--horizon", type=int, default=4)
    args = parser.parse_args(argv)

    import sqlite3
    from core.v9.config import DB_PATH
    closes = []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT close FROM candles_d WHERE symbol = 'GBPUSD'
                ORDER BY timestamp DESC LIMIT 30
            """).fetchall()
            closes = [float(r[0]) for r in rows][::-1]
        finally:
            conn.close()
    except Exception:
        pass
    result = kalman_projection(closes, horizon=args.horizon)
    print("=" * 70)
    print(f"P1-3 — KALMAN FORECAST (H+{args.horizon})")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"Current       : {result['current']}")
    print(f"Projected     : {result['projected']}")
    print(f"Delta         : {result['delta']} ({result['delta_pct']:+.2f}%)")
    print(f"Direction     : {result['direction']}")
    print(f"Uncertainty   : {result['uncertainty']}")
    print(f"Confidence    : {result['confidence']}")
    print(f"Velocity      : {result['velocity']}")
    print(f"Inflection    : {result['inflection']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())