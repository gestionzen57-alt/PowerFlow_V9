"""PrincipleCascadeEngine — Découverte des combinaisons gagnantes V9 (SOUL.md §5).

Couche 4 du moteur de recherche alpha : certains principes, seuls, ont un edge
modeste ; ensemble (co-déclenchés sur le même snapshot), ils forment une
cascade dont le WR dépasse celui du meilleur principe isolé. Ce module découvre
ces synergies (boosters) et les anti-synergies (dampeners), les enregistre, et
fournit un boost de confiance à appliquer en live.

  cascade  = ensemble de principes co-triggered sur un même snapshot
  wr_lift  = WR[cascade] - WR[meilleur principe seul]
  booster  = wr_lift > +seuil   (la combinaison amplifie l'edge)
  dampener = wr_lift < -seuil   (la combinaison le détruit)

Doctrine :
  - R18 : stdlib uniquement, aucun LLM, aucune dépendance externe
  - R2 : couche additive (le boost s'ajoute, ne remplace rien)
  - R6 : try/except, ne crash jamais l'orchestrateur
  - R25' : les cascades sont découvertes puis validées (n_validation) avant emploi
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

CASCADE_ENGINE_VERSION = "1.0"

# Boost de confiance = wr_lift * facteur (cappé). SOUL.md §3.
CONFIDENCE_BOOST_FACTOR = 0.5
CONFIDENCE_CAP = 100.0

CASCADE_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS principle_cascade_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cascade_id TEXT NOT NULL,
    principles_json TEXT NOT NULL,
    n_trades INTEGER,
    win_rate REAL,
    expectancy REAL,
    avg_pips REAL,
    wr_lift REAL,
    expectancy_lift REAL,
    status TEXT DEFAULT 'discovered',
    discovered_at TEXT NOT NULL,
    validated_at TEXT,
    n_validation INTEGER DEFAULT 0,
    UNIQUE(cascade_id)
);
CREATE INDEX IF NOT EXISTS idx_cascade_status
    ON principle_cascade_registry (status);
"""


