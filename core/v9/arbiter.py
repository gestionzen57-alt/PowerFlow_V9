"""Arbiter — consolidation des décisions V9 pour paper-trade (Phase 9.7).

L'Arbiter consolide les décisions d'un même snapshot en une seule
synthèse directionnelle (direction majoritaire + confiance moyenne),
utilisée ensuite par RiskManager (filtre) puis PaperTradeLogger (saisie).

Aucune logique d'exécution d'ordre — la doctrine interdit tout ordre
réel avant Phase 12. Ce module ne fait QUE consolider des décisions déjà
journalisées.

Usage :
    arbiter = Arbiter()
    result = arbiter.consolidate(snapshot_id)
    # → dict direction / confiance_arbitree / principes_source /
    #   nb_principes_actifs / timestamp / arbiter_version
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.principle_scorer import MIN_SAMPLE_SCORE, _combination_hash
from core.v9.trader_mini_weigher import TRADER_MINI_MULT_NEUTRAL, TraderMiniWeigher

ARBITER_VERSION = "1.0"

# Instance module-level (lazy) — évite de recharger le modèle JSON (Brief Q1)
# à chaque consolidate(). Pas de mutation d'état décisionnel (le modèle est
# figé, chargé une fois, R18).
_TRADER_MINI_WEIGHER: TraderMiniWeigher | None = None


def _get_trader_mini_weigher() -> TraderMiniWeigher:
    global _TRADER_MINI_WEIGHER
    if _TRADER_MINI_WEIGHER is None:
        _TRADER_MINI_WEIGHER = TraderMiniWeigher()
    return _TRADER_MINI_WEIGHER

# Plafond confiance si < 2 principes actifs (force le filtre risk_manager).
CONFIANCE_PLAFOND_SOUS_2_PRINCIPES = 74

# ── Brief O2 (2026-07-12) — Pondération PrincipleScorer ────────────
# Kill switch env (défaut 1 = ON, 0 = neutre intégral). Même pattern que
# V9_AUTO_RESOLVE_ENABLED (core/v9/orchestrator.py).
SCORER_ENABLED_ENV = "V9_ARBITER_SCORER_ENABLED"
SCORER_WR_LOW = 60.0    # WR < 60% -> confiance x0.8
SCORER_WR_HIGH = 90.0   # WR > 90% -> confiance x1.1 (plafond absolu 100)
SCORER_MULT_LOW = 0.8
SCORER_MULT_HIGH = 1.1
SCORER_MULT_NEUTRAL = 1.0
# Bornes dures du multiplicateur final (convention PrincipleScorer).
SCORER_MULT_BOUNDS = (0.5, 1.5)


class ArbiterError(ValueError):
    """Erreur de l'Arbiter (snapshot introuvable, données invalides)."""


