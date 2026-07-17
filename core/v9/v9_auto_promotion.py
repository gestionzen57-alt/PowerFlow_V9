"""v9_auto_promotion.py — Auto-promotion Engine R25''.

2026-07-17 motion CEO « orchestre et optimise au max, hedge fund mondial ».

Doctrine R25'' (assouplie 2026-07-14) :
    SHADOW = vocabulaire descriptif, promotion ACTIVE conditionnée à :
      - wr >= min_wr (défaut 0.70)
      - n_trades >= min_n_trades (défaut 100)
      - sharpe >= min_sharpe (défaut 1.0)

Ce module :
  1. Calcule les métriques par principe depuis paper_trades (jointure
     via json_each sur principes_source pour attribuer chaque trade à
     tous ses principes contributeurs).
  2. Évalue chaque principe vs les seuils R25''.
  3. Propose promote / demote / keep avec rationale.
  4. apply_promotions() met à jour principles.v9_status en DB (SHADOW <-> ACTIVE).

Doctrine R6 : try/except défensif.
Doctrine R18 : pas de LLM. SQL + stdlib uniquement.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

AUTO_PROMOTION_VERSION = "1.0"

# Status valides pour principles.v9_status
STATUS_SHADOW = "SHADOW"
STATUS_ACTIVE = "ACTIVE"


@dataclass
class PromotionDecision:
    """Décision de promotion pour un principe."""

    principle_id: str
    action: str  # "promote" | "demote" | "keep"
    current_status: str
    new_status: str
    metrics: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutoPromotionEngine:
    """Moteur d'auto-promotion R25'' (SHADOW <-> ACTIVE).

    Évalue les principes sur les paper_trades clôturés. Chaque trade est
    attribué à TOUS les principes présents dans principes_source (json).
    On cumule wr, n, sharpe, profit_factor par principle_id, puis on
    compare aux seuils R25'' pour décider.

    Important : on regarde UNIQUEMENT le v9_status courant du principe ;
    le source_status est conservé tel quel (audit historique).
    """

    def __init__(
        self,
        *,
        min_wr: float = 0.70,
        min_n_trades: int = 100,
        min_sharpe: float = 1.0,
        # Optionnels : seuils pour la démotion
        demote_wr: float = 0.55,
        demote_min_n_trades: int = 100,
        db_path: Path | str | None = None,
    ) -> None:
        if not 0.0 <= min_wr <= 1.0:
            raise ValueError(f"min_wr doit être dans [0,1], reçu {min_wr}")
        if min_n_trades <= 0:
            raise ValueError(f"min_n_trades doit être > 0, reçu {min_n_trades}")
        self.min_wr = min_wr
        self.min_n_trades = min_n_trades
        self.min_sharpe = min_sharpe
        self.demote_wr = demote_wr
        self.demote_min_n_trades = demote_min_n_trades
        self.db_path = Path(db_path) if db_path else None

    # ── Agrégation des métriques par principe ───────────────────────

    def _compute_principle_metrics(self) -> dict[str, dict[str, float]]:
        """Agrège wr, n, sharpe_like, profit_factor par principle_id.

        Jointure json_each(principes_source) -> paper_trades. Tous les
        principes contributeurs d'un trade reçoivent le trade en crédit.
        """
        conn = get_connection(self.db_path)
        out: dict[str, dict[str, float]] = {}
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    je.value AS principle_id,
                    pt.pips_simulated,
                    pt.is_win
                FROM paper_trades pt,
                     json_each(pt.principes_source) AS je
                WHERE pt.closed_at IS NOT NULL
                  AND pt.pips_simulated IS NOT NULL
                """
            ).fetchall()
        except sqlite3.Error as exc:
            log.error("[auto_promotion] SQL _compute_principle_metrics: %s", exc)
            try:
                conn.close()
            except Exception:
                pass
            return out

        try:
            # Buckets bruts
            buckets: dict[str, list[tuple[float, int]]] = {}
            for r in rows:
                pid = r["principle_id"]
                if pid is None:
                    continue
                buckets.setdefault(str(pid), []).append(
                    (float(r["pips_simulated"]), int(r["is_win"] or 0))
                )

            for pid, trades in buckets.items():
                n = len(trades)
                pips = [t[0] for t in trades]
                wins = sum(t[1] for t in trades)
                wr = wins / n if n else 0.0
                win_pips = [p for p in pips if p > 0]
                loss_pips = [abs(p) for p in pips if p < 0]
                pf = (
                    sum(win_pips) / sum(loss_pips)
                    if sum(loss_pips) > 0
                    else float(sum(win_pips)) if sum(win_pips) > 0 else 0.0
                )
                if n > 1:
                    mu = statistics.fmean(pips)
                    sigma = statistics.pstdev(pips)
                    sharpe = (mu / sigma) * math.sqrt(n) if sigma > 0 else 0.0
                else:
                    sharpe = 0.0

                out[pid] = {
                    "n_trades": float(n),
                    "wr": round(wr, 4),
                    "pf": round(pf, 3),
                    "sharpe": round(sharpe, 3),
                    "avg_pips": round(statistics.fmean(pips) if pips else 0.0, 3),
                    "total_pips": round(sum(pips), 2),
                }
        except Exception as exc:  # R6
            log.error("[auto_promotion] agrégation: %s", exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    def _load_principle_statuses(self) -> dict[str, str]:
        """Charge {principle_id: v9_status} depuis principles."""
        conn = get_connection(self.db_path)
        out: dict[str, str] = {}
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT principle_id, v9_status FROM principles"
            ).fetchall()
            for r in rows:
                out[str(r["principle_id"])] = str(r["v9_status"] or STATUS_SHADOW)
        except sqlite3.Error as exc:
            log.error("[auto_promotion] SQL _load_principle_statuses: %s", exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    # ── Évaluation R25'' ────────────────────────────────────────────

    def _evaluate_one(
        self,
        principle_id: str,
        current_status: str,
        m: dict[str, float],
    ) -> PromotionDecision:
        """Applique la doctrine R25'' à un principe."""
        n = m.get("n_trades", 0.0)
        wr = m.get("wr", 0.0)
        sharpe = m.get("sharpe", 0.0)
        pf = m.get("pf", 0.0)

        # Promotion : SHADOW -> ACTIVE
        if current_status == STATUS_SHADOW:
            if n >= self.min_n_trades and wr >= self.min_wr and sharpe >= self.min_sharpe:
                return PromotionDecision(
                    principle_id=principle_id,
                    action="promote",
                    current_status=current_status,
                    new_status=STATUS_ACTIVE,
                    metrics=m,
                    rationale=(
                        f"R25'': SHADOW->ACTIVE — n={int(n)} >= {self.min_n_trades}, "
                        f"wr={wr:.2%} >= {self.min_wr:.0%}, "
                        f"sharpe={sharpe:.2f} >= {self.min_sharpe:.2f}"
                    ),
                )
            # Pas assez de data ou sous les seuils
            missing = []
            if n < self.min_n_trades:
                missing.append(f"n={int(n)}<{self.min_n_trades}")
            if wr < self.min_wr:
                missing.append(f"wr={wr:.2%}<{self.min_wr:.0%}")
            if sharpe < self.min_sharpe:
                missing.append(f"sharpe={sharpe:.2f}<{self.min_sharpe:.2f}")
            return PromotionDecision(
                principle_id=principle_id,
                action="keep",
                current_status=current_status,
                new_status=current_status,
                metrics=m,
                rationale=(
                    f"R25'': maintien SHADOW — critères non remplis: {', '.join(missing)}"
                ),
            )

        # Démotion : ACTIVE -> SHADOW si dégradation
        if current_status == STATUS_ACTIVE:
            if n >= self.demote_min_n_trades and wr < self.demote_wr:
                return PromotionDecision(
                    principle_id=principle_id,
                    action="demote",
                    current_status=current_status,
                    new_status=STATUS_SHADOW,
                    metrics=m,
                    rationale=(
                        f"R25'': ACTIVE->SHADOW (démotion) — n={int(n)} >= "
                        f"{self.demote_min_n_trades}, wr={wr:.2%} < {self.demote_wr:.0%}"
                    ),
                )
            return PromotionDecision(
                principle_id=principle_id,
                action="keep",
                current_status=current_status,
                new_status=current_status,
                metrics=m,
                rationale=(
                    f"R25'': maintien ACTIVE — wr={wr:.2%}, sharpe={sharpe:.2f}, pf={pf:.2f}"
                ),
            )

        # Statut inconnu -> keep
        return PromotionDecision(
            principle_id=principle_id,
            action="keep",
            current_status=current_status,
            new_status=current_status,
            metrics=m,
            rationale=f"R25'': statut '{current_status}' non géré, maintien.",
        )

    # ── API publique ────────────────────────────────────────────────

    def evaluate_principles(self) -> list[PromotionDecision]:
        """Évalue tous les principes et retourne les décisions R25''.

        On évalue uniquement les principes qui ont au moins 1 trade
        contribué (présents dans le join json_each). Les principes sans
        trade ne sont pas retournés (rien à évaluer).
        """
        metrics = self._compute_principle_metrics()
        statuses = self._load_principle_statuses()

        decisions: list[PromotionDecision] = []
        for pid, m in metrics.items():
            current = statuses.get(pid, STATUS_SHADOW)
            try:
                decisions.append(self._evaluate_one(pid, current, m))
            except Exception as exc:  # R6
                log.error(
                    "[auto_promotion] _evaluate_one(%s) a échoué: %s", pid, exc
                )
                continue

        # Tri : promotions d'abord, puis démotions, puis keep
        order = {"promote": 0, "demote": 1, "keep": 2}
        decisions.sort(key=lambda d: (order.get(d.action, 9), d.principle_id))
        return decisions

    def apply_promotions(self, decisions: list[PromotionDecision]) -> int:
        """Applique les décisions promote/demote à principles.v9_status.

        Retourne le nombre de principes effectivement modifiés.
        """
        if not decisions:
            return 0
        conn = get_connection(self.db_path)
        applied = 0
        try:
            for d in decisions:
                if d.action not in ("promote", "demote"):
                    continue
                if d.current_status == d.new_status:
                    continue
                try:
                    cur = conn.execute(
                        "UPDATE principles SET v9_status = ?, synced_at = ? "
                        "WHERE principle_id = ?",
                        (
                            d.new_status,
                            datetime.now(timezone.utc).isoformat(),
                            d.principle_id,
                        ),
                    )
                    if cur.rowcount > 0:
                        applied += 1
                        log.info(
                            "[auto_promotion] %s: %s -> %s",
                            d.principle_id,
                            d.current_status,
                            d.new_status,
                        )
                except sqlite3.Error as exc:
                    log.error(
                        "[auto_promotion] UPDATE %s: %s", d.principle_id, exc
                    )
                    continue
            conn.commit()
        except Exception as exc:  # R6
            log.error("[auto_promotion] apply_promotions transaction: %s", exc)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return applied


# ── CLI entry point ────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-promotion R25''")
    parser.add_argument("--evaluate", action="store_true", help="Évalue et affiche les décisions")
    parser.add_argument("--apply", action="store_true", help="Applique les promotions (écrit en DB)")
    parser.add_argument("--min-wr", type=float, default=0.70, help="WR minimum pour promotion")
    parser.add_argument("--min-n", type=int, default=100, help="Nombre de trades minimum")
    parser.add_argument("--min-sharpe", type=float, default=1.0, help="Sharpe minimum")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Affiche uniquement un résumé (counts par action)",
    )
    args = parser.parse_args()

    engine = AutoPromotionEngine(
        min_wr=args.min_wr,
        min_n_trades=args.min_n,
        min_sharpe=args.min_sharpe,
    )

    try:
        decisions = engine.evaluate_principles()
    except Exception as exc:  # R6
        log.error("[auto_promotion] evaluate_principles: %s", exc)
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    if args.summary:
        counts: dict[str, int] = {}
        for d in decisions:
            counts[d.action] = counts.get(d.action, 0) + 1
        print(json.dumps({"version": AUTO_PROMOTION_VERSION, "counts": counts, "n_total": len(decisions)}, indent=2))
        return 0

    print(json.dumps(
        {
            "version": AUTO_PROMOTION_VERSION,
            "thresholds": {
                "min_wr": args.min_wr,
                "min_n_trades": args.min_n,
                "min_sharpe": args.min_sharpe,
            },
            "decisions": [d.to_dict() for d in decisions],
        },
        indent=2,
        ensure_ascii=False,
    ))

    if args.apply:
        applied = engine.apply_promotions(decisions)
        print(f"\n[apply] {applied} promotion(s) appliquée(s) en DB.")
        return 0

    if not args.evaluate:
        # Mode par défaut = --evaluate (déjà fait)
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())