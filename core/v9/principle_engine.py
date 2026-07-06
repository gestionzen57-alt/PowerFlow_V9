"""PrincipleEngine — couche Décision (Phase 9) PowerFlow V9.

Chaîne cognitive étendue :
    Forces → Scènes → Comportements → Fenêtres → Exploitabilité →
    [PRINCIPES] → Signal → Décision

Évalue les 27 principes migrés tels quels depuis V8
(core/v9/principles/*.yaml, docs/audit_v8_v9_migration.md §4.3) contre le
contexte d'un snapshot : scène + comportement + fenêtre + exploitabilité
(couches V9 existantes) et regime_snapshots + zone_diagnostics (gaps V8
comblés en Phase 9 — voir core/v9/regime_detector.py et
core/v9/zone_db.py). Cette couche ne recalcule jamais une valeur des
couches amont, elle ne fait qu'évaluer des conditions déclaratives
dessus (charte cognitive V9).

GAP DOCUMENTÉ — 9 des 27 principes (`kind: node_rule`, ceux qui portent
une logique conditionnelle réelle : ANTAGONIST_NODE, COALITION_NODE,
ELASTIC_BREATH, GRAVITY_RESPRING_NODE, NODE_BIRTH_FAST,
POWER_ANGLE_BREAK_TO_PRICE_IMPACT, PRICE_LAG_AT_NODE_BIRTH,
RAW_NODE_BIRTH, ZONE_RETEST) référencent des champs qui, en V8, vivaient
dans `zone_diagnostics` (state, z_extreme_dir, bars_in_extreme,
tension_score, ...) ou dans des tables sans équivalent V9
(`coalition_strength` — coalition_log V8 ; `h1_dir`/`h1_state`/`m5_dir`/
`m5_state` — cross-timeframe, absent de zone_diagnostics elle-même dans
le schéma réel lu en V8). `zone_diagnostics` est créée (core/v9/zone_db.py)
mais volontairement non alimentée cette phase (chantier Priorité 2,
~5-8 jours, cf. audit §7/§8) : ces champs restent `None` dans le contexte
tant qu'aucun détecteur ne peuple la table, et leurs conditions
n'évaluent alors jamais à True — dégradation gracieuse, jamais d'erreur.
Les 20 principes `kind: grammar` sont des entrées de vocabulaire
documentaires (conditions vides, non émettrices en V8 déjà) : ils sont
catalogués et journalisés mais ne déclenchent jamais de signal.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.v9.config import (
    DB_PATH,
    DEVISES,
    PRINCIPLE_ACTIVE_IDS,
    PRINCIPLE_CONFIDENCE_DEFAULT,
    PRINCIPLE_TIMEFRAME_MINUTES_TO_V9,
    PRINCIPLES_DIR,
    SCHEMA_VERSION,
)
from core.v9.db_schema import get_connection
from core.v9.principle_db import (
    PRINCIPLE_EVALUATIONS_COLUMNS,
    PRINCIPLES_COLUMNS,
    init_principle_db,
)

STATUS_ACTIVE = "ACTIVE"
STATUS_SHADOW = "SHADOW"

_KNOWN_OPS = {"==", "!=", ">=", "<=", "in", "not_in", "is_not_null"}


class PrincipleEngineError(ValueError):
    """Erreur de chargement/évaluation d'un principe (YAML invalide, opérateur inconnu)."""