def init_cascade_db(db_path: Path | None = None) -> None:
    """Crée la table principle_cascade_registry si absente (idempotent)."""
    conn = get_connection(db_path)
    try:
        conn.executescript(CASCADE_REGISTRY_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def make_cascade_id(principles: list[str]) -> str:
    """ID canonique d'une cascade (indépendant de l'ordre)."""
    return "+".join(sorted(principles))


class PrincipleCascadeEngine:
    """Moteur de découverte et d'application des cascades de principes.

    Usage :
        eng = PrincipleCascadeEngine()
        cascades = eng.discover_cascades(min_n=20, min_wr_lift=5.0)
        active = eng.get_active_cascades()
        boosted = eng.apply_cascade_confidence_boost(arbiter_result, active)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_cascade_db(self.db_path)

    # ── Chargement des co-déclenchements ──

    def _load_snapshot_principles(self) -> dict[str, dict[str, Any]]:
        """Snapshots résolus → {principes triggered, is_win, pips}.

        Ne garde que les snapshots dont la décision a un outcome et où au moins
        un principe a triggered.
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        snapshots: dict[str, dict[str, Any]] = {}
        try:
            rows = conn.execute(
                """
                SELECT pe.snapshot_id AS sid, pe.principle_id AS pid,
                       d.is_win AS is_win, d.resolution_pips AS pips
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.triggered = 1
                  AND d.is_win IS NOT NULL
                """,
            ).fetchall()
        except Exception as exc:
            log.debug("cascade: load failed: %s", exc)
            rows = []
        finally:
            conn.close()

        for r in rows:
            sid = r["sid"]
            entry = snapshots.setdefault(
                sid, {"principles": set(), "is_win": r["is_win"],
                      "pips": r["pips"] if r["pips"] is not None else
                      (1.0 if r["is_win"] == 1 else -1.0)},
            )
            entry["principles"].add(r["pid"])
        return snapshots

    @staticmethod
    def _metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
        """WR/expectancy/avg_pips d'un ensemble de snapshots."""
        n = len(rows)
        if n == 0:
            return {"n": 0, "wr": 0.0, "expectancy": 0.0, "avg_pips": 0.0}
        wins = sum(1 for r in rows if r["is_win"] == 1)
        pips = [float(r["pips"]) for r in rows]
        avg = sum(pips) / n
        return {
            "n": n,
            "wr": round(wins / n * 100.0, 2),
            "expectancy": round(avg, 3),
            "avg_pips": round(avg, 3),
        }

    # ── Découverte ──

    def discover_cascades(
        self,
        min_n: int = 20,
        min_wr_lift: float = 5.0,
        max_combo: int = 2,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        """Découvre les cascades boosters et dampeners.

        Scanne toutes les paires (jusqu'à `max_combo`) de principes co-triggered.
        Pour chaque combinaison observée sur ≥ min_n snapshots, compare son WR
        au WR du meilleur principe seul. |wr_lift| ≥ min_wr_lift → cascade.

        Args:
            min_n: nb minimal de co-déclenchements pour retenir une cascade
            min_wr_lift: seuil de lift (points de WR) pour booster/dampener
            max_combo: taille max des combinaisons (2 = paires)
            persist: si True, enregistre les cascades dans le registre

        Returns:
            liste de cascades {cascade_id, principles, n_trades, win_rate,
            wr_lift, kind (booster/dampener), ...}, triées par |wr_lift| décr.
        """
        snapshots = self._load_snapshot_principles()

        # WR par principe seul (référence de lift).
        solo: dict[str, list[dict[str, Any]]] = {}
        for sid, e in snapshots.items():
            for pid in e["principles"]:
                solo.setdefault(pid, []).append(e)
        solo_wr = {pid: self._metrics(rows)["wr"] for pid, rows in solo.items()}

        # Regroupe par combinaison observée.
        combo_rows: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for sid, e in snapshots.items():
            principles = sorted(e["principles"])
            if len(principles) < 2:
                continue
            for size in range(2, min(max_combo, len(principles)) + 1):
                for combo in combinations(principles, size):
                    combo_rows.setdefault(combo, []).append(e)

        cascades: list[dict[str, Any]] = []
        for combo, rows in combo_rows.items():
            m = self._metrics(rows)
            if m["n"] < min_n:
                continue
            best_alone = max(solo_wr.get(p, 0.0) for p in combo)
            wr_lift = round(m["wr"] - best_alone, 2)
            if abs(wr_lift) < min_wr_lift:
                continue
            # expectancy lift vs meilleur principe seul (par expectancy)
            best_exp = max(
                self._metrics(solo.get(p, []))["expectancy"] for p in combo
            )
            cascade = {
                "cascade_id": make_cascade_id(list(combo)),
                "principles": list(combo),
                "n_trades": m["n"],
                "win_rate": m["wr"],
                "expectancy": m["expectancy"],
                "avg_pips": m["avg_pips"],
                "wr_lift": wr_lift,
                "expectancy_lift": round(m["expectancy"] - best_exp, 3),
                "best_alone_wr": best_alone,
                "kind": "booster" if wr_lift > 0 else "dampener",
            }
            cascades.append(cascade)

        cascades.sort(key=lambda c: abs(c["wr_lift"]), reverse=True)

        if persist:
            for c in cascades:
                self._register(c)

        return cascades

    def score_cascade(self, principles_list: list[str]) -> dict[str, Any]:
        """Score une combinaison précise de principes.

        Retourne WR, expectancy, n_trades, wr_lift, confidence_boost.
        """
        snapshots = self._load_snapshot_principles()
        target = set(principles_list)

        rows = [e for e in snapshots.values() if target.issubset(e["principles"])]
        m = self._metrics(rows)

        # Meilleur principe seul de la combinaison.
        solo_wr = 0.0
        for pid in principles_list:
            solo = [e for e in snapshots.values() if pid in e["principles"]]
            solo_wr = max(solo_wr, self._metrics(solo)["wr"])

        wr_lift = round(m["wr"] - solo_wr, 2)
        return {
            "cascade_id": make_cascade_id(principles_list),
            "principles": sorted(principles_list),
            "n_trades": m["n"],
            "win_rate": m["wr"],
            "expectancy": m["expectancy"],
            "avg_pips": m["avg_pips"],
            "best_alone_wr": solo_wr,
            "wr_lift": wr_lift,
            "confidence_boost": self._boost_from_lift(wr_lift),
        }

    @staticmethod
    def _boost_from_lift(wr_lift: float) -> float:
        """Boost de confiance dérivé du lift (positif uniquement, cappé)."""
        if wr_lift <= 0:
            return 0.0
        return round(min(wr_lift * CONFIDENCE_BOOST_FACTOR, 30.0), 2)

    # ── Registre ──

    def _register(self, cascade: dict[str, Any]) -> None:
        """Upsert une cascade dans le registre (R6 : ne crash pas)."""
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """
                INSERT INTO principle_cascade_registry (
                    cascade_id, principles_json, n_trades, win_rate, expectancy,
                    avg_pips, wr_lift, expectancy_lift, status, discovered_at,
                    n_validation
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cascade_id) DO UPDATE SET
                    n_trades=excluded.n_trades, win_rate=excluded.win_rate,
                    expectancy=excluded.expectancy, avg_pips=excluded.avg_pips,
                    wr_lift=excluded.wr_lift,
                    expectancy_lift=excluded.expectancy_lift,
                    n_validation=principle_cascade_registry.n_validation + 1,
                    validated_at=?
                """,
                (
                    cascade["cascade_id"],
                    json.dumps(cascade["principles"]),
                    cascade["n_trades"], cascade["win_rate"],
                    cascade["expectancy"], cascade["avg_pips"],
                    cascade["wr_lift"], cascade.get("expectancy_lift", 0.0),
                    cascade.get("kind", "discovered"), now, 0, now,
                ),
            )
            conn.commit()
        except Exception as exc:
            log.debug("cascade: register failed: %s", exc)
        finally:
            conn.close()

    def get_active_cascades(
        self, min_wr_lift: float = 5.0, min_validation: int = 0,
    ) -> list[dict[str, Any]]:
        """Cascades boosters validées et prêtes à booster la confiance."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT * FROM principle_cascade_registry
                WHERE status = 'booster'
                  AND wr_lift >= ?
                  AND n_validation >= ?
                ORDER BY wr_lift DESC
                """,
                (min_wr_lift, min_validation),
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({
                "cascade_id": r["cascade_id"],
                "principles": json.loads(r["principles_json"]),
                "n_trades": r["n_trades"],
                "win_rate": r["win_rate"],
                "wr_lift": r["wr_lift"],
                "confidence_boost": self._boost_from_lift(r["wr_lift"]),
            })
        return out

    def get_cascade_for_snapshot(
        self, snapshot_id: str, active_cascades: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Quelles cascades actives matchent les principes de ce snapshot ?"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT principle_id FROM principle_evaluations "
                "WHERE snapshot_id = ? AND triggered = 1",
                (snapshot_id,),
            ).fetchall()
            triggered = {r[0] for r in rows}
        except Exception:
            triggered = set()
        finally:
            conn.close()

        if active_cascades is None:
            active_cascades = self.get_active_cascades()

        return [
            c for c in active_cascades
            if set(c["principles"]).issubset(triggered)
        ]

    def apply_cascade_confidence_boost(
        self,
        arbiter_result: dict[str, Any],
        cascades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Applique le boost de confiance des cascades matchées (SOUL.md §3).

        confiance += wr_lift * 0.5, cappé à 100. Non destructif : retourne une
        copie enrichie (confiance_arbitree_boosted + cascade_boost + cascades).
        """
        result = dict(arbiter_result)
        base = float(
            arbiter_result.get("confiance_arbitree")
            or arbiter_result.get("confiance")
            or 0.0
        )

        if not cascades:
            result["cascade_boost"] = 0.0
            result["confiance_arbitree_boosted"] = base
            result["cascades_matched"] = []
            return result

        # Prend le lift le plus fort (ne cumule pas — évite l'inflation).
        best = max(cascades, key=lambda c: c.get("wr_lift", 0.0))
        boost = self._boost_from_lift(best.get("wr_lift", 0.0))
        boosted = min(base + boost, CONFIDENCE_CAP)

        result["cascade_boost"] = boost
        result["confiance_arbitree_boosted"] = round(boosted, 2)
        result["cascades_matched"] = [c["cascade_id"] for c in cascades]
        result["cascade_source"] = best["cascade_id"]
        return result