class Arbiter:
    """Consolide les décisions d'un snapshot_id en une synthèse unique."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_decisions(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT decision_id, direction, confiance, principes_json, timestamp "
            "FROM decisions "
            "WHERE snapshot_id = ? AND source_type = 'live' "
            "AND direction IS NOT NULL AND direction != 'neutre'",
            (snapshot_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _extract_principes(principes_json: str | None) -> list[str]:
        if not principes_json:
            return []
        try:
            data = json.loads(principes_json)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, list):
            return []
        return [p for p in data if isinstance(p, str)]

    # ── Helpers règle 29 — pondération zone-type × session ─────
    def _detect_zone_type_from_snapshot(
        self,
        snapshot_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> str | None:
        """Lit `zone_type` depuis `principle_evaluations.context_json`.

        Règle 29 (DOCTRINE §29). Lecture défensive : si une connexion
        est fournie (param ``conn``), l'utilise sans l'ouvrir/fermer ;
        sinon ouvre sa propre connexion (backward-compat). Retourne
        None si DB inaccessible / snapshot absent / context_json
        malformé. Ne lève JAMAIS d'exception : le caller tombe sur la
        pondération neutre, comportement backward-compatible.

        Cette fonction est idempotente : ré-appels = même résultat.
        """
        if conn is not None:
            # Connexion partagée — le caller gère le cycle de vie.
            try:
                row = conn.execute(
                    "SELECT context_json FROM principle_evaluations "
                    "WHERE snapshot_id = ? AND context_json LIKE '%zone_type%' "
                    "LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
            except Exception:
                return None
            if row is None or not row["context_json"]:
                return None
            try:
                data = json.loads(row["context_json"])
                if isinstance(data, dict):
                    zt = data.get("zone_type")
                    return str(zt) if zt else None
                return None
            except Exception:
                return None

        # Backward-compat : ouvre sa propre connexion.
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT context_json FROM principle_evaluations "
                    "WHERE snapshot_id = ? AND context_json LIKE '%zone_type%' "
                    "LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
            finally:
                conn.close()
            if row is None or not row["context_json"]:
                return None
            data = json.loads(row["context_json"])
            if isinstance(data, dict):
                zt = data.get("zone_type")
                return str(zt) if zt else None
            return None
        except Exception:
            return None

    @staticmethod
    def _scorer_enabled() -> bool:
        """Kill switch V9_ARBITER_SCORER_ENABLED (défaut '1' = ON)."""
        return os.environ.get(SCORER_ENABLED_ENV, "1") != "0"

    @staticmethod
    def _wr_to_multiplier(win_rate: float) -> float:
        """Règle de pondération discrète (Brief O2) — distincte de
        PrincipleScorer.get_weights() (formule continue, utilisée ailleurs).
        WR<60 -> x0.8, WR>90 -> x1.1, sinon neutre x1.0."""
        if win_rate < SCORER_WR_LOW:
            mult = SCORER_MULT_LOW
        elif win_rate > SCORER_WR_HIGH:
            mult = SCORER_MULT_HIGH
        else:
            mult = SCORER_MULT_NEUTRAL
        lo, hi = SCORER_MULT_BOUNDS
        return max(lo, min(hi, mult))

    def _compute_scorer_multiplier(
        self, principes: list[str], conn: sqlite3.Connection,
    ) -> tuple[float, str]:
        """Pondère la confiance par le score historique des principes source.

        Lecture seule, déterministe (R18). Score figé par évaluation : une
        seule lecture de `principle_scores` par appel, aucune mutation.
        Tolère table absente/vide -> neutre (jamais d'exception, règle 6).

        Ordre de résolution (Brief O2) :
        1. Lookup par combination_hash des principes (si n_trades >= seuil).
        2. Fallback : moyenne du win_rate des principes individuels ayant
           chacun n_trades >= seuil (jamais d'extrapolation sur petit
           échantillon).
        3. Sinon neutre (x1.0), basis='neutral'.

        Retourne (multiplicateur, basis) — basis in
        {'combination', 'individual', 'neutral', 'disabled'}.
        """
        if not self._scorer_enabled():
            return SCORER_MULT_NEUTRAL, "disabled"
        if not principes:
            return SCORER_MULT_NEUTRAL, "neutral"

        try:
            comb_hash = _combination_hash(principes)
            if comb_hash:
                row = conn.execute(
                    "SELECT win_rate, n_trades FROM principle_scores "
                    "WHERE combination_hash = ?",
                    (comb_hash,),
                ).fetchone()
                if row and row["n_trades"] >= MIN_SAMPLE_SCORE:
                    return self._wr_to_multiplier(row["win_rate"]), "combination"

            placeholders = ",".join("?" for _ in principes)
            individual_rows = conn.execute(
                "SELECT win_rate, n_trades FROM principle_scores "
                f"WHERE principle_id IN ({placeholders}) "
                "AND combination_hash IS NULL AND n_trades >= ?",
                (*principes, MIN_SAMPLE_SCORE),
            ).fetchall()
            if individual_rows:
                avg_wr = sum(r["win_rate"] for r in individual_rows) / len(individual_rows)
                return self._wr_to_multiplier(avg_wr), "individual"

            return SCORER_MULT_NEUTRAL, "neutral"
        except sqlite3.Error:
            # Table absente/corrompue -> neutre, ne jamais bloquer (règle 6).
            return SCORER_MULT_NEUTRAL, "neutral"

    @staticmethod
    def _compute_trader_mini_multiplier(
        snapshot_id: str, conn: sqlite3.Connection,
    ) -> tuple[float, str]:
        """Brief Q1 (2026-07-12) — pondération baseline V9-trader-mini.

        Même garde-fou que le scorer O2 : ne lève jamais, neutre par défaut
        (kill switch OFF, modèle absent, contexte indisponible). Voir
        core/v9/trader_mini_weigher.py pour le détail (bornes resserrées,
        signal faible mais réel sur la classe LOSS)."""
        try:
            weigher = _get_trader_mini_weigher()
            return weigher.compute_multiplier(snapshot_id, conn)
        except Exception:
            return TRADER_MINI_MULT_NEUTRAL, "neutral"

    @staticmethod
    def _infer_session_from_snapshot_ts(ts_iso: str | None) -> str | None:
        """Infère la session de marché depuis un timestamp ISO (UTC).

        Règle 29 (DOCTRINE §29 §3.2). Heuristique conservative UTC :
        - asie     : 00:00-07:00 UTC
        - london   : 07:00-12:00 UTC
        - overlap  : 12:00-16:00 UTC (London+NY chevauchement)
        - new_york : 16:00-22:00 UTC
        - None     : 22:00-00:00 UTC (transition weekend) ou timestamp
                     malformé (lecture défensive).

        Note : volontairement simple. La doctrine V8 nuance europe/
        americas vs pure UTC. Cette heuristique sert d'amorce — à
        recalibrer Phase 13 quand WIN/LOSS ≥ 50.
        """
        if not ts_iso:
            return None
        try:
            ts = ts_iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            h = dt.astimezone(timezone.utc).hour
        except Exception:
            return None
        if 0 <= h < 7:
            return "asie"
        if 7 <= h < 12:
            return "london"
        if 12 <= h < 16:
            return "overlap"
        if 16 <= h < 22:
            return "new_york"
        return None

    def consolidate(self, snapshot_id: str) -> dict:
        """Consolide les décisions d'un snapshot en une synthèse unique.

        Logique :
        - Lecture de toutes les décisions `live` directionnelles pour
          ce snapshot_id.
        - Si vide → direction='neutre', confiance=0.
        - Sinon → direction majoritaire, confiance=moyenne des confiances
          dans la direction majoritaire, principes_source=union des
          principes déclenchés dans cette direction.
        - Si nb_principes_actifs < 2 → confiance_arbitree plafonnée à 74.
        """
        conn = self._connect()
        try:
            rows = self._load_decisions(conn, snapshot_id)

            if not rows:
                # Règle 29 — DOCTRINE §29. Champs présents même en early return
                # pour stabilité de l'API (consommateurs peuvent lire .get()
                # sans KeyError). zone_type/session=None car pas de données.
                return {
                    "direction": "neutre",
                    "confiance_arbitree": 0,
                    "confiance_brute": 0,
                    "plafonne_sous_2_principes": False,
                    "ajustement_rule29": 0,
                    "raisons_ajustement": [],
                    "zone_type_predit": None,
                    "session_marche": None,
                    "principes_source": [],
                    "nb_principes_actifs": 0,
                    "scorer_multiplier": SCORER_MULT_NEUTRAL,
                    "scorer_basis": "neutral",
                    "trader_mini_multiplier": TRADER_MINI_MULT_NEUTRAL,
                    "trader_mini_basis": "neutral",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "arbiter_version": ARBITER_VERSION,
                    "snapshot_id": snapshot_id,
                    "nb_decisions_consolidees": 0,
                    "nb_decisions_totales": 0,
                }

            # Direction majoritaire (gestion ex-aequo : Counter.most_common).
            directions = [r["direction"] for r in rows]
            counter = Counter(directions)
            direction_majoritaire, _ = counter.most_common(1)[0]

            # Décisions dans la direction majoritaire uniquement.
            rows_dir = [r for r in rows if r["direction"] == direction_majoritaire]

            # Confiance moyenne (entière, arrondie).
            confiances = [int(r["confiance"]) for r in rows_dir if r["confiance"] is not None]
            confiance_moyenne = round(sum(confiances) / len(confiances)) if confiances else 0

            # Union des principes (set, ordre stable par 1ère apparition).
            seen: set[str] = set()
            principes_union: list[str] = []
            for r in rows_dir:
                for p in self._extract_principes(r["principes_json"]):
                    if p not in seen:
                        seen.add(p)
                        principes_union.append(p)

            nb_principes_actifs = len(principes_union)

            # Brief O2 (2026-07-12) — pondération PrincipleScorer. Insérée ICI
            # (APRÈS le vote directionnel, AVANT le plafond <2 principes et
            # les ajustements règle 29) conformément à la spec du brief.
            # Lecture figée : un seul appel par consolidate(), pas de mutation
            # mid-run. Boucle de rétroaction scorer->arbiter->décisions->scorer :
            # risque d'auto-renforcement documenté — les bornes [0.5;1.5] et le
            # seuil n>=5 (MIN_SAMPLE_SCORE) sont les garde-fous actés (pas
            # d'autres ajoutés sans HITL, cf DECISIONS_LOG §2026-07-12 Brief O2).
            scorer_multiplier, scorer_basis = self._compute_scorer_multiplier(
                principes_union, conn,
            )
            confiance_ponderee = confiance_moyenne
            if scorer_multiplier != SCORER_MULT_NEUTRAL:
                confiance_ponderee = round(
                    min(100, max(0, confiance_moyenne * scorer_multiplier))
                )

            # Brief Q1 (2026-07-12) — pondération V9-trader-mini, CHAÎNÉE
            # après le scorer O2 (même point d'insertion que le brief l'exige :
            # "après le vote directionnel", avant le plafond <2 principes).
            # Kill switch OFF par défaut (V9_TRADER_MINI_ENABLED=0) — neutre
            # tant que Søn ne l'active pas explicitement.
            trader_mini_multiplier, trader_mini_basis = self._compute_trader_mini_multiplier(
                snapshot_id, conn,
            )
            if trader_mini_multiplier != TRADER_MINI_MULT_NEUTRAL:
                confiance_ponderee = round(
                    min(100, max(0, confiance_ponderee * trader_mini_multiplier))
                )

            # Plafond confiance si < 2 principes actifs.
            confiance_finale = confiance_ponderee
            plafonne = False
            if nb_principes_actifs < 2:
                confiance_finale = min(confiance_finale, CONFIANCE_PLAFOND_SOUS_2_PRINCIPES)
                plafonne = confiance_finale != confiance_ponderee

            # Timestamp le plus récent parmi les décisions consolidées.
            timestamps = [r["timestamp"] for r in rows_dir if r["timestamp"]]
            ts_max = max(timestamps) if timestamps else datetime.now(timezone.utc).isoformat()

            # Règle 29 — DOCTRINE §29. Pondération zone-type × session (lecture
            # §3bis D2 + D5). Insérée ICI, APRÈS calcul de ts_max (corrige le
            # bug d'ordonnancement de la tentative précédente, voir DECISIONS_LOG
            # 2026-07-07 'Rule 29 (c) annulé'). Lecture défensive : sans
            # zone_type ou session, on ne touche pas la confiance (cohérence
            # backward-compatible). Bornes ±15 max pour ne pas écraser le
            # filtre risk_manager.
            #
            # Phase 13 — recalibrage CEO 2026-07-10 (9411 décisions résolues,
            # WR global 97.99%). Source : docs/reports/H24_ARBITER_RECAL_20260710.json
            # + DECISIONS_LOG §"Phase 13 arbiter recal".
            # - zone_type=neutre (4 sessions) : WR 95-98% sans boost → pénalité
            #   -6 (after) / -7 (asie/london) / -6 (ny) — REPASSE la condition
            #   `nb_principes_actifs >= 2` pour ne pas écraser les zones non-neutres.
            # - zone_type=naissance : +5 (inchangé, R29 original)
            # - zone_type=continuation : -2 (inchangé)
            # - session=asie/after : -3 (inchangé) — pénalité déjà sur la session.
            zone_type = self._detect_zone_type_from_snapshot(snapshot_id, conn=conn)
            session_marche = self._infer_session_from_snapshot_ts(ts_max)

            ajustement = 0
            raisons_ajustement: list[str] = []
            if zone_type == "naissance" and nb_principes_actifs >= 2:
                ajustement += 5
                raisons_ajustement.append("zone_type=naissance (boost +5)")
            elif zone_type == "continuation" and nb_principes_actifs >= 2:
                ajustement -= 2
                raisons_ajustement.append("zone_type=continuation (réduction -2)")
            elif zone_type == "neutre" and nb_principes_actifs >= 2:
                # Phase 13 recalibrage — pénalité plus forte sur zone neutre
                # car HR y est structurellement 95-98% (biais artefact).
                # -7 asie/london, -6 after/ny (cf recalibrate_arbiter.py §3).
                if session_marche in ("asie", "london"):
                    ajustement -= 7
                    raisons_ajustement.append(
                        f"zone_type=neutre session={session_marche} (réduction -7)"
                    )
                else:
                    ajustement -= 6
                    raisons_ajustement.append(
                        f"zone_type=neutre session={session_marche} (réduction -6)"
                    )
            if session_marche in ("asie", "after"):
                ajustement -= 3
                raisons_ajustement.append(f"session={session_marche} (réduction -3)")

            if ajustement:
                confiance_avant = confiance_finale
                confiance_finale = max(0, min(100, confiance_finale + ajustement))
                plafonne = plafonne or (confiance_finale != confiance_avant)

            return {
                "direction": direction_majoritaire,
                "confiance_arbitree": int(confiance_finale),
                "confiance_brute": int(confiance_moyenne),
                "plafonne_sous_2_principes": plafonne,
                "ajustement_rule29": int(ajustement),
                "raisons_ajustement": raisons_ajustement,
                "zone_type_predit": zone_type,
                "session_marche": session_marche,
                "principes_source": principes_union,
                "nb_principes_actifs": nb_principes_actifs,
                "scorer_multiplier": scorer_multiplier,
                "scorer_basis": scorer_basis,
                "trader_mini_multiplier": trader_mini_multiplier,
                "trader_mini_basis": trader_mini_basis,
                "timestamp": ts_max,
                "arbiter_version": ARBITER_VERSION,
                "snapshot_id": snapshot_id,
                "nb_decisions_consolidees": len(rows_dir),
                "nb_decisions_totales": len(rows),
            }
        finally:
            conn.close()