@dataclass
class PrincipleRecord:
    """Reflet plat d'une grammaire de principe (core/v9/principles/*.yaml)."""

    principle_id: str
    version: int
    origin: str
    kind: str
    source_status: str
    scope_timeframes: Any
    scope_currencies: Any
    conditions: list[dict] = field(default_factory=list)
    emits: dict = field(default_factory=dict)
    bounds: dict = field(default_factory=dict)
    anti_signal_bias: bool = False
    notes: str = ""
    created_by: str = ""
    created_at_source: str = ""

    @classmethod
    def from_yaml_dict(cls, raw: dict) -> "PrincipleRecord":
        if not raw.get("id"):
            raise PrincipleEngineError("principe YAML sans champ 'id'")
        scope = raw.get("scope") or {}
        return cls(
            principle_id=raw["id"],
            version=int(raw.get("version", 1)),
            origin=raw.get("origin", ""),
            kind=raw.get("kind", "grammar"),
            source_status=str(raw.get("status", "")),
            scope_timeframes=scope.get("timeframes", "ALL"),
            scope_currencies=scope.get("currencies", "ALL"),
            conditions=list(raw.get("conditions") or []),
            emits=dict(raw.get("emits") or {}),
            bounds=dict(raw.get("bounds") or {}),
            anti_signal_bias=bool(raw.get("anti_signal_bias", False)),
            notes=str(raw.get("notes", "")),
            created_by=str(raw.get("created_by", "")),
            created_at_source=str(raw.get("created_at", "")),
        )

    @property
    def v9_status(self) -> str:
        return STATUS_ACTIVE if self.principle_id in PRINCIPLE_ACTIVE_IDS else STATUS_SHADOW

    def matches_scope(self, symbol: str, timeframe: str, currency: str) -> bool:
        if self.scope_timeframes != "ALL":
            allowed_tfs = {
                PRINCIPLE_TIMEFRAME_MINUTES_TO_V9.get(m, str(m))
                for m in self.scope_timeframes
            }
            if timeframe not in allowed_tfs:
                return False
        if self.scope_currencies != "ALL":
            allowed_currencies = {str(c).upper() for c in self.scope_currencies}
            if currency.upper() not in allowed_currencies:
                return False
        return True


# Cache process-local : les grammaires *.yaml sont statiques pendant
# l'exécution (orchestrator.py instancie un PrincipleEngine par snapshot,
# cf. convention des autres couches V9) — relire et re-parser 27 fichiers
# YAML à chaque snapshot coûtait ~30ms, dépassant la cible de latence
# <200ms/snapshot mesurée sur les 1194 snapshots (Phase 9). Invalidé
# uniquement en changeant explicitement `principles_dir`.
_YAML_CACHE: dict[Path, list[PrincipleRecord]] = {}
_SYNCED_DB_PATHS: set[Path] = set()


def load_principles_from_yaml(principles_dir: Path | None = None) -> list[PrincipleRecord]:
    """Charge les grammaires *.yaml (portées telles quelles depuis V8, non réécrites)."""
    directory = principles_dir or PRINCIPLES_DIR
    cached = _YAML_CACHE.get(directory)
    if cached is not None:
        return cached
    records = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        records.append(PrincipleRecord.from_yaml_dict(raw))
    _YAML_CACHE[directory] = records
    return records


def _resolve_condition_value(cond: dict, context: dict[str, Any]) -> Any:
    value = context.get(cond["field"])
    if value is not None and cond.get("transform") == "abs":
        value = abs(value)
    return value


def _resolve_condition_target(cond: dict, context: dict[str, Any]) -> Any:
    if "value_field" in cond:
        return context.get(cond["value_field"])
    return cond.get("value")


def evaluate_condition(cond: dict, context: dict[str, Any]) -> bool:
    """Évalue une clause de condition (field/op/value|value_field) contre `context`.

    Une donnée de contexte absente (`None`) ne remplit jamais une
    condition, quel que soit l'opérateur — dégradation gracieuse plutôt
    qu'exception, cohérent avec le gap zone_diagnostics documenté en
    tête de module.
    """
    op = cond.get("op")
    if op not in _KNOWN_OPS:
        raise PrincipleEngineError(f"operateur de condition inconnu: {op!r}")

    value = _resolve_condition_value(cond, context)
    if op == "is_not_null":
        return value is not None
    if value is None:
        return False

    target = _resolve_condition_target(cond, context)
    if op == "==":
        return value == target
    if op == "!=":
        return value != target
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    if op == "in":
        return value in (target or [])
    if op == "not_in":
        return value not in (target or [])
    raise PrincipleEngineError(f"operateur de condition inconnu: {op!r}")  # pragma: no cover


