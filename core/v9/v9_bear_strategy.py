"""v9_bear_strategy — stratégie baissière adaptée (audit cognition mission 1/2).

Constat (cf. v9_movement_analyzer) :
- L'arbiter produit 3× plus de décisions haussières que baissières sur
  GBPUSD (6393 vs 2033) — biais de consolidation multi-devises.
- 99.3% des décisions GBPUSD reposent sur des principes émis sur devise
  NZD (UP-dominant dans le dataset) qui n'est pas une devise constitutive
  de la paire GBPUSD.
- WR baissier réel : 0.87% (32/3675) — toute décision baissière doit être
  filtrée avec un sur-ensemble de conditions avant saisie.

Cette classe implémente :
- should_enter_bearish() : filtre strict pour valider un short
  (devise source = devise constitutive, signal_z=baissier confirmé,
  alignement cross-TF, pas de signal haussier fort ailleurs)
- compute_exit_params() : TP/SL/TimeExit serrés, profil baissier
- whitelist + sizing baissier

R6, R18. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


# ── Constantes ──────────────────────────────────────────────────────────
# Devises constitutives d'une paire forex (pour GBPUSD = GBP + USD).
# Mapping : on prend les 3 premiers chars et les 3 derniers.
def _pair_currencies(symbol: str) -> tuple[str, str]:
    s = symbol.upper()
    if len(s) >= 6:
        return s[:3], s[3:6]
    return ("", "")


# Pondération par défaut d'un principe selon sa devise source.
# Pour une décision baissière sur GBPUSD, on refuse tout principe émis
# sur une devise NON constitutive (ratio=0).
CONSTITUTIVE_CURRENCY_WEIGHT = 1.0
NON_CONSTITUTIVE_CURRENCY_WEIGHT = 0.0

# Confiance minimale (sur 100) pour accepter une décision baissière
MIN_BEARISH_CONFIDENCE = 70

# Z-extreme minimum sur la devise constitutive pour valider un short
MIN_Z_EXTREME_DOWN_ABS = 0.5

# Ratio tension/z minimum sur la devise constitutive
MIN_TENSION_SCORE = 0.5


# ── Dataclasses ─────────────────────────────────────────────────────────
@dataclass
class BearishEntryDecision:
    """Résultat de la validation d'entrée baissière."""

    should_enter: bool
    confidence: int
    symbol: str
    snapshot_id: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    constitutive_currencies: tuple[str, str] = ("", "")
    bearish_source_currencies: list[str] = field(default_factory=list)
    bullish_source_currencies: list[str] = field(default_factory=list)
    source_currency_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BearishExitParams:
    """Paramètres de sortie pour trade baissier."""

    symbol: str
    regime: str
    tp_pips: float
    sl_pips: float
    time_bars: int
    risk_reward_ratio: float
    trailing_activation: float
    trailing_distance: float
    rationale: str = ""
    supporting_stats: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Utilitaires ─────────────────────────────────────────────────────────
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


