"""ZoneDetector — alimente la table zone_diagnostics (Phase 9, gap comblé).

Calcule par devise, à chaque snapshot, un diagnostic de zone extrême à partir
de l'historique des forces du même symbol+timeframe : z-score, état de zone,
direction d'extrême, tension, pullbacks absorbés.

La table zone_diagnostics était créée (core/v9/zone_db.py) mais jamais
alimentée — ce module comble ce gap. Les 7 principes node_rule ACTIVE qui
référencent ses champs (NODE_BIRTH_FAST, ZONE_RETEST, ELASTIC_BREATH,
GRAVITY_RESPRING_NODE, POWER_ANGLE_BREAK_TO_PRICE_IMPACT,
PRICE_LAG_AT_NODE_BIRTH, RAW_NODE_BIRTH) deviennent ainsi déclenchables.

2 principes ACTIVE restent bloqués même après : ANTAGONIST_NODE (champs
cross-TF h1_state/m5_state/h1_dir/m5_dir absents du schéma zone_diagnostics)
et COALITION_NODE (champ coalition_strength absent). Dégradation gracieuse
inchangée pour ceux-ci.

Appelé par orchestrator.py entre regime_detector et principle_engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from core.v9.config import DB_PATH, DEVISES, SCHEMA_VERSION
from core.v9.db_schema import get_connection
from core.v9.zone_db import ZONE_DIAGNOSTICS_COLUMNS, init_zone_db

# Seuils de zone (calibrés sur les distributions observées en V8 et
# les données V9 — à recalibrer après n>=50 snapshots live).
Z_SCORE_THRESHOLD_EXTREME = 1.0   # |z| >= 1.0 = entrée en zone extrême
Z_SCORE_THRESHOLD_RUPTURE = 2.0   # |z| >= 2.0 = rupture
TENSION_SCORE_MIN = 0.5            # seuil plancher pour tension_score
PULLBACK_LOOKBACK = 5             # nombre de snapshots pour détecter un pullback

# États de zone (vocabulaire V8, porté tel quel — les principes YAML
# les référencent par leur nom exact).
NEUTRAL = "NEUTRAL"
EARLY_EXTREME = "EARLY_EXTREME"
ACCUMULATING = "ACCUMULATING"
LEAKING = "LEAKING"
RUPTURE = "RUPTURE"

# Directions d'extrême
UP = "UP"
DOWN = "DOWN"


class ZoneDetectorError(ValueError):
    """Erreur de détection de zone (snapshot introuvable)."""


class ZoneDetector:
    """Calcule les diagnostics de zone par devise pour un snapshot.

    Instancié par snapshot (comme les autres détecteurs V9). Charge
    l'historique des forces du même symbol+timeframe, calcule le z-score
    de chaque devise, détermine l'état de zone, et persiste dans
    zone_diagnostics.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        source_type: str = "live",
    ) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_zone_db(self.db_path)

    def _connect(self):
        conn = get_connection(self.db_path)
        conn.row_factory = None  # rows as tuples for speed
        return conn

    def detect(self, snapshot_id: str) -> None:
        """Calcule et persiste les diagnostics de zone pour un snapshot.

        Produit une ligne par devise dans zone_diagnostics. Utilise
        INSERT OR REPLACE (contrainte UNIQUE sur forces_snapshot_ref +
        currency) pour être idempotent.
        """
        conn = self._connect()
        try:
            # Charger le snapshot courant
            row = conn.execute(
                "SELECT * FROM forces_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if row is None:
                raise ZoneDetectorError(f"snapshot introuvable: {snapshot_id!r}")

            # Convertir en dict pour accès nommé
            columns = [d[1] for d in conn.execute(
                "PRAGMA table_info(forces_snapshots)"
            ).fetchall()]
            row_dict = dict(zip(columns, row))

            symbol = row_dict["symbol"]
            timeframe = row_dict["timeframe"]
            timestamp = row_dict["timestamp"]

            # Charger l'historique des forces pour ce symbol+timeframe
            history = self._load_force_history(conn, symbol, timeframe, timestamp)

            # Calculer les diagnostics par devise
            now = datetime.now(timezone.utc).isoformat()
            for currency in DEVISES:
                force_key = f"force_{currency.lower()}"
                force_value = row_dict.get(force_key)
                if force_value is None:
                    continue

                # Extraire la série historique pour cette devise
                series = [h[currency] for h in history if h[currency] is not None]

                # Calculer le z-score
                z_current = self._compute_z_score(force_value, series)

                # Déterminer l'état de zone
                state, prev_state = self._determine_zone_state(
                    conn, symbol, timeframe, currency, timestamp, z_current
                )

                # Direction de l'extrême
                z_extreme_dir = UP if z_current > 0 else DOWN

                # Bars in extreme
                bars_in_extreme = self._count_bars_in_extreme(
                    conn, symbol, timeframe, currency, timestamp, z_current
                )

                # Tension score
                tension_score = self._compute_tension_score(z_current, series)

                # Pullbacks absorbés
                absorbed_pullbacks = self._count_absorbed_pullbacks(
                    conn, symbol, timeframe, currency, timestamp, z_current
                )

                # Générer l'ID de diagnostic
                zone_id = (
                    f"zone_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_"
                    f"{symbol.lower()}_{timeframe.lower()}_{currency.lower()}_"
                    f"{uuid.uuid4().hex[:6]}"
                )

                # Absorption factor : mesure de la capacité du marché à
                # absorber la zone extrême courante. Combinaison de :
                # - tension_score (plus la tension est haute, plus l'absorption est forte)
                # - absorbed_pullbacks (chaque pullback absorbé augmente le facteur)
                # - bars_in_extreme (plus on reste dans l'extrême, plus l'absorption est forte)
                # Normalisé entre 0.0 et ~3.0 pour rester dans l'échelle V8.
                abs_z = abs(z_current)
                if abs_z >= Z_SCORE_THRESHOLD_EXTREME:
                    absorption_factor = round(
                        (tension_score * 0.4)
                        + (absorbed_pullbacks * 0.3)
                        + (min(bars_in_extreme, 10) / 10.0 * 0.3),
                        4,
                    )
                else:
                    absorption_factor = 0.0
                zone_level = round(abs(z_current), 4)
                depth_slope = 0.0
                depth_acceleration = 0.0
                context_score = 0.0
                profile_name = ""
                rank_position = 0
                rank_total = 0
                duration_bars = bars_in_extreme
                context_tags_json = "{}"
                raw_diagnosis_json = "{}"
                stale = False

                values = {
                    "zone_diagnostic_id": zone_id,
                    "schema_version": SCHEMA_VERSION,
                    "timestamp": timestamp,
                    "forces_snapshot_ref": snapshot_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "currency": currency,
                    "state": state,
                    "prev_state": prev_state,
                    "zone_level": zone_level,
                    "z_current": round(z_current, 4),
                    "z_extreme_dir": z_extreme_dir,
                    "prev_z_extreme_dir": z_extreme_dir,  # simplifié : même dir tant qu'on est dans l'extrême
                    "bars_in_extreme": bars_in_extreme,
                    "pullback_count": 0,
                    "absorbed_pullback_count": absorbed_pullbacks,
                    "depth_slope": depth_slope,
                    "depth_acceleration": depth_acceleration,
                    "absorption_factor": absorption_factor,
                    "tension_score": round(tension_score, 4),
                    "context_score": context_score,
                    "profile_name": profile_name,
                    "rank_position": rank_position,
                    "rank_total": rank_total,
                    "duration_bars": duration_bars,
                    "context_tags_json": context_tags_json,
                    "raw_diagnosis_json": raw_diagnosis_json,
                    "stale": stale,
                    "created_at": now,
                }

                placeholders = ", ".join("?" for _ in ZONE_DIAGNOSTICS_COLUMNS)
                columns_str = ", ".join(ZONE_DIAGNOSTICS_COLUMNS)
                conn.execute(
                    f"INSERT OR REPLACE INTO zone_diagnostics ({columns_str}) "
                    f"VALUES ({placeholders})",
                    [values[c] for c in ZONE_DIAGNOSTICS_COLUMNS],
                )

            conn.commit()
        finally:
            conn.close()

    def _load_force_history(
        self, conn, symbol: str, timeframe: str, upto_timestamp: str
    ) -> list[dict[str, float | None]]:
        """Charge les N derniers snapshots non-stale pour ce symbol+timeframe.

        Retourne une liste de dicts {currency: force_value} triés par
        timestamp croissant.
        """
        rows = conn.execute(
            "SELECT force_usd, force_gbp, force_eur, force_jpy, "
            "force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = ? AND timestamp <= ? AND stale = 0 "
            "ORDER BY timestamp DESC LIMIT 20",
            (symbol, timeframe, upto_timestamp),
        ).fetchall()

        result = []
        for r in reversed(rows):
            entry = {}
            for i, currency in enumerate(DEVISES):
                val = r[i]
                entry[currency] = float(val) if val is not None else None
            result.append(entry)
        return result

    @staticmethod
    def _compute_z_score(
        force_value: float, series: list[float]
    ) -> float:
        """Calcule le z-score de force_value par rapport à l'historique.

        z = (x - mean) / stdev. Si stdev = 0 ou historique < 2, retourne
        un score normalisé simple (x - 50) / 25.
        """
        if len(series) >= 2:
            m = mean(series)
            s = stdev(series)
            if s > 0:
                return (force_value - m) / s

        # Fallback : écart à la référence neutre 50, normalisé
        return (force_value - 50.0) / 25.0

    def _determine_zone_state(
        self, conn, symbol: str, timeframe: str, currency: str,
        upto_timestamp: str, z_current: float
    ) -> tuple[str, str]:
        """Détermine l'état de zone courant et l'état précédent.

        États :
        - NEUTRAL : |z| < 1.0
        - EARLY_EXTREME : |z| >= 1.0, pas d'état extrême précédent
        - ACCUMULATING : |z| >= 1.0, même direction que le snapshot précédent
        - LEAKING : |z| >= 1.0, direction opposée au snapshot précédent
        - RUPTURE : |z| >= 2.0
        """
        abs_z = abs(z_current)

        # Charger le diagnostic précédent pour cette devise
        prev_row = conn.execute(
            "SELECT state, z_current FROM zone_diagnostics "
            "WHERE symbol = ? AND timeframe = ? AND currency = ? "
            "AND timestamp < ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, timeframe, currency, upto_timestamp),
        ).fetchone()

        prev_state = prev_row[0] if prev_row else NEUTRAL

        if abs_z >= Z_SCORE_THRESHOLD_RUPTURE:
            state = RUPTURE
        elif abs_z >= Z_SCORE_THRESHOLD_EXTREME:
            if prev_state in (NEUTRAL, ""):
                state = EARLY_EXTREME
            else:
                # Vérifier si on est dans la même direction
                prev_z = prev_row[1] if prev_row else 0.0
                if (z_current > 0 and prev_z >= 0) or (z_current < 0 and prev_z <= 0):
                    state = ACCUMULATING
                else:
                    state = LEAKING
        else:
            state = NEUTRAL

        return state, prev_state

    def _count_bars_in_extreme(
        self, conn, symbol: str, timeframe: str, currency: str,
        upto_timestamp: str, z_current: float
    ) -> int:
        """Compte le nombre de snapshots consécutifs dans l'extrême.

        Remonte l'historique des diagnostics zone_diagnostics tant que
        |z| >= 1.0, ou utilise l'historique des forces si aucun
        diagnostic précédent n'existe.
        """
        abs_z = abs(z_current)
        if abs_z < Z_SCORE_THRESHOLD_EXTREME:
            return 0

        # D'abord essayer depuis zone_diagnostics
        rows = conn.execute(
            "SELECT z_current FROM zone_diagnostics "
            "WHERE symbol = ? AND timeframe = ? AND currency = ? "
            "AND timestamp < ? "
            "ORDER BY timestamp DESC",
            (symbol, timeframe, currency, upto_timestamp),
        ).fetchall()

        count = 1  # le snapshot courant
        for (z_val,) in rows:
            if z_val is not None and abs(z_val) >= Z_SCORE_THRESHOLD_EXTREME:
                count += 1
            else:
                break

        return count

    def _compute_tension_score(
        self, z_current: float, series: list[float]
    ) -> float:
        """Calcule le score de tension.

        Tension = |z| * (1 + taux_de_variation). Plus la force dévie
        rapidement de sa moyenne, plus la tension est élevée.
        """
        abs_z = abs(z_current)
        if abs_z < Z_SCORE_THRESHOLD_EXTREME:
            return 0.0

        # Taux de variation : écart-type relatif de la série récente
        if len(series) >= 3:
            recent = series[-3:]
            m = mean(recent)
            if m != 0:
                cv = stdev(recent) / abs(m) if len(recent) >= 2 else 0.1
            else:
                cv = 0.1
        else:
            cv = 0.1

        tension = abs_z * (1.0 + cv)
        return max(tension, TENSION_SCORE_MIN)

    def _count_absorbed_pullbacks(
        self, conn, symbol: str, timeframe: str, currency: str,
        upto_timestamp: str, z_current: float
    ) -> int:
        """Compte les pullbacks absorbés dans la zone extrême courante.

        Un pullback est un changement de direction temporaire (z repasse
        sous le seuil d'extrême puis remonte) qui n'a pas fait sortir
        de la zone.
        """
        abs_z = abs(z_current)
        if abs_z < Z_SCORE_THRESHOLD_EXTREME:
            return 0

        # Charger l'historique des z_current pour cette devise
        rows = conn.execute(
            "SELECT z_current FROM zone_diagnostics "
            "WHERE symbol = ? AND timeframe = ? AND currency = ? "
            "AND timestamp < ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (symbol, timeframe, currency, upto_timestamp, PULLBACK_LOOKBACK),
        ).fetchall()

        if len(rows) < 2:
            return 0

        z_values = [z_current] + [r[0] for r in rows if r[0] is not None]
        pullbacks = 0
        in_pullback = False

        for i in range(1, len(z_values)):
            prev_z = z_values[i - 1]
            curr_z = z_values[i]

            if prev_z is None or curr_z is None:
                continue

            # Un pullback = on était dans l'extrême, on en sort, puis on y retourne
            if abs(prev_z) >= Z_SCORE_THRESHOLD_EXTREME and abs(curr_z) < Z_SCORE_THRESHOLD_EXTREME:
                in_pullback = True
            elif in_pullback and abs(curr_z) >= Z_SCORE_THRESHOLD_EXTREME:
                pullbacks += 1
                in_pullback = False

        return pullbacks