def _resolve_direction(emits: dict, context: dict[str, Any]) -> str | None:
    directive = emits.get("direction")
    if not directive:
        return None
    if directive == "mean_reversion_from_z":
        z_current = context.get("z_current")
        if z_current is None:
            return None
        return "baissiere" if z_current > 0 else "haussiere"
    if directive.startswith("from_"):
        source_field = directive[len("from_"):]
        raw = context.get(source_field)
        if raw is None:
            return None
        return _normalize_direction(raw)
    return None


def _normalize_direction(raw: Any) -> str | None:
    """Traduit un vocabulaire de direction V8 (UP/DOWN/haussiere/baissiere/...)
    vers le vocabulaire V9 (haussiere/baissiere/neutre, cf. forces_reader.py)."""
    text = str(raw).strip().lower()
    if text in ("up", "haussiere", "long", "bullish"):
        return "haussiere"
    if text in ("down", "baissiere", "short", "bearish"):
        return "baissiere"
    if text in ("neutre", "neutral", "none", ""):
        return "neutre"
    return None


def _compute_confidence(principle: PrincipleRecord, context: dict[str, Any]) -> int:
    positions = []
    for field_name, bound in principle.bounds.items():
        value = context.get(field_name)
        if value is None:
            continue
        lo, hi = bound.get("min"), bound.get("max")
        if lo is None or hi is None or hi == lo:
            continue
        position = (abs(value) - lo) / (hi - lo)
        positions.append(max(0.0, min(1.0, position)))
    if not positions:
        return PRINCIPLE_CONFIDENCE_DEFAULT
    return round(50 + 50 * (sum(positions) / len(positions)))


def evaluate_principle(
    principle: PrincipleRecord, context: dict[str, Any]
) -> dict[str, Any]:
    """Évalue un principe contre un contexte déjà filtré sur le scope (une
    devise donnée). Ne vérifie pas le scope lui-même (voir `matches_scope`)."""
    if not principle.conditions:
        return {
            "triggered": False,
            "direction": None,
            "confidence": None,
            "reason": "entree_documentaire_non_emettrice",
        }

    for cond in principle.conditions:
        if not evaluate_condition(cond, context):
            return {
                "triggered": False,
                "direction": None,
                "confidence": None,
                "reason": f"condition_non_remplie:{cond['field']}",
            }

    direction = _resolve_direction(principle.emits, context)
    confidence = _compute_confidence(principle, context)
    return {
        "triggered": True,
        "direction": direction,
        "confidence": confidence,
        "reason": "conditions_remplies",
    }