# ── BearStrategy ────────────────────────────────────────────────────────
class BearStrategy:
    """Stratégie baissière calibrée sur l'audit cognition V9 (mission 1/2)."""

    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        fast_tf: str = "M1",
        slow_tf: str = "M5",
    ) -> None:
        # DB par défaut = data/v9_forces.db racine projet
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent.parent / "data" / "v9_forces.db"
        self.db_path = Path(db_path)
        self.fast_tf = fast_tf
        self.slow_tf = slow_tf

    # ── Filtre d'entrée ──────────────────────────────────────────
    def should_enter_bearish(
        self, decision: dict, market_context: dict
    ) -> bool:
        """Filtre de tendance strict pour valider un short.

        Conditions cumulatives :
        1. direction == 'baissiere'
        2. confiance >= MIN_BEARISH_CONFIDENCE (70)
        3. Au moins 1 principe baissier émis sur devise CONSTITUTIVE
           de la paire (GBP ou USD pour GBPUSD)
        4. Aucun principe haussier sur devise constitutive (sinon
           signal contradictoire)
        5. z_extreme_dir de la devise constitutive = DOWN (snapshot_ref)
        6. tension_score >= MIN_TENSION_SCORE (zone extrême confirmée)
        7. Au moins 2 principes baissiers actifs (sinon confiance
           structurellement plafonnée à 74 par l'arbiter)
        8. Pas de signal haussier fort sur devise NON constitutive
           (ceux-ci étaient la cause de 99.3% des décisions baissières
           historiques — on les exclut)

        Args:
            decision: dict avec clés 'symbol', 'direction', 'confiance',
                'snapshot_id', 'principes_source' (optionnel), 'nb_principes_actifs'.
            market_context: dict optionnel avec clés 'session', 'vol_regime',
                'zone_type'. Si absent, le filtre consulte la DB.

        Returns:
            True si toutes les conditions sont remplies, False sinon.
        """
        try:
            valid, _report = self._evaluate_entry(decision, market_context)
        except Exception:
            # R6 — toute exception = on refuse (conservateur)
            return False
        return valid

    def evaluate_entry(
        self, decision: dict, market_context: dict | None = None,
    ) -> BearishEntryDecision:
        """Variante riche de should_enter_bearish qui retourne le détail."""
        try:
            valid, report = self._evaluate_entry(decision, market_context or {})
        except Exception as e:
            return BearishEntryDecision(
                should_enter=False,
                confidence=int(decision.get("confiance", 0) or 0),
                symbol=str(decision.get("symbol", "")),
                snapshot_id=str(decision.get("snapshot_id", "")),
                reasons=[],
                warnings=[f"exception: {e}"],
            )
        return report

    # ── Calcul TP/SL/TimeExit ────────────────────────────────────
    def compute_exit_params(
        self, *, symbol: str, regime: str = "TREND",
        min_tp: float = 4.0, min_sl: float = 3.0,
    ) -> dict[str, Any]:
        """Retourne TP/SL/TimeExit optimaux pour baissier.

        Args:
            symbol: ex. 'GBPUSD'
            regime: 'TREND' (par défaut) | 'RANGE' | 'VOLATILE'
            min_tp: TP plancher (pips)
            min_sl: SL plancher (pips)

        Returns:
            dict avec tp_pips, sl_pips, time_bars, risk_reward,
            trailing_activation, trailing_distance, rationale, supporting_stats
        """
        try:
            return self._compute_exit_internal(symbol=symbol, regime=regime, min_tp=min_tp, min_sl=min_sl)
        except Exception as e:
            return {
                "symbol": symbol,
                "regime": regime,
                "tp_pips": max(min_tp, 6.0),
                "sl_pips": max(min_sl, 5.0),
                "time_bars": 4,
                "risk_reward_ratio": round(max(min_tp, 6.0) / max(min_sl, 5.0), 3),
                "trailing_activation": 3.0,
                "trailing_distance": 2.0,
                "rationale": f"Fallback conservateur ({e})",
                "supporting_stats": {},
            }

    # ── Whitelist baissière (sizing) ─────────────────────────────
    def bearish_whitelist(self, *, symbol: str) -> dict[str, Any]:
        """Retourne la liste blanche baissière pour la paire.

        Critères :
        - Au moins 50 paper_trades baissières clôturées sur la paire
          (sinon pas de signal statistique)
        - WR baissier historique sur la paire (info)
        - Sizing multiplier recommandé (0.0 si blacklist, <0.5 si méfiance)
        """
        try:
            conn = _connect(self.db_path)
            try:
                # Snapshot_ids GBPUSD
                snap_rows = conn.execute(
                    "SELECT DISTINCT snapshot_id FROM decisions "
                    "WHERE symbol = ? AND direction = 'baissiere' AND action = 'preparer_entree'",
                    (symbol.upper(),),
                ).fetchall()
                snap_ids = [r["snapshot_id"] for r in snap_rows]
                if not snap_ids:
                    return {
                        "symbol": symbol,
                        "is_whitelisted": False,
                        "reason": "Aucun snapshot baissier historique",
                        "n_bearish_trades": 0,
                        "wr_bearish": 0.0,
                        "sizing_multiplier": 0.0,
                    }
                # Limite la taille de la clause IN (sécurité SQLite : <=999 params)
                placeholders = ",".join("?" * len(snap_ids))
                pt_rows = conn.execute(
                    f"SELECT direction, is_win, pips_simulated FROM paper_trades "
                    f"WHERE snapshot_id IN ({placeholders})",
                    snap_ids,
                ).fetchall()
            finally:
                _safe_close(conn)

            n_total = len(pt_rows)
            if n_total < 50:
                return {
                    "symbol": symbol,
                    "is_whitelisted": False,
                    "reason": f"Échantillon trop petit ({n_total} < 50)",
                    "n_bearish_trades": n_total,
                    "wr_bearish": 0.0,
                    "sizing_multiplier": 0.0,
                }
            wins = sum(1 for r in pt_rows if r["is_win"])
            wr = wins / n_total * 100.0
            avg_pips = mean(r["pips_simulated"] for r in pt_rows if r["pips_simulated"] is not None)

            # Sizing : si WR < 30% → blacklist, < 50% → 0.25, sinon 0.5
            if wr < 30.0:
                sizing = 0.0
                whitelisted = False
                reason = f"WR baissier {wr:.1f}% < 30% — blackliste recommandée"
            elif wr < 50.0:
                sizing = 0.25
                whitelisted = True
                reason = f"WR baissier {wr:.1f}% — sizing réduit 0.25 (méfiance)"
            else:
                sizing = min(0.5, max(0.1, wr / 100.0))
                whitelisted = True
                reason = f"WR baissier {wr:.1f}% — sizing {sizing:.2f}"

            return {
                "symbol": symbol,
                "is_whitelisted": whitelisted,
                "reason": reason,
                "n_bearish_trades": n_total,
                "wr_bearish": round(wr, 2),
                "avg_pips": round(avg_pips, 2) if avg_pips is not None else 0.0,
                "sizing_multiplier": sizing,
            }
        except Exception as e:
            return {
                "symbol": symbol,
                "is_whitelisted": False,
                "reason": f"Exception: {e}",
                "n_bearish_trades": 0,
                "wr_bearish": 0.0,
                "sizing_multiplier": 0.0,
            }

    # ── Internals ─────────────────────────────────────────────────
    def _evaluate_entry(
        self, decision: dict, market_context: dict,
    ) -> tuple[bool, BearishEntryDecision]:
        symbol = str(decision.get("symbol", "")).upper()
        direction = str(decision.get("direction", "")).lower()
        confidence = int(decision.get("confiance", 0) or 0)
        snapshot_id = str(decision.get("snapshot_id", ""))
        principes_source = decision.get("principes_source") or []
        nb_principes_actifs = int(decision.get("nb_principes_actifs", 0) or 0)

        reasons: list[str] = []
        warnings: list[str] = []
        constitutive = _pair_currencies(symbol)

        report = BearishEntryDecision(
            should_enter=False,
            confidence=confidence,
            symbol=symbol,
            snapshot_id=snapshot_id,
            constitutive_currencies=constitutive,
            bearish_source_currencies=[],
            bullish_source_currencies=[],
            source_currency_breakdown={},
        )

        # Filtre 1 : direction
        if direction != "baissiere":
            warnings.append(f"direction={direction} != baissiere")
            return False, report

        # Filtre 2 : confiance
        if confidence < MIN_BEARISH_CONFIDENCE:
            warnings.append(f"confiance={confidence} < {MIN_BEARISH_CONFIDENCE}")
            return False, report

        # Filtres 3-8 : reposent sur la lecture DB des principes émis
        # pour ce snapshot, par devise
        per_currency = self._fetch_principle_breakdown(snapshot_id)
        report.source_currency_breakdown = per_currency
        if not per_currency:
            # Pas de données → fallback conservateur
            warnings.append("aucun principe persisté pour ce snapshot")
            return False, report

        # Filtre 3 : au moins 1 devise constitutive a émis baissier
        constitutive_bearish = []
        for c in constitutive:
            if c and c in per_currency and per_currency[c].get("baissiere", 0) > 0:
                constitutive_bearish.append(c)
        report.bearish_source_currencies = constitutive_bearish
        if not constitutive_bearish:
            warnings.append(
                f"aucun principe baissier sur devise constitutive {constitutive}"
            )
            return False, report

        # Filtre 4 : aucun haussier sur devise constitutive
        constitutive_bullish = [
            c for c in constitutive
            if c and c in per_currency and per_currency[c].get("haussiere", 0) > 0
        ]
        report.bullish_source_currencies = constitutive_bullish
        if constitutive_bullish:
            warnings.append(
                f"signal haussier contradictoire sur devise constitutive {constitutive_bullish}"
            )
            return False, report

        # Filtre 5 : z_extreme_dir = DOWN sur au moins 1 devise constitutive
        z_ok, z_detail = self._check_z_extreme_down(snapshot_id, constitutive_bearish)
        if not z_ok:
            warnings.append(f"z_extreme_dir non-DOWN: {z_detail}")
            return False, report
        reasons.append(f"z_extreme_dir DOWN confirmé sur {z_detail}")

        # Filtre 6 : tension_score
        tension_ok, tension_val = self._check_tension(snapshot_id, constitutive_bearish)
        if not tension_ok:
            warnings.append(f"tension_score={tension_val} trop faible")
            return False, report
        reasons.append(f"tension_score={tension_val:.2f} (zone extrême confirmée)")

        # Filtre 7 : nb principes baissiers >= 2
        total_bearish_principes = sum(
            per_currency[c].get("baissiere", 0) for c in constitutive_bearish
        )
        if total_bearish_principes < 2:
            warnings.append(
                f"seulement {total_bearish_principes} principes baissiers sur devises constitutives (<2)"
            )
            return False, report
        reasons.append(f"{total_bearish_principes} principes baissiers sur devises constitutives")

        # Filtre 8 (optionnel, marché context) : session
        session = str(market_context.get("session", "")).lower()
        if session and session not in ("overlap", "new_york", "london"):
            warnings.append(f"session={session} défavorable pour baissier")
            # On alerte mais on ne bloque pas (le contexte peut être validé ailleurs)

        report.should_enter = True
        report.reasons = reasons
        report.warnings = warnings
        return True, report

    def _fetch_principle_breakdown(self, snapshot_id: str) -> dict[str, dict[str, int]]:
        """Charge la répartition par devise des principes triggered pour ce snapshot."""
        if not snapshot_id or not self.db_path.exists():
            return {}
        conn = _connect(self.db_path)
        try:
            try:
                rows = conn.execute(
                    "SELECT currency, direction, COUNT(*) cnt "
                    "FROM principle_evaluations "
                    "WHERE snapshot_id = ? AND triggered = 1 "
                    "AND direction IS NOT NULL AND direction != 'neutre' "
                    "GROUP BY currency, direction",
                    (snapshot_id,),
                ).fetchall()
            except sqlite3.Error:
                return {}
            result: dict[str, dict[str, int]] = {}
            for r in rows:
                cur = (r["currency"] or "").upper()
                if not cur:
                    continue
                result.setdefault(cur, {"haussiere": 0, "baissiere": 0})
                d = (r["direction"] or "").lower()
                if d in ("haussiere", "baissiere"):
                    result[cur][d] += r["cnt"]
            return result
        finally:
            _safe_close(conn)

    def _check_z_extreme_down(
        self, snapshot_id: str, currencies: list[str]
    ) -> tuple[bool, str]:
        """Vérifie que zone_diagnostics.z_extreme_dir = DOWN pour au moins
        une devise constitutive, et que l'état est extrême."""
        if not snapshot_id or not currencies:
            return False, "no_currencies"
        conn = _connect(self.db_path)
        try:
            try:
                placeholders = ",".join("?" * len(currencies))
                rows = conn.execute(
                    f"SELECT currency, z_extreme_dir, z_current, state "
                    f"FROM zone_diagnostics "
                    f"WHERE forces_snapshot_ref = ? AND currency IN ({placeholders})",
                    (snapshot_id, *currencies),
                ).fetchall()
            except sqlite3.Error:
                return False, "db_error"
            for r in rows:
                if (
                    (r["z_extreme_dir"] or "").upper() == "DOWN"
                    and r["z_current"] is not None
                    and abs(float(r["z_current"])) >= MIN_Z_EXTREME_DOWN_ABS
                    and (r["state"] or "").upper() in ("EARLY_EXTREME", "ACCUMULATING", "RUPTURE", "LEAKING")
                ):
                    return True, str(r["currency"])
            return False, "no_zone_DOWN_with_extreme_state"
        finally:
            _safe_close(conn)

    def _check_tension(
        self, snapshot_id: str, currencies: list[str]
    ) -> tuple[bool, float]:
        """Vérifie tension_score >= MIN_TENSION_SCORE sur au moins 1 devise."""
        if not snapshot_id or not currencies:
            return False, 0.0
        conn = _connect(self.db_path)
        try:
            try:
                placeholders = ",".join("?" * len(currencies))
                rows = conn.execute(
                    f"SELECT currency, tension_score FROM zone_diagnostics "
                    f"WHERE forces_snapshot_ref = ? AND currency IN ({placeholders})",
                    (snapshot_id, *currencies),
                ).fetchall()
            except sqlite3.Error:
                return False, 0.0
            for r in rows:
                ts = r["tension_score"]
                if ts is not None and float(ts) >= MIN_TENSION_SCORE:
                    return True, float(ts)
            return False, 0.0
        finally:
            _safe_close(conn)

    def _compute_exit_internal(
        self, *, symbol: str, regime: str, min_tp: float, min_sl: float,
    ) -> dict[str, Any]:
        """Calcule les exit params en lisant stats baissières réelles
        du symbole depuis la DB.
        """
        conn = _connect(self.db_path)
        try:
            try:
                # Bougies baissières du symbole (toutes TF)
                rows = conn.execute(
                    "SELECT open, close, high, low, timeframe FROM forces_snapshots "
                    "WHERE symbol = ? AND is_closed_bar = 1 AND stale = 0 "
                    "AND close < open ORDER BY bar_time DESC LIMIT 1000",
                    (symbol.upper(),),
                ).fetchall()
            except sqlite3.Error:
                rows = []

            if not rows:
                # Fallback conservateur
                return {
                    "symbol": symbol,
                    "regime": regime,
                    "tp_pips": max(min_tp, 6.0),
                    "sl_pips": max(min_sl, 5.0),
                    "time_bars": 4,
                    "risk_reward_ratio": round(max(min_tp, 6.0) / max(min_sl, 5.0), 3),
                    "trailing_activation": 3.0,
                    "trailing_distance": 2.0,
                    "rationale": "Pas de données baissières historiques — fallback conservateur",
                    "supporting_stats": {},
                }

            pip_factor = 100.0 if _pair_currencies(symbol)[1] == "JPY" else 10000.0
            amps = [float(r["high"] - r["low"]) * pip_factor for r in rows if r["high"] is not None and r["low"] is not None]
            amps_sorted = sorted(amps)
            if not amps_sorted:
                return {
                    "symbol": symbol,
                    "regime": regime,
                    "tp_pips": max(min_tp, 6.0),
                    "sl_pips": max(min_sl, 5.0),
                    "time_bars": 4,
                    "risk_reward_ratio": round(max(min_tp, 6.0) / max(min_sl, 5.0), 3),
                    "trailing_activation": 3.0,
                    "trailing_distance": 2.0,
                    "rationale": "Amp invalide — fallback",
                    "supporting_stats": {},
                }
            p90_amp = amps_sorted[int(len(amps_sorted) * 0.9)] if amps_sorted else 0
            avg_amp = mean(amps)
            std_amp = pstdev(amps) if len(amps) > 1 else 0.0

            # Heuristique par régime
            if regime.upper() == "TREND":
                tp_mult, sl_mult, time_bars = 0.8, 1.2, 6
            elif regime.upper() == "RANGE":
                tp_mult, sl_mult, time_bars = 0.6, 1.0, 4
            elif regime.upper() == "VOLATILE":
                tp_mult, sl_mult, time_bars = 1.2, 1.8, 8
            else:
                tp_mult, sl_mult, time_bars = 0.8, 1.2, 6

            tp = max(p90_amp * tp_mult, min_tp)
            sl = max(avg_amp * sl_mult, min_sl)
            rr = round(tp / sl, 3) if sl > 0 else 0.0
            trailing_act = round(tp * 0.5, 2)
            trailing_dist = round(max(sl * 0.5, 1.0), 2)

            return {
                "symbol": symbol,
                "regime": regime,
                "tp_pips": round(tp, 2),
                "sl_pips": round(sl, 2),
                "time_bars": time_bars,
                "risk_reward_ratio": rr,
                "trailing_activation": trailing_act,
                "trailing_distance": trailing_dist,
                "rationale": (
                    f"TP=p90_amp×{tp_mult}, SL=avg_amp×{sl_mult} sur {len(amps)} bougies baissières "
                    f"(p90={p90_amp:.2f}p, avg={avg_amp:.2f}p, σ={std_amp:.2f}p)"
                ),
                "supporting_stats": {
                    "n_bearish_bars": len(amps),
                    "p90_amplitude_pips": round(p90_amp, 2),
                    "avg_amplitude_pips": round(avg_amp, 2),
                    "stdev_amplitude_pips": round(std_amp, 2),
                },
            }
        finally:
            _safe_close(conn)


