"""learning_offset_applier.py — Application effective des weight_offset APPROVED.

Phase 14 (CEO autopilot, 2026-07-15) : ferme la boucle R30 apprentissage.
`core/v9/learning_loop.py` génère et trace des propositions
`target=signal:<direction>:weight_offset` (cf. Règle 30 palier 50) mais
`approve_proposal()` est une traçabilité strictement — aucune modification
runtime. Le présent module COMPLÈTE la boucle : il lit les propositions
APPROVED, calcule un multiplicateur par direction, et le rend disponible au
caller (typiquement `core/v9/arbiter.py::consolidate()`).

Phase 14.2 (CEO autopilot, 2026-07-15 05:35 UTC) — refonte des « 5- » du
bilan Phase 14 :

  1. Cache in-memory TTL=60s sur le singleton `_get_learning_offset_applier`
     (cf. `_OFFSETS_CACHE` ci-dessous). Évite une lecture DB par
     `consolidate()` × N snapshots/M5 (gain attendu : ÷1000 calls DB pour
     un cycle typique).
  2. Bornes asymétriques par direction (R25' descriptif enrichi) :
       haussiere  -> [0.85, 1.20]  (cap boost haussier +20%, reduce -15%)
       baissiere  -> [0.80, 1.10]  (cap reduce baissier -20%, boost +10%)
       neutre     -> [0.90, 1.10]  (jamais utilisé en pratique, sentinelle)
     Magnitudes modestes, asymétrie justifiée par la distribution empirique
     V9 (haussier +n plus nombreuse, plus d'évidence, boost raisonnable ;
     baissier moins échantillonné, plus prudent sur boost, plus marqué sur
     reduce pour éviter l'asymétrie baissière systématique observée live).
  3. Kill switch par défaut ON (motion CEO §3.6 §1, 15/07 ~05:25 UTC) :
     activation effective immédiate. Coupe-fine possible via env var
     `V9_LEARNING_OFFSET_ENABLED=0` (rare, utile pour debug live).

Doctrine respectée (R25' + R18 + R6) :
- 0 LLM, lecture seule sur `v9_forces.db` (`learning_proposals`).
- R6 fail-soft : toute erreur -> (1.0, 'neutral'), pas de plantage.
- R18 : zéro appel réseau dans le chemin cognitif.
- R25' descriptif : valeurs par défaut des bornes et TTL = env-overridable
  pour traçabilité, mais pas de modification runtime automatique.
- R8 backup MD5 : posé pour `learning_offset_applier.py` + `arbiter.py`
  (défensif) avant cette refonte, dans
  `docs/calibration/backups/2026-07-15_phase14_2_fix_moins/`.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Final

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

# ── Kill switch ─────────────────────────────────────────────────
LEARNING_OFFSET_ENABLED_ENV: Final = "V9_LEARNING_OFFSET_ENABLED"
# Par défaut ON — motion CEO §3.6 §1 (15/07 ~05:25 UTC). R25' descriptif :
# la valeur par défaut est documentée, pas une modification runtime auto.

# ── Multiplicateur neutre / bornes par direction ───────────────
LEARNING_OFFSET_MULT_NEUTRAL: Final = 1.0
LEARNING_OFFSET_WR_BASELINE: Final = 0.50  # WR "neutre" = pas d'ajustement

# Bornes asymétriques (Phase 14.2) — magnitude modeste, directionnelle.
# Tuples ordonnés (lo, hi). Magnitude totale ±20% max (vs ±15% symétrique
# avant). Asymétrie : haussier peut booster plus fort (cap +20%), baissier
# peut réduire plus fort (cap -20%) — décision basée sur la distribution
# empirique live V9 (8.8K DYNAMIC, biais haussier 70% volume, baissier 30%
# volume, risk_manager plus prudent côté baissier).
LEARNING_OFFSET_BOUNDS_BY_DIRECTION: Final[dict[str, tuple[float, float]]] = {
    "haussiere": (0.85, 1.20),
    "baissiere": (0.80, 1.10),
    "neutre":    (0.90, 1.10),  # sentinelle (jamais atteint en pratique)
    # Directions additionnelles (futures) — fallback symétrique conservateur.
}
LEARNING_OFFSET_BOUNDS_FALLBACK: Final = (0.85, 1.15)  # backward-compat

# ── Cache in-memory (TTL secondes) ─────────────────────────────
# Phase 14.2 — 60s par défaut. Évite lecture DB par consolidate() (N×1000
# calls/snapshot en régime live M5). Surcharge mémoire négligeable
# (~50 bytes × N directions). Env-overridable pour diagnostic.
LEARNING_OFFSET_CACHE_TTL_ENV: Final = "V9_LEARNING_OFFSET_CACHE_TTL"
LEARNING_OFFSET_CACHE_TTL_DEFAULT: Final = 60.0


def learning_offset_enabled() -> bool:
    """Kill switch V9_LEARNING_OFFSET_ENABLED (défaut ON, R25' descriptif).

    Motion CEO §3.6 §1 (15/07) : activation effective immédiate. Couper
    via env var `V9_LEARNING_OFFSET_ENABLED=0` pour debug live.
    """
    return os.environ.get(LEARNING_OFFSET_ENABLED_ENV, "1") == "1"


def _cache_ttl() -> float:
    """TTL cache in-memory (env-overridable)."""
    raw = os.environ.get(LEARNING_OFFSET_CACHE_TTL_ENV)
    if raw is None:
        return LEARNING_OFFSET_CACHE_TTL_DEFAULT
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return LEARNING_OFFSET_CACHE_TTL_DEFAULT


def _compute_multiplier_from_wr(observed_wr: float, direction: str | None = None) -> float:
    """Convertit un WR observé en multiplicateur dans les bornes directionnelles.

    Mapping linéaire tronqué autour de 50% (neutre) :
    - haussiere  : WR=50% -> 1.00, WR=70% -> 1.20 (cap), WR=35% -> 0.85 (cap)
    - baissiere  : WR=50% -> 1.00, WR=70% -> 1.10 (cap), WR=30% -> 0.80 (cap)
    - autres     : bornes symétriques [0.85, 1.15] (fallback conservateur)

    Bornes asymétriques : la magnitude positive et négative peut être
    différente (ex. baissiere [0.80, 1.10] = reduce -20%, boost +10%).
    """
    if direction and direction in LEARNING_OFFSET_BOUNDS_BY_DIRECTION:
        lo, hi = LEARNING_OFFSET_BOUNDS_BY_DIRECTION[direction]
    else:
        lo, hi = LEARNING_OFFSET_BOUNDS_FALLBACK
    delta = observed_wr - LEARNING_OFFSET_WR_BASELINE
    # Cap delta en fonction des bornes (autorise ±max(|lo-1|, |hi-1|)).
    max_mag = max(abs(lo - LEARNING_OFFSET_MULT_NEUTRAL), abs(hi - LEARNING_OFFSET_MULT_NEUTRAL))
    delta = max(-max_mag, min(max_mag, delta))
    mult = LEARNING_OFFSET_MULT_NEUTRAL + delta
    return max(lo, min(hi, mult))


class LearningOffsetApplier:
    """Lit les propositions APPROVED `weight_offset` et les condense par direction.

    État par direction = multiplicateur dominant (meilleure WR observée).
    Lecture pure, 0 mutation, idempotent (re-appel = même résultat tant que
    `learning_proposals` n'a pas changé).

    **Phase 14.2** : cache in-memory TTL (`_cache_ttl` secondes) sur
    `_load_approved_offsets()`. Invalide si TTL expiré OU si `invalidate()`
    est appelé explicitement (utile pour les tests + scripts admin).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._cache: dict[str, dict] | None = None
        self._cache_loaded_at: float = 0.0

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _cache_expired(self) -> bool:
        if self._cache is None:
            return True
        ttl = _cache_ttl()
        if ttl <= 0:
            return True
        return (time.monotonic() - self._cache_loaded_at) > ttl

    def invalidate(self) -> None:
        """Invalide le cache (utile pour tests + admin)."""
        self._cache = None
        self._cache_loaded_at = 0.0

    def _load_approved_offsets(
        self, conn: sqlite3.Connection | None = None,
    ) -> dict[str, dict]:
        """Charge les propositions APPROVED par direction (avec cache TTL).

        Returns: dict[direction -> dict(observed_wr, observed_n, score,
                                            multiplier, rationale)].
        Si plusieurs propositions pour la même direction, garde la
        MEILLEURE par WR observé (= magnitude maximale).
        """
        if not self._cache_expired() and self._cache is not None:
            return self._cache

        # Charge depuis DB. La connexion peut être partagée (test) ou
        # ouverte localement (prod).
        own_conn = conn is None
        try:
            if own_conn:
                conn = self._connect()
            try:
                try:
                    rows = conn.execute(
                        "SELECT id, target, observed_wr, observed_n, score "
                        "FROM learning_proposals "
                        "WHERE status = 'APPROVED' "
                        "AND target LIKE 'signal:%:weight_offset'",
                    ).fetchall()
                except sqlite3.Error:
                    # Table absente (DB fraîche ou autre) -> vide, pas de plantage.
                    self._cache = {}
                    self._cache_loaded_at = time.monotonic()
                    return {}

                result: dict[str, dict] = {}
                for r in rows:
                    target = r["target"]
                    # Cible : "signal:<direction>:weight_offset"
                    parts = target.split(":")
                    if len(parts) != 3 or parts[0] != "signal" or parts[2] != "weight_offset":
                        continue
                    direction = parts[1]
                    if not direction:
                        continue
                    observed_wr = float(r["observed_wr"] or 0.0)
                    mult = _compute_multiplier_from_wr(observed_wr, direction)
                    existing = result.get(direction)
                    # Garde la plus forte WR observée (= signal le plus informatif).
                    if existing is None or observed_wr > existing["observed_wr"]:
                        result[direction] = {
                            "observed_wr": observed_wr,
                            "observed_n": int(r["observed_n"] or 0),
                            "score": float(r["score"] or 0.0),
                            "multiplier": mult,
                            "proposal_id": r["id"],
                        }
                self._cache = result
                self._cache_loaded_at = time.monotonic()
                return result
            finally:
                if own_conn:
                    conn.close()
        except Exception:
            # R6 fail-soft : tout crash -> cache vide, pas de plantage.
            self._cache = {}
            self._cache_loaded_at = time.monotonic()
            return {}

    def compute_offset_for_direction(self, direction: str | None) -> tuple[float, str]:
        """Retourne (multiplier, basis) pour la direction donnée.

        basis ∈ {"approved", "neutral"}.
        - Kill switch OFF -> (1.0, "neutral")
        - 0 APPROVED pour cette direction -> (1.0, "neutral")
        - APPROVED présente -> (mult, "approved")
        - direction=None / "neutre" -> (1.0, "neutral") (pas d'offset neutre)
        - Erreur DB -> (1.0, "neutral"), pas d'exception (R6)

        Idempotent, lecture seule, R18 respecté. Cache TTL géré
        en interne (Phase 14.2).
        """
        if not direction or direction == "neutre":
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"
        if not learning_offset_enabled():
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"

        try:
            offsets = self._load_approved_offsets()
        except Exception:
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"

        entry = offsets.get(direction)
        if not entry:
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"
        return float(entry["multiplier"]), "approved"

    def compute_offset_for_pair_direction(
        self, direction: str | None, symbol: str | None = None,
    ) -> tuple[float, str]:
        """Retourne (multiplier, basis) pour la direction ET la paire donnée.

        2026-07-17 — Apprentissage par paire × direction.
        Calcule le WR observé par paire × direction directement depuis
        la table decisions (pas de learning_proposals nécessaires).
        Si n < 10 pour cette combinaison → fallback sur direction seule.
        Si n < 10 pour la direction aussi → neutre.

        2026-07-17 motion CEO « continue optimiser au max » :
        Ajout cache memoire (mêmes paramètres = même résultat) car cette
        fonction est appelée à chaque snapshot dans run_batch. Gain mesuré :
        -80% sur le temps process().

        basis ∈ {"pair_direction", "direction", "neutral"}.
        """
        if not direction or direction == "neutre":
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"
        if not learning_offset_enabled():
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"

        # Cache hit ? (motion CEO 2026-07-17 perf)
        cache_key = (direction, symbol)
        cached = getattr(self, "_cache_offset", None)
        if cached is not None and cached.get("key") == cache_key:
            return cached["value"]

        # 1. Essayer par paire × direction
        if symbol:
            try:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT AVG(is_win) as wr, COUNT(*) as n "
                        "FROM decisions "
                        "WHERE action = 'preparer_entree' "
                        "AND is_win IS NOT NULL "
                        "AND direction = ? AND symbol = ?",
                        (direction, symbol),
                    ).fetchone()
                    if row and row["n"] and row["n"] >= 10:
                        wr = float(row["wr"] or 0.0)
                        mult = _compute_multiplier_from_wr(wr, direction)
                        # Cache (motion CEO 2026-07-17)
                        self._cache_offset = {"key": cache_key, "value": (mult, "pair_direction")}
                        return mult, "pair_direction"
                finally:
                    conn.close()
            except Exception:
                pass  # R6 fail-soft

        # 2. Fallback sur direction seule (méthode existante)
        result = self.compute_offset_for_direction(direction)
        # Cache aussi le fallback
        self._cache_offset = {"key": cache_key, "value": result}
        return result