class PrincipleEngine:
    """Charge le catalogue de principes et évalue chaque snapshot contre lui."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        principles_dir: Path | None = None,
        source_type: str = "live",
    ) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_principle_db(self.db_path)
        self.principles = load_principles_from_yaml(principles_dir)
        if self.db_path not in _SYNCED_DB_PATHS:
            self._sync_principles_to_db()
            _SYNCED_DB_PATHS.add(self.db_path)

    # ── Connexion ───────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Synchronisation catalogue ─────────────────────────────
    def _sync_principles_to_db(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            for p in self.principles:
                values = {
                    "principle_id": p.principle_id,
                    "version": p.version,
                    "origin": p.origin,
                    "kind": p.kind,
                    "source_status": p.source_status,
                    "v9_status": p.v9_status,
                    "scope_timeframes_json": json.dumps(p.scope_timeframes, ensure_ascii=False),
                    "scope_currencies_json": json.dumps(p.scope_currencies, ensure_ascii=False),
                    "conditions_json": json.dumps(p.conditions, ensure_ascii=False),
                    "emits_json": json.dumps(p.emits, ensure_ascii=False),
                    "bounds_json": json.dumps(p.bounds, ensure_ascii=False),
                    "anti_signal_bias": p.anti_signal_bias,
                    "notes": p.notes,
                    "created_by": p.created_by,
                    "created_at_source": p.created_at_source,
                    "synced_at": now,
                }
                columns = ", ".join(PRINCIPLES_COLUMNS)
                placeholders = ", ".join("?" for _ in PRINCIPLES_COLUMNS)
                conn.execute(
                    f"INSERT OR REPLACE INTO principles ({columns}) VALUES ({placeholders})",
                    [values[c] for c in PRINCIPLES_COLUMNS],
                )
            conn.commit()
        finally:
            conn.close()

    # ── Chargement du contexte (scène/comportement/fenêtre/exploitabilité) ──
    def _load_shared_context(self, conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
        context: dict[str, Any] = {}

        forces_row = conn.execute(
            "SELECT symbol, timeframe, mid, stale FROM forces_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if forces_row is None:
            raise PrincipleEngineError(f"snapshot de forces introuvable: {snapshot_id!r}")
        symbol = forces_row["symbol"]
        timeframe = forces_row["timeframe"]
        context["pf_mid"] = forces_row["mid"]
        context["stale"] = bool(forces_row["stale"])

        scene_row = conn.execute(
            "SELECT * FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        scene_id = None
        behavior_row = None
        window_row = None
        exploitability_row = None
        if scene_row is not None:
            scene_id = scene_row["scene_id"]
            try:
                coalitions = json.loads(scene_row["coalitions_json"] or "[]")
            except (TypeError, ValueError):
                coalitions = []
            try:
                antagonismes = json.loads(scene_row["antagonismes_json"] or "[]")
            except (TypeError, ValueError):
                antagonismes = []
            context["coalitions_count"] = len(coalitions)
            context["antagonismes_count"] = len(antagonismes)

            behavior_row = conn.execute(
                "SELECT * FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
                (scene_id,),
            ).fetchone()

        behavior_id = None
        if behavior_row is not None:
            behavior_id = behavior_row["behavior_id"]
            context["qualification"] = behavior_row["qualification"]
            context["intensite"] = behavior_row["intensite"]
            context["phase"] = behavior_row["phase"]
            context["confiance_qualification"] = behavior_row["confiance_qualification"]
            context["point_de_rupture_detecte"] = bool(behavior_row["point_de_rupture_detecte"])
            context["sens_transition"] = behavior_row["sens_transition"]

            window_row = conn.execute(
                "SELECT * FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
                (behavior_id,),
            ).fetchone()

        window_id = None
        if window_row is not None:
            window_id = window_row["window_id"]
            context["window_statut"] = window_row["statut"]
            context["type_fenetre"] = window_row["type_fenetre"]
            context["niveau_confiance"] = window_row["niveau_confiance"]
            context["fragilite_detectee"] = bool(window_row["fragilite_detectee"])

            exploitability_row = conn.execute(
                "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1",
                (window_id,),
            ).fetchone()

        exploitability_id = None
        if exploitability_row is not None:
            exploitability_id = exploitability_row["exploitability_id"]
            context["exploitability_statut"] = exploitability_row["statut"]
            context["niveau_confiance_global"] = exploitability_row["niveau_confiance_global"]

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "scene_id": scene_id,
            "behavior_id": behavior_id,
            "window_id": window_id,
            "exploitability_id": exploitability_id,
            "context": context,
        }

    def _load_per_currency_rows(
        self, conn: sqlite3.Connection, table: str, snapshot_id: str
    ) -> dict[str, sqlite3.Row]:
        try:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE forces_snapshot_ref = ?", (snapshot_id,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {row["currency"].upper(): row for row in rows if row["currency"]}

    def _build_currency_context(
        self,
        base_context: dict[str, Any],
        currency: str,
        regime_by_currency: dict[str, sqlite3.Row],
        zone_by_currency: dict[str, sqlite3.Row],
        force_value: float | None,
    ) -> dict[str, Any]:
        context = dict(base_context)
        context["force_value"] = force_value

        regime_row = regime_by_currency.get(currency)
        if regime_row is not None:
            context["regime_type"] = regime_row["regime_type"]
            context["cassure_type"] = regime_row["cassure_type"]
            context["cassure_direction"] = regime_row["cassure_direction"]
            context["mean_reversion_zone"] = bool(regime_row["mean_reversion_zone"])

        zone_row = zone_by_currency.get(currency)
        if zone_row is not None:
            context["state"] = zone_row["state"]
            context["prev_state"] = zone_row["prev_state"]
            context["z_current"] = zone_row["z_current"]
            context["z_extreme_dir"] = zone_row["z_extreme_dir"]
            context["prev_z_extreme_dir"] = zone_row["prev_z_extreme_dir"]
            context["bars_in_extreme"] = zone_row["bars_in_extreme"]
            context["tension_score"] = zone_row["tension_score"]
            context["absorbed_pullbacks"] = zone_row["absorbed_pullback_count"]

        return context

    # ── Évaluation principale ─────────────────────────────────
    def evaluate_principles(self, snapshot_id: str) -> list[dict[str, Any]]:
        """Évalue les 27 principes (ACTIVE + SHADOW) pour un snapshot, par
        devise concernée par le scope de chaque principe. Persiste chaque
        évaluation dans `principle_evaluations` et retourne la liste des
        évaluations produites (pour SignalGenerator / DecisionLogger)."""
        conn = self._connect()
        try:
            shared = self._load_shared_context(conn, snapshot_id)
            symbol = shared["symbol"]
            timeframe = shared["timeframe"]
            base_context = shared["context"]

            regime_by_currency = self._load_per_currency_rows(conn, "regime_snapshots", snapshot_id)
            zone_by_currency = self._load_per_currency_rows(conn, "zone_diagnostics", snapshot_id)
            forces_row = conn.execute(
                "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()

            evaluations: list[dict[str, Any]] = []
            now = datetime.now(timezone.utc).isoformat()

            for currency in DEVISES:
                force_value = forces_row[f"force_{currency.lower()}"] if forces_row else None
                context = self._build_currency_context(
                    base_context, currency, regime_by_currency, zone_by_currency, force_value
                )
                for principle in self.principles:
                    if not principle.matches_scope(symbol, timeframe, currency):
                        continue
                    result = evaluate_principle(principle, context)
                    evaluation = {
                        "evaluation_id": _generate_evaluation_id(symbol, timeframe, currency, principle.principle_id),
                        "schema_version": SCHEMA_VERSION,
                        "timestamp": now,
                        "snapshot_id": snapshot_id,
                        "principle_id": principle.principle_id,
                        "v9_status": principle.v9_status,
                        "kind": principle.kind,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "currency": currency,
                        "anti_signal_bias": principle.anti_signal_bias,
                        **result,
                    }
                    evaluations.append(evaluation)

            self._write_evaluations_to_db(conn, evaluations)
            return evaluations
        finally:
            conn.close()

    def _write_evaluations_to_db(self, conn: sqlite3.Connection, evaluations: list[dict]) -> None:
        columns = ", ".join(PRINCIPLE_EVALUATIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in PRINCIPLE_EVALUATIONS_COLUMNS)
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for e in evaluations:
            rows.append((
                e["evaluation_id"], e["schema_version"], e["timestamp"], e["snapshot_id"],
                e["principle_id"], e["v9_status"], e["kind"], e["symbol"], e["timeframe"], e["currency"],
                e["triggered"], e["direction"], e["confidence"], e["anti_signal_bias"], e["reason"],
                json.dumps({}, ensure_ascii=False), self.source_type, now,
            ))
        conn.executemany(
            f"INSERT OR IGNORE INTO principle_evaluations ({columns}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()


def _generate_evaluation_id(symbol: str, timeframe: str, currency: str, principle_id: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"peval_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_"
        f"{currency.lower()}_{principle_id.lower()}_{uuid.uuid4().hex[:6]}"
    )
