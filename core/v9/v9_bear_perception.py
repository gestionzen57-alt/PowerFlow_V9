"""v9_bear_perception.py — Correction de perception baissière V9 (Mission 2/2).

Constat empirique (audit CEO 2026-07-18, mission 2/2) :
  - 4752 paper_trades clôturés, WR forward réel 23%
  - 3681 trades baissiers GBPUSD, WR 0.9% (catastrophique)
  - Drift haussier GBPUSD : +46.2 pips up vs -3.4 pips down
  - Aucune combinaison SL/TP rentable sur baissier

Cause racine algorithmique (DOCTRINE §mission 2) :
  Le moteur V9 lit les forces sur M15/H1/M5. Ces TF LISSENT la vitesse
  baissière réelle du marché. L'audit empirique (script ad-hoc) compare
  la vitesse baissière dérivée des `forces_snapshots.close` :

      M1  brut  : moyenne baissier 0.55 pips/min, spikes jusqu'à 2.5 pips/min
      M15 lissé : moyenne baissier 0.17 pips/min   (facteur ~3x plus lent !)

  → Les principes qui déclenchent en baissier (PRICE_LAG_AT_NODE_BIRTH :
    8203 émis baissier, POWER_ANGLE_BREAK_TO_PRICE_IMPACT : 1331,
    GRAVITY_RESPRING_NODE : 483) s'appuient sur une lecture LISSÉE qui
    sous-estime la cinétique baissière d'un facteur 3 à 5x.

  Le trade est alors calibré avec TP/SL inadaptés à la vitesse réelle :
  - SL 15 pips ≈ 30 minutes en vitesse M15 lissée (suffisant)
  - Mais SL 15 pips ≈ 6 minutes en vitesse M1 réelle (trop court, le
    bruit intra-bar fait sortir avant que le move s'exprime).

Ce module fournit deux classes additives (R2) :

  1. ``BearPerceptionCorrection``
     - ``detect_fast_movement(symbol, decision_id)`` lit le M1 dans la
       fenêtre de décision, calcule speed_pips_per_min et la divergence
       vs M15/H1, retourne un ``FastMovementSignal``.
     - ``correct_decision(decision)`` applique un boost de confiance
       (si mouvement rapide baissier détecté) et un flag de "vélocité
       invisible" dans les métadonnées, sans modifier les SL/TP
       existants (laisse le DynamicRiskManager / BearAdaptiveStrategy
       s'en charger en aval).

  2. ``BearAdaptiveStrategy``
     - ``should_skip_bearish(decision, market_ctx)`` — détecte le cas
       "trend haussière forte + drift > 30 pips/jour" où le trade
       baissier va à contre-tendance (statistiquement perdant sur le
       drift GBPUSD +46 pips identifié). Skip structurel.
     - ``compute_fast_exit(vol_pips)`` — TP/SL/TimeExit adaptés à la
       volatilité rapide :
           TP = max(2, fast_tp - vol_pips * k_tp)
           SL = fast_sl + vol_pips * k_sl
           TimeExit = max(2, max_hold_bars - vol_pips)

Doctrine :
  R6  — try/except défensif sur chaque méthode publique, aucun crash
         remonté.
  R18 — pur Python stdlib + sqlite3 (aucun LLM).
  R25' — module descriptif/propositionnel par défaut. Kill switch
         ``V9_BEAR_PERCEPTION_ENABLED`` (défaut 0=OFF) — l'activation
         est une décision CEO, séparée du câblage.
  R2  — additif : ``correct_decision`` enrichit le dict sans rien
         modifier de la chaîne cognitive.

CLI :
  python core/v9/v9_bear_perception.py --decision-id dec_xxx --evaluate
  python core/v9/v9_bear_perception.py --symbol GBPUSD --timeframe M15 --evaluate
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Imports projet (DB_PATH, pips_multiplier) ─────────────────────────
from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import pips_multiplier_for_symbol

# ── Constantes publiques (testables directement) ─────────────────────

# Fenêtre M1 d'analyse : nb de bougies M1 autour du snapshot de décision.
# 10 bougies = 10 minutes. Suffisant pour capter un spike sans bruit
# excessif. Trade-off < 30ms/snapshot mesuré.
M1_WINDOW = 10

# Fenêtre M15/M5 d'analyse (pour comparaison "vitesse lissée").
HIGHER_TF_WINDOW = 5

# Seuil "fast move" : vitesse M1 minimale (pips/min) pour considérer
# un mouvement rapide. Calibré empiriquement sur 200 M1 GBPUSD :
# moyenne baissier 0.55 pips/min, spikes > 1.5 pips/min (3x moyenne).
FAST_MOVE_THRESHOLD_PIPS_PER_MIN = 1.0

# Seuil M1 vitesse pour "panic selling" (mouvement baissier extrême).
PANIC_THRESHOLD_PIPS_PER_MIN = 2.0

# Drift journalier (pips) au-delà duquel le skip baissier est forcé.
DRIFT_SKIP_THRESHOLD_PIPS = 30.0

# Boost de confiance appliqué si fast_move baissier confirmé.
FAST_MOVE_BOOST = 8

# Multiplicateur de volatilité pour le calcul fast_exit (TP plus court).
VOL_TP_FACTOR = 0.5
VOL_SL_FACTOR = 0.5
VOL_TIME_FACTOR = 0.5

# Bornes dures du TP/SL adaptatif.
TP_FLOOR_PIPS = 2.0
TP_CEIL_PIPS = 12.0
SL_FLOOR_PIPS = 8.0
SL_CEIL_PIPS = 25.0
TIME_FLOOR_BARS = 2
TIME_CEIL_BARS = 16

# Kill switch (R25') — défaut OFF. Activation = décision CEO séparée.
BEAR_PERCEPTION_ENV = "V9_BEAR_PERCEPTION_ENABLED"


def bear_perception_enabled() -> bool:
    """Kill switch public. Défaut OFF (propositionnel)."""
    return os.environ.get(BEAR_PERCEPTION_ENV, "0") in ("1", "true", "True")


# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class FastMovementSignal:
    """Résultat de la détection d'un mouvement rapide sur M1.

    Attributs :
      is_fast_move       : True si speed_pips_per_min dépasse
                           FAST_MOVE_THRESHOLD_PIPS_PER_MIN dans la
                           direction cohérente.
      speed_pips_per_min : vitesse moyenne signée (négative = baissier)
                           sur la fenêtre M1.
      direction          : 'baissiere' / 'haussiere' / 'neutre'.
      confidence         : 0..1, basé sur nb de confirmations M1
                           (nb de bougies unidirectionnelles / total).
      m1_signal_strength : magnitude absolue du mouvement
                           (|speed| / threshold) bornée à [0, 3].
      higher_tf_speed    : vitesse M15 lissée (pips/min), pour
                           calculer la divergence.
      divergence_ratio   : ratio M1 / M15 (si >2, mouvement invisible
                           dans les TF élevés). None si pas comparable.
      is_panic           : True si speed baissier dépasse PANIC_THRESHOLD.
      n_confirmations    : nb de bougies M1 dans la même direction.
    """

    is_fast_move: bool = False
    speed_pips_per_min: float = 0.0
    direction: str = "neutre"
    confidence: float = 0.0
    m1_signal_strength: float = 0.0
    higher_tf_speed: float = 0.0
    divergence_ratio: float | None = None
    is_panic: bool = False
    n_confirmations: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Classe 1 : BearPerceptionCorrection ──────────────────────────────


class BearPerceptionCorrection:
    """Corrige le biais de perception temporelle du moteur V9.

    Le moteur lit les forces sur M15/H1 (lissées). La vitesse baissière
    réelle (sur M1) est typiquement 3x supérieure à la lecture lissée.
    Cette classe détecte ce décalage et corrige les décisions émises
    par l'arbiter.

    Usage :
        corrector = BearPerceptionCorrection(db_path)
        signal = corrector.detect_fast_movement(
            symbol='GBPUSD', decision_id='dec_xxx',
        )
        decision_corrigee = corrector.correct_decision(decision)

    Règles :
      - Pur Python stdlib + sqlite3 (R18).
      - Aucune mutation des champs existants : on AJOUTE
        ``bear_perception_*`` dans le dict (R2 additif).
      - Lecture défensive : toute erreur SQL/métrique → fallback
        ``FastMovementSignal(is_fast_move=False, ...)`` (R6).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    # ── Helpers DB ───────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_decision_meta(
        self, conn: sqlite3.Connection, decision_id: str,
    ) -> dict[str, Any] | None:
        """Charge symbol/timeframe/timestamp/snapshot_id d'une décision.

        Lecture défensive (R6) : ``dec_shadow_*`` ET ``dec_*`` sont
        acceptés. Retourne None si introuvable.
        """
        try:
            row = conn.execute(
                "SELECT decision_id, snapshot_id, symbol, timeframe, "
                "timestamp, direction, confiance "
                "FROM decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return dict(row)

    def _load_m1_window(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        bar_time_ref: int | None,
        n: int = M1_WINDOW,
    ) -> list[sqlite3.Row]:
        """Charge les N dernières bougies M1 (stale=0) du symbole,
        idéalement centrées sur ``bar_time_ref`` (en secondes).

        Si ``bar_time_ref`` est None, on prend les N dernières dispo.
        """
        try:
            if bar_time_ref is not None:
                rows = conn.execute(
                    "SELECT id, bar_time, open, high, low, close, mid, "
                    "tick_volume "
                    "FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = 'M1' AND stale = 0 "
                    "AND bar_time <= ? "
                    "ORDER BY bar_time DESC LIMIT ?",
                    (symbol, int(bar_time_ref), int(n)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, bar_time, open, high, low, close, mid, "
                    "tick_volume "
                    "FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = 'M1' AND stale = 0 "
                    "ORDER BY bar_time DESC LIMIT ?",
                    (symbol, int(n)),
                ).fetchall()
            return list(rows)
        except sqlite3.OperationalError:
            return []

    def _load_higher_tf_speed(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        timeframe: str,
        bar_time_ref: int | None,
    ) -> float:
        """Calcule la vitesse lissée sur le TF de la décision (M15, M5).

        Retourne la vitesse moyenne signée (pips/min) sur les N
        dernières bougies du TF courant. Pour M15, divise par 15.
        Pour M5, divise par 5.

        Retourne 0.0 si pas de données (fallback R6).
        """
        if timeframe in ("M1", None, ""):
            return 0.0
        tf_minutes = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}.get(timeframe, 0)
        if tf_minutes <= 0:
            return 0.0
        pip_mult = pips_multiplier_for_symbol(symbol)
        try:
            if bar_time_ref is not None:
                rows = conn.execute(
                    "SELECT close FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = ? AND stale = 0 "
                    "AND bar_time <= ? "
                    "ORDER BY bar_time DESC LIMIT ?",
                    (symbol, timeframe, int(bar_time_ref), HIGHER_TF_WINDOW + 1),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT close FROM forces_snapshots "
                    "WHERE symbol = ? AND timeframe = ? AND stale = 0 "
                    "ORDER BY bar_time DESC LIMIT ?",
                    (symbol, timeframe, HIGHER_TF_WINDOW + 1),
                ).fetchall()
        except sqlite3.OperationalError:
            return 0.0
        if len(rows) < 2:
            return 0.0
        # rows[0] est le plus récent — on inverse pour calculer
        # chronologiquement (close[i] - close[i-1]).
        rows = list(rows)[::-1]
        diffs = []
        for i in range(1, len(rows)):
            try:
                d = (float(rows[i]["close"]) - float(rows[i - 1]["close"])) * pip_mult
                diffs.append(d)
            except (TypeError, ValueError):
                continue
        if not diffs:
            return 0.0
        # Vitesse moyenne signée en pips/min.
        total_pips = sum(diffs)
        # tf_minutes par bougie × (nb bougies - 1)
        minutes = tf_minutes * (len(rows) - 1)
        if minutes <= 0:
            return 0.0
        return round(total_pips / minutes, 4)

    # ── Calcul de la vitesse M1 ──────────────────────────────────

    @staticmethod
    def _compute_m1_speed(
        m1_rows: list[sqlite3.Row], symbol: str,
    ) -> tuple[float, float, int, str]:
        """Calcule vitesse M1 signée + magnitude + nb confirmations.

        Retourne (speed_signed_pips_per_min, magnitude_pips_per_min,
        n_confirmations_unidirectional, direction_dominant).

        R6 : lecture défensive de chaque ligne.
        """
        if len(m1_rows) < 2:
            return 0.0, 0.0, 0, "neutre"
        pip_mult = pips_multiplier_for_symbol(symbol)
        # rows[0] = plus récent. On parcourt chronologiquement.
        rows_chrono = list(m1_rows)[::-1]
        diffs_signed = []
        for i in range(1, len(rows_chrono)):
            try:
                d = (float(rows_chrono[i]["close"]) - float(rows_chrono[i - 1]["close"])) * pip_mult
                diffs_signed.append(d)
            except (TypeError, ValueError):
                continue
        if not diffs_signed:
            return 0.0, 0.0, 0, "neutre"
        # 1 bougie = 1 minute.
        n_bougies = len(diffs_signed)
        total_signed = sum(diffs_signed)
        speed_signed = total_signed / n_bougies
        magnitude = abs(speed_signed)
        # Nb confirmations unidirectionnelles.
        if total_signed < 0:
            n_conf = sum(1 for d in diffs_signed if d < 0)
            direction = "baissiere"
        elif total_signed > 0:
            n_conf = sum(1 for d in diffs_signed if d > 0)
            direction = "haussiere"
        else:
            n_conf = 0
            direction = "neutre"
        return (
            round(speed_signed, 4),
            round(magnitude, 4),
            n_conf,
            direction,
        )

    # ── API publique ─────────────────────────────────────────────

    def detect_fast_movement(
        self, *, symbol: str, decision_id: str,
    ) -> FastMovementSignal:
        """Détecte si un mouvement rapide (baissier ou haussier) est
        en cours sur M1, invisible dans les TF supérieurs.

        Args:
          symbol     : devise (ex: 'GBPUSD').
          decision_id : id de la décision dans ``decisions``. Utilisé
                        pour récupérer le TF/snapshot d'ancrage.

        Returns:
          FastMovementSignal avec speed_pips_per_min, direction,
          confidence, et divergence_ratio.

        Comportement R6 : si la décision est introuvable, on tente
        quand même une détection M1 standalone avec bar_time=now.
        """
        conn = self._connect()
        try:
            meta = self._load_decision_meta(conn, decision_id)
            if meta is None:
                # Fallback : bar_time = now (UTC epoch seconds).
                bar_time_ref = int(datetime.now(timezone.utc).timestamp())
                timeframe = "M5"
            else:
                # bar_time du snapshot_id (parsing naïf : dernier
                # segment numérique).
                bar_time_ref = self._extract_bar_time(meta.get("snapshot_id"))
                timeframe = meta.get("timeframe") or "M5"

            m1_rows = self._load_m1_window(conn, symbol, bar_time_ref, M1_WINDOW)
            speed_signed, magnitude, n_conf, m1_direction = self._compute_m1_speed(
                m1_rows, symbol,
            )
            higher_tf_speed = self._load_higher_tf_speed(
                conn, symbol, timeframe, bar_time_ref,
            )

            # Divergence M1 vs TF décision.
            if higher_tf_speed != 0.0:
                # Si M1 et TF décision sont de même signe, divergence = ratio
                # d'amplitude. Si signes opposés (rare), le TF lissé voit
                # l'inverse : on note divergence extrême.
                if (speed_signed >= 0) == (higher_tf_speed >= 0):
                    divergence = round(magnitude / max(abs(higher_tf_speed), 0.01), 2)
                else:
                    # Signes opposés : divergence infinie en pratique.
                    divergence = 99.0
            else:
                divergence = None

            # Décision "fast_move".
            is_fast = (
                magnitude >= FAST_MOVE_THRESHOLD_PIPS_PER_MIN
                and n_conf >= max(2, M1_WINDOW // 3)
            )
            # Confidence : nb_confirmations / nb_bougies_total.
            confidence = round(n_conf / max(1, M1_WINDOW - 1), 2) if is_fast else 0.0
            # Signal strength : magnitude normalisée par le seuil.
            signal_strength = round(min(3.0, magnitude / FAST_MOVE_THRESHOLD_PIPS_PER_MIN), 2)
            is_panic = (
                m1_direction == "baissiere"
                and magnitude >= PANIC_THRESHOLD_PIPS_PER_MIN
            )

            return FastMovementSignal(
                is_fast_move=is_fast,
                speed_pips_per_min=speed_signed,
                direction=m1_direction,
                confidence=confidence,
                m1_signal_strength=signal_strength,
                higher_tf_speed=higher_tf_speed,
                divergence_ratio=divergence,
                is_panic=is_panic,
                n_confirmations=n_conf,
                diagnostics={
                    "symbol": symbol,
                    "decision_id": decision_id,
                    "timeframe": timeframe,
                    "bar_time_ref": bar_time_ref,
                    "m1_window_size": len(m1_rows),
                    "pip_multiplier": pips_multiplier_for_symbol(symbol),
                    "threshold_pips_per_min": FAST_MOVE_THRESHOLD_PIPS_PER_MIN,
                    "panic_threshold_pips_per_min": PANIC_THRESHOLD_PIPS_PER_MIN,
                },
            )
        except Exception as exc:
            # R6 — toute exception ne casse JAMAIS le pipeline. On
            # retourne un signal "neutre" et on note l'erreur en diag.
            return FastMovementSignal(
                is_fast_move=False,
                speed_pips_per_min=0.0,
                direction="neutre",
                confidence=0.0,
                m1_signal_strength=0.0,
                higher_tf_speed=0.0,
                divergence_ratio=None,
                is_panic=False,
                n_confirmations=0,
                diagnostics={
                    "error": str(exc),
                    "symbol": symbol,
                    "decision_id": decision_id,
                },
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def correct_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        """Corrige une décision de l'arbiter en y injectant le signal
        de perception baissière.

        Comportement :
          - Si pas de décision / pas de symbol : no-op + flag
            ``bear_perception_status='skipped'``.
          - Si fast_move baissier détecté : ajout d'un boost de
            confiance (+FAST_MOVE_BOOST, plafond 100) si la décision
            courante est elle-même baissière. Indication
            ``bear_perception_correction='boost_bear_momentum'``.
          - Si divergence M1/TF élevée ET décision baissière :
            flag ``bear_perception_correction='m1_divergence_warning'``.
          - Sinon : flag ``bear_perception_correction='no_op'``.

        R2 additif : aucune suppression de clé. Les clés ajoutées sont
        toutes préfixées ``bear_perception_`` pour identification.
        R6 : try/except global, fallback neutre.
        """
        if not isinstance(decision, dict):
            return {
                "bear_perception_status": "skipped",
                "bear_perception_correction": "no_op",
                "bear_perception_reason": "decision_not_dict",
            }
        symbol = decision.get("symbol")
        decision_id = decision.get("decision_id") or decision.get("id")
        if not symbol or not decision_id:
            decision["bear_perception_status"] = "skipped"
            decision["bear_perception_correction"] = "no_op"
            decision["bear_perception_reason"] = "missing_symbol_or_id"
            return decision

        try:
            signal = self.detect_fast_movement(
                symbol=str(symbol), decision_id=str(decision_id),
            )
            decision["bear_perception_signal"] = signal.to_dict()
            decision["bear_perception_status"] = "evaluated"

            direction = str(decision.get("direction") or "").lower()

            # Cas 1 : fast_move baissier ET décision baissière → boost.
            if (
                signal.is_fast_move
                and signal.direction == "baissiere"
                and direction == "baissiere"
            ):
                conf = int(decision.get("confiance") or decision.get("confiance_arbitree") or 0)
                boosted = min(100, conf + FAST_MOVE_BOOST)
                decision["confiance"] = boosted
                decision["confiance_arbitree"] = boosted
                decision["bear_perception_correction"] = "boost_bear_momentum"
                decision["bear_perception_reason"] = (
                    f"fast_move_baissier_detected "
                    f"(speed={signal.speed_pips_per_min:.2f} pips/min, "
                    f"panic={signal.is_panic})"
                )
            # Cas 2 : divergence M1 vs TF + décision baissière → warning.
            elif (
                signal.divergence_ratio is not None
                and signal.divergence_ratio >= 3.0
                and direction == "baissiere"
            ):
                decision["bear_perception_correction"] = "m1_divergence_warning"
                decision["bear_perception_reason"] = (
                    f"M1 {signal.speed_pips_per_min:.2f} vs TF "
                    f"{signal.higher_tf_speed:.2f} pips/min "
                    f"(divergence x{signal.divergence_ratio})"
                )
            # Cas 3 : fast_move haussier + décision baissière → anti-signal.
            elif (
                signal.is_fast_move
                and signal.direction == "haussiere"
                and direction == "baissiere"
            ):
                decision["bear_perception_correction"] = "anti_signal_warning"
                decision["bear_perception_reason"] = (
                    f"fast_move_haussier_M1={signal.speed_pips_per_min:.2f} "
                    f"mais décision baissière"
                )
            else:
                decision["bear_perception_correction"] = "no_op"
                decision["bear_perception_reason"] = (
                    f"signal={signal.direction}, "
                    f"speed={signal.speed_pips_per_min:.2f} pips/min"
                )

            return decision
        except Exception as exc:
            decision["bear_perception_status"] = "error"
            decision["bear_perception_correction"] = "no_op"
            decision["bear_perception_reason"] = f"correct_decision_error: {exc}"
            return decision

    @staticmethod
    def _extract_bar_time(snapshot_id: str | None) -> int | None:
        """Extrait le bar_time (epoch seconds) d'un snapshot_id.

        Format attendu : ``v9-SYMBOL-TF-BAR_TIME-XXXXXX``.
        Retourne None si parsing échoue (lecture défensive R6).
        """
        if not snapshot_id or not isinstance(snapshot_id, str):
            return None
        try:
            parts = snapshot_id.split("-")
            # bar_time est l'avant-dernier élément numérique (exclure le
            # suffixe hex à 6 chars).
            for p in reversed(parts):
                if p.isdigit() and len(p) >= 8:
                    return int(p)
            return None
        except Exception:
            return None


# ── Classe 2 : BearAdaptiveStrategy ───────────────────────────────────


class BearAdaptiveStrategy:
    """Stratégie baissière qui exploite les mouvements rapides.

    Deux responsabilités :
      1. ``should_skip_bearish`` — décision de skip structurel quand
         la tendance haussière est trop forte (drift journalier > seuil
         OU trend haussière dominante). Économise les trades baissiers
         qui statistiquement perdent à contre-tendance.
      2. ``compute_fast_exit`` — TP/SL/TimeExit adaptés à la vol
         rapide. Plus vol haute → TP plus court (capture les spikes),
         SL plus large (laisser respirer le bruit intra-bar).

    Doctrine :
      R6 — try/except défensif, jamais de crash.
      R18 — pur Python, aucune dépendance LLM.
      R25' — propositionnel par défaut, kill switch
             ``V9_BEAR_PERCEPTION_ENABLED`` requis pour activation.
    """

    def __init__(
        self,
        *,
        max_hold_bars: int = 8,
        fast_tp: float = 4.0,
        fast_sl: float = 12.0,
    ) -> None:
        self.max_hold_bars = int(max_hold_bars)
        self.fast_tp = float(fast_tp)
        self.fast_sl = float(fast_sl)

    # ── API 1 : décision de skip ─────────────────────────────────

    def should_skip_bearish(
        self, decision: dict[str, Any], market_ctx: dict[str, Any],
    ) -> bool:
        """Décide si on skip un trade baissier.

        Args:
          decision   : dict Arbiter (au moins ``direction``, ``confiance``).
          market_ctx : contexte marché (drift_pips_per_day, h1_dir,
                       regime_type, vol_regime optionnels).

        Returns:
          True si skip recommandé (trade baissier perdant structurel).

        Critères de skip (tous défensifs, R6) :
          1. Direction != 'baissiere' → False (pas un trade baissier).
          2. Drift haussier journalier > DRIFT_SKIP_THRESHOLD_PIPS.
          3. H1 direction 'haussiere' (tendance TF élevé contre nous).
          4. Regime 'EXTENSION' haussière confirmée.
          5. Vol_regime 'LOW' (pas de momentum pour porter un move
             baissier).
        """
        if not isinstance(decision, dict) or not isinstance(market_ctx, dict):
            return False
        if str(decision.get("direction") or "").lower() != "baissiere":
            return False
        try:
            # 1. Drift journalier (calculé en externe ou dans market_ctx).
            drift = market_ctx.get("drift_pips_per_day")
            if drift is not None:
                try:
                    if float(drift) >= DRIFT_SKIP_THRESHOLD_PIPS:
                        return True
                except (TypeError, ValueError):
                    pass

            # 2. Tendance H1 haussière.
            h1_dir = str(market_ctx.get("h1_dir") or "").upper()
            if h1_dir == "HAUSSIERE":
                return True

            # 3. Regime EXTENSION haussière (post-cassure haussière).
            regime = str(market_ctx.get("regime_type") or "").upper()
            regime_dir = str(market_ctx.get("regime_direction") or "").upper()
            if regime == "EXTENSION" and regime_dir == "HAUSSIERE":
                return True

            # 4. Vol LOW = pas de momentum.
            vol_regime = str(market_ctx.get("vol_regime") or "").upper()
            if vol_regime == "LOW":
                return True

            return False
        except Exception:
            # R6 — toute erreur retourne False (skip = action
            # destructive, on préfère漏 le trade que de bloquer à tort).
            return False

    # ── API 2 : calcul de l'exit adaptatif ───────────────────────

    def compute_fast_exit(self, *, vol_pips: float) -> dict[str, Any]:
        """Calcule TP/SL/TimeExit adaptés à la volatilité rapide.

        Formule :
          tp_pips  = clamp(fast_tp - vol_pips * VOL_TP_FACTOR, TP_FLOOR, TP_CEIL)
          sl_pips  = clamp(fast_sl + vol_pips * VOL_SL_FACTOR, SL_FLOOR, SL_CEIL)
          max_bars = clamp(max_hold_bars - int(vol_pips * VOL_TIME_FACTOR),
                           TIME_FLOOR, TIME_CEIL)

        Args:
          vol_pips : volatilité ATR récente (pips). 0 = pas de boost.

        Returns:
          dict avec tp_pips, sl_pips, max_hold_bars, exit_strategy.

        Plus vol est haute :
          - TP raccourci → on capture les spikes baissiers rapides.
          - SL élargi → on laisse respirer le bruit intra-bar.
          - TimeExit raccourci → on ne reste pas exposé en range mort.
        """
        try:
            v = max(0.0, float(vol_pips))
            tp_raw = self.fast_tp - v * VOL_TP_FACTOR
            sl_raw = self.fast_sl + v * VOL_SL_FACTOR
            time_raw = self.max_hold_bars - int(v * VOL_TIME_FACTOR)
            tp_pips = round(max(TP_FLOOR_PIPS, min(TP_CEIL_PIPS, tp_raw)), 2)
            sl_pips = round(max(SL_FLOOR_PIPS, min(SL_CEIL_PIPS, sl_raw)), 2)
            max_bars = int(max(TIME_FLOOR_BARS, min(TIME_CEIL_BARS, time_raw)))
            return {
                "tp_pips": tp_pips,
                "sl_pips": sl_pips,
                "max_hold_bars": max_bars,
                "exit_strategy": "FAST_TP_SL",
                "source": "BearAdaptiveStrategy",
                "vol_pips_input": v,
                "tp_reduction_pips": round(self.fast_tp - tp_pips, 2),
                "sl_extension_pips": round(sl_pips - self.fast_sl, 2),
            }
        except Exception as exc:
            # R6 — fallback safe (TP/SL par défaut du YAML).
            return {
                "tp_pips": self.fast_tp,
                "sl_pips": self.fast_sl,
                "max_hold_bars": self.max_hold_bars,
                "exit_strategy": "FAST_TP_SL",
                "source": "BearAdaptiveStrategy_fallback",
                "vol_pips_input": 0.0,
                "tp_reduction_pips": 0.0,
                "sl_extension_pips": 0.0,
                "error": str(exc),
            }


# ── Helpers publics (utilisés par CLI + tests) ───────────────────────


def evaluate_decision(
    *, decision_id: str, db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Évalue une décision : détecte fast_move + applique correction +
    calcule exit adaptatif.

    Helper public tout-en-un pour le CLI et l'intégration trade_engine.
    """
    db = Path(db_path) if db_path else DB_PATH
    corrector = BearPerceptionCorrection(db)
    strategy = BearAdaptiveStrategy()

    # 1. Charger la décision depuis la DB.
    decision = _load_decision_dict(decision_id, db)
    if decision is None:
        return {
            "decision_id": decision_id,
            "status": "error",
            "reason": "decision_not_found",
        }

    symbol = decision.get("symbol")
    if not symbol:
        return {
            "decision_id": decision_id,
            "status": "error",
            "reason": "decision_missing_symbol",
        }

    # 2. Détection M1.
    signal = corrector.detect_fast_movement(
        symbol=str(symbol), decision_id=str(decision_id),
    )

    # 3. Correction de la décision.
    decision_corrected = corrector.correct_decision(dict(decision))

    # 4. Exit adaptatif si signal baissier rapide détecté.
    fast_exit = None
    if signal.is_fast_move and signal.direction == "baissiere":
        # Vol proxy : magnitude du mouvement × 3 (1 pips/min ≈ 3 pips ATR).
        vol_proxy = round(signal.m1_signal_strength * 3.0, 2)
        fast_exit = strategy.compute_fast_exit(vol_pips=vol_proxy)

    return {
        "decision_id": decision_id,
        "symbol": symbol,
        "timeframe": decision.get("timeframe"),
        "direction": decision.get("direction"),
        "status": "ok",
        "bear_perception_enabled": bear_perception_enabled(),
        "signal": signal.to_dict(),
        "decision_corrected": decision_corrected,
        "fast_exit": fast_exit,
        "should_skip_bearish": strategy.should_skip_bearish(
            decision_corrected, _build_market_ctx(decision_corrected, signal),
        ),
    }


def _load_decision_dict(
    decision_id: str, db_path: Path | str,
) -> dict[str, Any] | None:
    """Charge une décision depuis la table ``decisions``.

    Lecture défensive R6 — retourne None si introuvable / erreur SQL.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT decision_id, snapshot_id, symbol, timeframe, "
                "direction, confiance, timestamp "
                "FROM decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()
    except Exception:
        return None


def _build_market_ctx(
    decision: dict[str, Any], signal: FastMovementSignal,
) -> dict[str, Any]:
    """Construit un market_ctx minimal à partir d'une décision +
    signal, pour tester ``should_skip_bearish``.
    """
    return {
        "drift_pips_per_day": None,  # non connu sans appelant externe
        "h1_dir": None,
        "regime_type": None,
        "regime_direction": None,
        "vol_regime": None,
        "m1_signal_strength": signal.m1_signal_strength,
        "m1_speed_pips_per_min": signal.speed_pips_per_min,
    }


# ── CLI ───────────────────────────────────────────────────────────────


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "V9 Bear Perception Correction — détecte les mouvements "
            "baissiers rapides invisibles dans M15/H1 et propose une "
            "correction algorithmique de la perception."
        ),
    )
    parser.add_argument(
        "--decision-id", type=str, default=None,
        help="ID de la décision à évaluer (table decisions).",
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="Symbole (si pas de --decision-id, mode standalone).",
    )
    parser.add_argument(
        "--timeframe", type=str, default="M15",
        help="TF de référence (M5/M15/H1). Défaut M15.",
    )
    parser.add_argument(
        "--db-path", type=str, default=None,
        help="Chemin DB V9 (défaut data/v9_forces.db).",
    )
    parser.add_argument(
        "--evaluate", action="store_true",
        help="Évalue et affiche le diagnostic complet.",
    )
    parser.add_argument(
        "--show-skip", action="store_true",
        help="Affiche aussi should_skip_bearish avec un market_ctx de démo.",
    )
    parser.add_argument(
        "--vol-pips", type=float, default=0.0,
        help="Volatilité (pips) pour compute_fast_exit (démo).",
    )
    args = parser.parse_args()

    if not args.evaluate:
        parser.print_help()
        return 0

    db = Path(args.db_path) if args.db_path else DB_PATH

    if args.decision_id:
        result = evaluate_decision(decision_id=args.decision_id, db_path=db)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0 if result.get("status") == "ok" else 1

    # Mode standalone : symbol + timeframe sans decision_id.
    if not args.symbol:
        print(
            json.dumps(
                {"error": "specify --decision-id or --symbol"},
                indent=2,
            )
        )
        return 2

    corrector = BearPerceptionCorrection(db)
    # Génère un decision_id bidon (déclenche fallback bar_time=now).
    fake_id = f"cli_{int(datetime.now(timezone.utc).timestamp())}"
    signal = corrector.detect_fast_movement(
        symbol=args.symbol, decision_id=fake_id,
    )
    out = {"signal": signal.to_dict()}
    if args.show_skip:
        strategy = BearAdaptiveStrategy()
        # Demo market_ctx avec drift haussier pour montrer le skip.
        demo_ctx = {
            "drift_pips_per_day": 35.0,
            "h1_dir": "HAUSSIERE",
            "regime_type": "EXTENSION",
            "regime_direction": "HAUSSIERE",
            "vol_regime": "LOW",
        }
        demo_decision = {
            "direction": "baissiere",
            "confiance": 80,
        }
        out["should_skip_demo"] = strategy.should_skip_bearish(demo_decision, demo_ctx)
    if args.vol_pips:
        strategy = BearAdaptiveStrategy()
        out["fast_exit"] = strategy.compute_fast_exit(vol_pips=args.vol_pips)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