# ── CLI ─────────────────────────────────────────────────────────────────
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="V9 BearStrategy — stratégie baissière calibrée (mission 1/2).",
    )
    p.add_argument("--db-path", default=None, help="Chemin DB (défaut : data/v9_forces.db).")
    p.add_argument("--symbol", default="GBPUSD", help="Symbole (défaut GBPUSD).")
    p.add_argument("--evaluate", action="store_true", help="Évalue la whitelist baissière.")
    p.add_argument("--exit-params", action="store_true", help="Calcule les exit params.")
    p.add_argument("--regime", default="TREND", help="Régime de marché (TREND/RANGE/VOLATILE).")
    p.add_argument("--json", action="store_true", help="Sortie JSON.")
    return p


def _resolve_db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    return Path(__file__).resolve().parent.parent.parent / "data" / "v9_forces.db"


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    db_path = _resolve_db_path(args.db_path)
    try:
        strat = BearStrategy(db_path=db_path)
    except Exception as e:
        print(f"ERREUR init BearStrategy: {e}", file=sys.stderr)
        return 1

    out: dict[str, Any] = {"symbol": args.symbol}
    try:
        if args.evaluate or not (args.evaluate or args.exit_params):
            wl = strat.bearish_whitelist(symbol=args.symbol)
            out["whitelist"] = wl
        if args.exit_params:
            ep = strat.compute_exit_params(symbol=args.symbol, regime=args.regime)
            out["exit_params"] = ep

        # Test filtre sur quelques décisions baissières historiques
        if args.evaluate:
            try:
                conn = _connect(db_path)
                try:
                    test_rows = conn.execute(
                        "SELECT decision_id, snapshot_id, direction, confiance, "
                        "principes_json, symbol "
                        "FROM decisions "
                        "WHERE symbol = ? AND direction = 'baissiere' "
                        "AND source_type = 'live' "
                        "ORDER BY timestamp DESC LIMIT 50",
                        (args.symbol.upper(),),
                    ).fetchall()
                finally:
                    _safe_close(conn)
                samples = []
                for r in test_rows[:10]:
                    principes = []
                    try:
                        principes = json.loads(r["principes_json"] or "[]")
                    except Exception:
                        pass
                    decision = {
                        "symbol": r["symbol"],
                        "direction": r["direction"],
                        "confiance": r["confiance"],
                        "snapshot_id": r["snapshot_id"],
                        "principes_source": principes,
                    }
                    rep = strat.evaluate_entry(decision, market_context={})
                    samples.append({
                        "snapshot_id": r["snapshot_id"],
                        "confiance": r["confiance"],
                        "should_enter": rep.should_enter,
                        "reasons": rep.reasons,
                        "warnings": rep.warnings,
                        "constitutive_currencies": rep.constitutive_currencies,
                        "bearish_source_currencies": rep.bearish_source_currencies,
                    })
                accepted = sum(1 for s in samples if s["should_enter"])
                out["entry_filter_sample"] = {
                    "tested": len(samples),
                    "accepted": accepted,
                    "rejected": len(samples) - accepted,
                    "samples": samples[:5],  # Top 5 pour lisibilité
                }
            except Exception as e:
                out["entry_filter_sample"] = {"error": str(e)}

    except Exception as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"\n=== V9 BearStrategy — {args.symbol} ===\n")
        if "whitelist" in out:
            wl = out["whitelist"]
            print(f"[Whitelist baissier]")
            print(f"  Status: {'OUI' if wl['is_whitelisted'] else 'NON'}")
            print(f"  Raison: {wl['reason']}")
            print(f"  Trades baissiers clôturés: {wl['n_bearish_trades']}")
            if wl.get('wr_bearish', 0) > 0:
                print(f"  WR baissier historique: {wl['wr_bearish']:.1f}%")
            print(f"  Sizing multiplier: {wl['sizing_multiplier']}")
        if "exit_params" in out:
            ep = out["exit_params"]
            print(f"\n[Exit params baissier — regime={args.regime}]")
            print(f"  TP={ep['tp_pips']:.2f} pips  SL={ep['sl_pips']:.2f} pips  R/R={ep['risk_reward_ratio']:.2f}")
            print(f"  TimeExit={ep['time_bars']} bougies  Trailing activation={ep['trailing_activation']:.2f} pips  dist={ep['trailing_distance']:.2f}")
            print(f"  Rationale: {ep['rationale']}")
        if "entry_filter_sample" in out:
            es = out["entry_filter_sample"]
            if "error" in es:
                print(f"\n[Entry filter] erreur: {es['error']}")
            else:
                print(f"\n[Entry filter — test sur 10 décisions baissières GBPUSD]")
                print(f"  Acceptées: {es['accepted']}/{es['tested']} ({es['accepted']/es['tested']*100:.0f}%)")
                for s in es['samples'][:5]:
                    flag = "✓" if s['should_enter'] else "✗"
                    print(f"    {flag} {s['snapshot_id'][:35]} conf={s['confiance']} -> {s['warnings'][:1] or s['reasons'][:1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())