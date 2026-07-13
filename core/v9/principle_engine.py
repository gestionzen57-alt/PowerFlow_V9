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

GAP RÉSOLU — les 9 principes `kind: node_rule` ACTIVE sont désormais tous
déclenchables (zone_diagnostics alimentée par core/v9/zone_detector.py ;
coalition_strength et h1_dir/h1_state/m5_dir/m5_state enrichis dans le
contexte par _load_shared_context, y compris pour ANTAGONIST_NODE et
COALITION_NODE, les 2 derniers à avoir été comblés). Les 18 principes
`kind: grammar` sont des entrées de vocabulaire documentaires : 17 restent
sans `conditions:` (non émetteurs, catalogués et journalisés mais ne
déclenchant jamais de signal) ; GRAMMAR_REGIME a reçu ses conditions
réelles en Phase 9.8 Phase B (voir son YAML) et est donc, comme les 9
node_rule, un détecteur réellement évaluable (DOCTRINE.md Règle 11,
« architecture 9+1 »).
"""

from __future__ import annotations

import json
import os
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

# ── P3-WIRE (2026-07-13) — kill switch dédié, OFF par défaut ─────────
# Câble core/v9/adaptive_thresholds_at_runtime.py (module pur P3, commit
# 5abfa2b, jamais branché) dans le contexte partagé, même pattern que
# vol_regime (P6) et news_context (P4) : ajoute des champs DESCRIPTIFS
# au contexte, ne modifie AUCUNE condition YAML existante (R25' — aucun
# principe ACTIVE/SHADOW ne référence encore ces champs). Nom dédié,
# ne réutilise pas un kill switch existant (consigne mission).
ADAPTIVE_THRESHOLDS_WIRED_ENV = "V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED"


def adaptive_thresholds_wired_enabled() -> bool:
    """Kill switch V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED (défaut '0' = OFF)."""
    return os.environ.get(ADAPTIVE_THRESHOLDS_WIRED_ENV, "0") == "1"


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
            "SELECT * FROM forces_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if forces_row is None:
            raise PrincipleEngineError(f"snapshot de forces introuvable: {snapshot_id!r}")
        symbol = forces_row["symbol"]
        timeframe = forces_row["timeframe"]
        context["pf_mid"] = forces_row["mid"]
        context["stale"] = bool(forces_row["stale"])

        # ── Contexte cross-TF (ANTAGONIST_NODE) ─────────────────────
        # Charge les snapshots H1 et M5 les plus récents pour le même
        # symbole, et dérive direction + état par devise. Utilisé par
        # ANTAGONIST_NODE (h1_state, m5_state, h1_dir, m5_dir).
        # L'état est dérivé de la position de la force par rapport à
        # la référence neutre 50.0 : >55 = HAUSSIERE, <45 = BAISSIERE,
        # sinon NEUTRAL. La direction est la même logique.
        cross_tf_context: dict[str, Any] = {}
        for target_tf in ("H1", "M5"):
            if target_tf == timeframe:
                # Même timeframe que le snapshot courant — dériver
                # l'état depuis les forces du snapshot lui-même
                forces_self = {}
                for d in DEVISES:
                    val = forces_row[f"force_{d.lower()}"]
                    if val is not None:
                        forces_self[d] = float(val)
                # Règle 29 — DOCTRINE §29. Propager compression_extension_etat
                # du snapshot pour permettre à _detect_zone_type de qualifier
                # respiration/compression. Lecture défensive (champ nullable).
                try:
                    comp_state = forces_row["compression_extension_etat"]
                except (KeyError, IndexError):
                    comp_state = None
                if comp_state:
                    cross_tf_context["compression_extension_etat"] = comp_state
                if forces_self:
                    max_force = max(forces_self.values())
                    if max_force > 60:
                        cross_tf_context[f"{target_tf.lower()}_state"] = "HAUSSIERE"
                    elif max_force < 40:
                        cross_tf_context[f"{target_tf.lower()}_state"] = "BAISSIERE"
                    else:
                        cross_tf_context[f"{target_tf.lower()}_state"] = "NEUTRAL"
                    if max_force > 55:
                        cross_tf_context[f"{target_tf.lower()}_dir"] = "HAUSSIERE"
                    elif max_force < 45:
                        cross_tf_context[f"{target_tf.lower()}_dir"] = "BAISSIERE"
                    else:
                        cross_tf_context[f"{target_tf.lower()}_dir"] = "NEUTRE"
                else:
                    cross_tf_context[f"{target_tf.lower()}_dir"] = None
                    cross_tf_context[f"{target_tf.lower()}_state"] = None
                continue
            tf_row = conn.execute(
                "SELECT * FROM forces_snapshots "
                "WHERE symbol = ? AND timeframe = ? AND stale = 0 "
                "ORDER BY timestamp DESC LIMIT 1",
                (symbol, target_tf),
            ).fetchone()
            if tf_row is None:
                cross_tf_context[f"{target_tf.lower()}_dir"] = None
                cross_tf_context[f"{target_tf.lower()}_state"] = None
                continue
            # Direction par devise : on prend la devise la plus forte
            # (celle avec la force max) comme indicateur directionnel
            forces = {}
            for d in DEVISES:
                val = tf_row[f"force_{d.lower()}"]
                if val is not None:
                    forces[d] = float(val)
            if not forces:
                cross_tf_context[f"{target_tf.lower()}_dir"] = None
                cross_tf_context[f"{target_tf.lower()}_state"] = None
                continue
            max_devise = max(forces, key=forces.get)
            max_force = forces[max_devise]
            # Direction : haussier si la devise la plus forte > 50
            if max_force > 55:
                cross_tf_context[f"{target_tf.lower()}_dir"] = "HAUSSIERE"
            elif max_force < 45:
                cross_tf_context[f"{target_tf.lower()}_dir"] = "BAISSIERE"
            else:
                cross_tf_context[f"{target_tf.lower()}_dir"] = "NEUTRE"
            # State : idem, mappé sur le vocabulaire V8 attendu
            if max_force > 60:
                cross_tf_context[f"{target_tf.lower()}_state"] = "HAUSSIERE"
            elif max_force < 40:
                cross_tf_context[f"{target_tf.lower()}_state"] = "BAISSIERE"
            else:
                cross_tf_context[f"{target_tf.lower()}_state"] = "NEUTRAL"
        context.update(cross_tf_context)

        scene_row = conn.execute(
            "SELECT * FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        scene_id = None
        behavior_row = None
        window_row = None
        exploitability_row = None

        # ── Fallbacks COMPLETS (avant scene_row) ──
        # Tous les champs PROPAGÉS attendus par EXPECTED_CONTEXT_FIELDS
        # (cf. docs/architecture/CONTEXT_CONTRACT.md) doivent être
        # présents dans le contexte, même quand scene_row = None.
        # Cela permet aux conditions des principes YAML de toujours
        # recevoir une clé (avec valeur par défaut) au lieu d'un
        # KeyError — doctrine de robustesse de propagation.

        # Cross-TF (H1/M5 dir + state) : pas de fallback ici.
        # Le bloc précédent (lignes 349-421) calcule ces champs depuis
        # les forces_snapshots (cible M5 ou M5==timeframe) et les pose
        # dans context via context.update(cross_tf_context).
        # Un fallback None ici ÉCRASERAIT la valeur calculée — bug
        # introduit lors de l'extension des fallbacks (commit 046b285,
        # 2026-07-06). ANTAGONIST_NODE bloqué par ce bug (0/1728).

        # Coalition intelligence (Tâche C)
        context["coalitions_count"] = 0
        context["antagonismes_count"] = 0
        context["coalition_strength"] = 0.0
        context["coalition_mtf_score"] = 0
        context["coalition_mtf_depth"] = "M5"
        context["coalition_rotation_detectee"] = False
        context["coalition_rotation_ancien_leader"] = None
        context["coalition_rotation_nouveau_leader"] = None

        # Cinématique (P1b)
        context["velocite_moyenne"] = 0.0
        context["acceleration_vraie"] = 0.0
        context["dispersion_velocite"] = 0.0
        context["pente"] = 0.0
        context["courbure"] = 0.0
        context["pliure_detectee"] = False
        context["pliure_severite"] = None

        # Risk assessment (Tâche B)
        context["risk_sentiment"] = "NEUTRE"
        context["risk_confidence"] = 0
        context["risk_on_score"] = 0.0
        context["risk_off_score"] = 0.0
        context["persistance_confirmee"] = False

        # Bascule (Anomalie #3)
        context["bascule_detectee"] = False
        context["bascule_devise_dominante"] = None
        context["bascule_intensite"] = 0.0

        # Contexte temporel (Anomalie #4)
        context["session_marche"] = "inconnu"
        context["heure_utc"] = None
        context["jour_semaine"] = None
        context["marche_ouvert"] = True

        # Vol regime (autopilot P6 2026-07-13)
        # Calcul ATR-30 sur (high, low) des 30 dernières bougies du même
        # (symbol, timeframe), classifie en LOW/NORMAL/HIGH/EXTREME.
        # Sert aux conditions YAML `vol_regime in [...]` / != EXTREME.
        # Défaut conservateur "NORMAL" si pas de données (intermédiaire).
        context["vol_regime"] = "NORMAL"
        context["vol_atr_pips"] = None
        context["vol_regime_level"] = 1

        # Comportements
        context["qualification"] = None
        context["intensite"] = None
        context["phase"] = None
        context["confiance_qualification"] = None
        context["point_de_rupture_detecte"] = False
        context["sens_transition"] = None
        # P2 DORMANT fallbacks
        context["contexte_temporel_fenetre"] = None
        context["point_de_rupture_declencheur"] = None
        context["est_variante"] = False
        context["comportement_reference"] = None

        # Fenêtres
        context["window_statut"] = None
        context["type_fenetre"] = None
        context["niveau_confiance"] = None
        context["fragilite_detectee"] = False

        # Exploitabilité
        context["exploitability_statut"] = None
        context["niveau_confiance_global"] = None

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

            # coalition_strength : ratio de devises alignées / total devises,
            # pondéré par l'intensité moyenne d'alignement des coalitions.
            # Nécessaire pour COALITION_NODE (champ coalition_strength >= 0.5).
            if coalitions:
                aligned_devises = set()
                total_intensity = 0.0
                for c in coalitions:
                    aligned_devises.update(c["devises_alignees"])
                    total_intensity += c["intensite_alignement"]
                coalition_strength = (len(aligned_devises) / 8.0) * (total_intensity / len(coalitions) / 50.0)
                context["coalition_strength"] = round(coalition_strength, 4)
            else:
                context["coalition_strength"] = 0.0

            # ── Contexte cinématique (velocité réelle, pente, pliure) ──
            # Extrait les 7 champs de cinematique_json pour les rendre
            # accessibles aux conditions des principes YAML.
            try:
                cinematique = json.loads(scene_row["cinematique_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                cinematique = {}
            context["velocite_moyenne"] = float(cinematique.get("velocite_moyenne", 0.0) or 0.0)
            context["acceleration_vraie"] = float(cinematique.get("acceleration_vraie", 0.0) or 0.0)
            context["dispersion_velocite"] = float(cinematique.get("dispersion_velocite", 0.0) or 0.0)
            context["pente"] = float(cinematique.get("pente", 0.0) or 0.0)
            context["courbure"] = float(cinematique.get("courbure", 0.0) or 0.0)
            pliure = cinematique.get("pliure", {}) or {}
            context["pliure_detectee"] = bool(pliure.get("detectee", False))
            context["pliure_severite"] = pliure.get("severite")

            # ── RiskMeter (Tâche B) ────────────────────────────────
            # Sentiment institutionnel risk_on / risk_off / mixte / neutre
            # + confidence + scores + persistance, lus depuis la colonne
            # risk_assessment_json de la scène courante (calculé par
            # SceneBuilder via core/v9/risk_meter.py).
            try:
                risk_assessment = json.loads(scene_row["risk_assessment_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                risk_assessment = {}
            if not isinstance(risk_assessment, dict):
                risk_assessment = {}
            context["risk_sentiment"] = str(risk_assessment.get("risk_sentiment") or "NEUTRE")
            try:
                context["risk_confidence"] = int(risk_assessment.get("risk_confidence", 0) or 0)
            except (TypeError, ValueError):
                context["risk_confidence"] = 0
            try:
                context["risk_on_score"] = float(risk_assessment.get("risk_on_score", 0.0) or 0.0)
                context["risk_off_score"] = float(risk_assessment.get("risk_off_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                context["risk_on_score"] = 0.0
                context["risk_off_score"] = 0.0
            context["persistance_confirmee"] = bool(
                risk_assessment.get("persistance_confirmee", False)
            )

            # ── Tâche C2 — coalition_mtf_score / depth / rotation ──
            # Propagés depuis confluences_mtf_json (Tâche C1) et
            # coalitions_json (rotation_leadership.detectee) de la scène.
            try:
                confluences_mtf = json.loads(
                    scene_row["confluences_mtf_json"] or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                confluences_mtf = {}
            if not isinstance(confluences_mtf, dict):
                confluences_mtf = {}
            try:
                context["coalition_mtf_score"] = int(
                    confluences_mtf.get("coalition_mtf_score", 0) or 0
                )
            except (TypeError, ValueError):
                context["coalition_mtf_score"] = 0
            context["coalition_mtf_depth"] = str(
                confluences_mtf.get("coalition_mtf_depth") or "M5"
            )

            # Rotation de leadership : première coalition où
            # rotation_leadership.detectee == True. Fallback False/None/None.
            context["coalition_rotation_detectee"] = False
            context["coalition_rotation_ancien_leader"] = None
            context["coalition_rotation_nouveau_leader"] = None
            for c in coalitions:
                rot = c.get("rotation_leadership") or {}
                if rot.get("detectee"):
                    context["coalition_rotation_detectee"] = True
                    context["coalition_rotation_ancien_leader"] = rot.get("ancien_leader")
                    context["coalition_rotation_nouveau_leader"] = rot.get("nouveau_leader")
                    break

            # ── Anomalie #3 — bascule_equilibre.sens dans le contexte ──
            # 1er antagonisme avec bascule_equilibre.detectee == True.
            # Expose la donnée directionnelle la plus précise de la
            # couche Scènes (quelle devise prend le dessus dans le conflit).
            context["bascule_detectee"] = False
            context["bascule_devise_dominante"] = None
            context["bascule_intensite"] = 0.0
            for a in antagonismes:
                bascule = a.get("bascule_equilibre") or {}
                if bascule.get("detectee"):
                    context["bascule_detectee"] = True
                    context["bascule_devise_dominante"] = bascule.get("sens")
                    try:
                        context["bascule_intensite"] = float(
                            a.get("intensite_conflit", 0.0) or 0.0
                        )
                    except (TypeError, ValueError):
                        context["bascule_intensite"] = 0.0
                    break

            # ── Anomalie #4 — contexte_temporel dans le contexte ────
            # Session de marché / heure UTC / jour de semaine / marché
            # ouvert. Lu depuis contexte_temporel_json (calculé par
            # SceneBuilder._identify_context).
            try:
                contexte_temporel = json.loads(
                    scene_row["contexte_temporel_json"] or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                contexte_temporel = {}
            if not isinstance(contexte_temporel, dict):
                contexte_temporel = {}
            # Mapping : SceneBuilder._identify_context retourne
            # {"session": "Londres"|"New York"|"Tokyo"|"Sydney"|"chevauchement",
            #  "fenetre": "..."}. On normalise vers le vocabulaire
            # court attendu par le contexte.
            session_raw = str(contexte_temporel.get("session") or "").strip().lower()
            session_map = {
                "londres": "london",
                "new york": "new_york",
                "tokyo": "asie",
                "sydney": "sydney",
                "chevauchement": "overlap",
            }
            context["session_marche"] = session_map.get(session_raw, "inconnu")
            # P2 DORMANT: contexte_temporel.fenetre — injecter dans le contexte
            context["contexte_temporel_fenetre"] = contexte_temporel.get("fenetre")
            # Heure UTC et jour de semaine dérivés du timestamp de la scène
            try:
                ts_iso = scene_row["timestamp"].replace("Z", "+00:00")
                dt_scene = datetime.fromisoformat(ts_iso)
                if dt_scene.tzinfo is None:
                    dt_scene = dt_scene.replace(tzinfo=timezone.utc)
                context["heure_utc"] = dt_scene.hour
                context["jour_semaine"] = dt_scene.weekday()  # 0=lundi, 4=vendredi
            except (TypeError, ValueError):
                context["heure_utc"] = None
                context["jour_semaine"] = None
            # Marché ouvert : lundi-vendredi ET pas dans la fenêtre
            # de fermeture vendredi 22h UTC → dimanche 22h UTC.
            try:
                if context["jour_semaine"] is None:
                    context["marche_ouvert"] = True
                else:
                    j = context["jour_semaine"]
                    h = context["heure_utc"] or 0
                    # Fermé : vendredi >= 22h UTC ou samedi ou dimanche < 22h UTC
                    if j == 4 and h >= 22:
                        context["marche_ouvert"] = False
                    elif j == 5:
                        context["marche_ouvert"] = False
                    elif j == 6 and h < 22:
                        context["marche_ouvert"] = False
                    else:
                        context["marche_ouvert"] = True
            except Exception:
                context["marche_ouvert"] = True

            behavior_row = conn.execute(
                "SELECT * FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
                (scene_id,),
            ).fetchone()

        # ── Vol regime (autopilot P6 2026-07-13) ─────────────────
        # Calcul ATR-30 sur les 30 dernières bougies du même
        # (symbol, timeframe) que le snapshot courant, classifie en
        # LOW/NORMAL/HIGH/EXTREME. Délégué à core.v9.vol_regime (module
        # pur). Volatilité JPY (USDJPY/GBPJPY) → multiplier=100.
        # Lecture défensive : si query échoue ou moins de 30 bougies,
        # on conserve le fallback "NORMAL" posé plus haut.
        try:
            from core.v9.vol_regime import compute_atr_pips, classify_atr
            from core.v9.exit_simulator import pips_multiplier_for_symbol

            pip_mult = pips_multiplier_for_symbol(symbol)
            candles_rows = conn.execute(
                "SELECT high, low FROM forces_snapshots "
                "WHERE symbol = ? AND timeframe = ? "
                "  AND high IS NOT NULL AND low IS NOT NULL "
                "ORDER BY bar_time DESC LIMIT 30",
                (symbol, timeframe),
            ).fetchall()
            highs = [float(r["high"]) for r in candles_rows]
            lows = [float(r["low"]) for r in candles_rows]
            atr_pips = compute_atr_pips(highs, lows, pip_multiplier=pip_mult)
            level = classify_atr(atr_pips)
            from core.v9.vol_regime import _LEVEL_TO_LABEL
            context["vol_atr_pips"] = atr_pips
            context["vol_regime_level"] = level
            context["vol_regime"] = _LEVEL_TO_LABEL.get(level, "NORMAL")
        except Exception:
            # Garde-fou — ne JAMAIS casser le pipeline sur un calcul dérivé.
            # Fallback déjà posé plus haut ("NORMAL", None, 1).
            pass

        behavior_id = None
        if behavior_row is not None:
            behavior_id = behavior_row["behavior_id"]
            context["qualification"] = behavior_row["qualification"]
            context["intensite"] = behavior_row["intensite"]
            context["phase"] = behavior_row["phase"]
            context["confiance_qualification"] = behavior_row["confiance_qualification"]
            context["point_de_rupture_detecte"] = bool(behavior_row["point_de_rupture_detecte"])
            context["sens_transition"] = behavior_row["sens_transition"]
            # P2 DORMANT: point_de_rupture.declencheur + variante_de_comportement_connu
            context["point_de_rupture_declencheur"] = behavior_row["point_de_rupture_declencheur"]
            context["est_variante"] = bool(behavior_row["est_variante"])
            context["comportement_reference"] = behavior_row["comportement_reference"]
            # Règle 29 — Lecture zone_type (DOCTRINE §29, import V8 §3.1+§3bis).
            # Lecture heuristique pure, 0 modif seuil. Résolu en amont pour
            # permettre aux patterns YAML (zone_type filter futur) de discriminer
            # naissance / 2e_jambe / continuation / respiration.
            try:
                context["zone_type"] = _detect_zone_type(context)
            except Exception:
                # Garde-fou — ne JAMAIS casser le pipeline sur une lecture dérivée.
                context["zone_type"] = "indetermine"

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

        # ── Contexte news (couche transversale NewsContext) ────────────
        # Placé EN DERNIER dans le bloc : tous les context.update()
        # précédents ont déjà posé leurs valeurs, donc ce bloc ne peut
        # rien écraser (leçon bug ANTAGONIST_NODE 2026-07-06, commit
        # 046b285). 5 champs PROPAGÉS dans CONTEXT_CONTRACT.md.
        try:
            from core.v9.news_context import NewsContext
            news_data = NewsContext().assess(datetime.now(timezone.utc))
            context.update(news_data)
        except Exception:
            context.update({
                "news_type": None,
                "news_phase": "NEUTRE",
                "news_distance_min": None,
                "news_importance": "NEUTRE",
                "news_session_clean": True,
            })

        # ── Champ calculé pour COALITION_NODE news-aware ─────────
        # coalition_news_allow = news_session_clean OR news_phase == "POST_NEWS"
        # Permet à la coalition de déclencher soit en session propre
        # (pas de news HIGH à venir), soit en POST_NEWS (réorganisation
        # confirmée après le choc). Les conditions YAML sont en AND, donc
        # ce champ combine l'OR logique en un seul booléen.
        context["coalition_news_allow"] = (
            context.get("news_session_clean", True) is True
            or context.get("news_phase") == "POST_NEWS"
        )

        # ── Adaptive thresholds P3-WIRE (kill switch OFF par défaut) ────
        # Placé APRÈS vol_regime et news (ce bloc en dépend), et APRÈS
        # tout context.update() du bloc news (même garde-fou anti-écrasement
        # que le bloc news lui-même, cf commentaire ligne ~793). Descriptif
        # uniquement : aucun principe YAML ACTIVE/SHADOW ne consomme encore
        # ces 3 champs, donc switch OFF *ou* ON laisse evaluate_condition/
        # evaluate_principle strictement inchangés tant qu'aucun principe
        # ne référence "adaptive_coalition_threshold" et consorts (cf.
        # tests/test_p3_wire_integration.py — non-régression bit-à-bit).
        context["adaptive_thresholds_enabled"] = adaptive_thresholds_wired_enabled()
        if context["adaptive_thresholds_enabled"]:
            try:
                from core.v9.adaptive_thresholds_at_runtime import get_effective_thresholds

                news_phase_raw = context.get("news_phase") or "NEUTRE"
                # news_context.py émet "NEUTRE" pour absence de news ;
                # adaptive_thresholds_at_runtime attend "NORMAL"/"UNKNOWN"
                # (son fallback NEWS_MULTIPLIER.get(x, 1.0) = 1.0 de toute
                # façon pour une clé inconnue — mapping explicite pour la
                # lisibilité, comportement identique).
                news_phase_mapped = "NORMAL" if news_phase_raw == "NEUTRE" else news_phase_raw
                effective = get_effective_thresholds(
                    context.get("vol_regime", "NORMAL"),
                    news_phase=news_phase_mapped,
                    timeframe=timeframe,
                )
                context["adaptive_coalition_threshold"] = effective["COALITION"]
                context["adaptive_antagonism_threshold"] = effective["ANTAGONISM"]
                context["adaptive_pliure_threshold"] = effective["PLIURE"]
            except Exception:
                # Garde-fou — ne JAMAIS casser le pipeline sur un calcul
                # dérivé (même doctrine que le bloc vol_regime ci-dessus).
                pass

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

        # ── Fallbacks zone_diagnostics (doctrine realign Phase 9.8, C2) ──
        # Les 8 champs ci-dessous sont référencés par des conditions des
        # 27 YAML (cf. audit champs conditions/value_field/bounds). Sans
        # ligne zone_diagnostics pour cette devise (zone_row is None), ils
        # étaient simplement absents du dict — `context.get(field)` en
        # amont (evaluate_condition) retombait déjà sur None, donc aucun
        # KeyError, mais la clé n'existait pas explicitement. Poser un
        # défaut explicite ici suit la même doctrine de propagation que
        # le bloc "Fallbacks COMPLETS" de _load_shared_context (toujours
        # une clé présente, jamais une absence silencieuse).
        context["state"] = None
        context["prev_state"] = None
        context["z_current"] = None
        context["z_extreme_dir"] = None
        context["prev_z_extreme_dir"] = None
        context["bars_in_extreme"] = None
        context["tension_score"] = None
        context["absorbed_pullbacks"] = None

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

        # Règle 29 — DOCTRINE §29. Calcule zone_type (naissance/2e_jambe/
        # continuation/respiration/indetermine) à partir du context enrichi.
        # Lecture défensive : toute exception => "indetermine" (jamais casser).
        try:
            context["zone_type"] = _detect_zone_type(context)
        except Exception:
            context["zone_type"] = "indetermine"

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
                        # Règle 29 — DOCTRINE §29. Persiste la lecture §3bis
                        # utile pour analyse offline (replay, calibration).
                        # Note : result contient "triggered"/"confidence"/"reason",
                        # on ajoute zone_type depuis context.
                        "context_json": json.dumps(
                            {"zone_type": context.get("zone_type", "indetermine")},
                            ensure_ascii=False, default=str,
                        ),
                        **result,
                    }
                    # P0 DB optimisation 2026-07-08 : on n'écrit les
                    # évaluations SHADOW que si triggered=1. Les 16 SHADOW
                    # génèrent ~1M lignes triggered=0 (99.9999% de bruit)
                    # qui ne sont jamais consultées par SignalGenerator.
                    # On les évalue toujours en mémoire (pour détecter
                    # un éventuel déclenchement), mais on ne les persiste
                    # pas. Gain : -60% des lignes principle_evaluations.
                    # Le filtre est dans _write_evaluations_to_db, pas ici,
                    # pour préserver le retour complet en mémoire.
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
            # P0 DB optimisation 2026-07-08 : skip SHADOW non-déclenchés.
            # Les 16 SHADOW génèrent ~1M lignes triggered=0 (99.9999% de
            # bruit) jamais consultées par SignalGenerator. On les évalue
            # toujours en mémoire (retour complet), mais on ne les persiste
            # pas. Gain : -60% des lignes principle_evaluations.
            if e["v9_status"] == STATUS_SHADOW and not e["triggered"]:
                continue
            rows.append((
                e["evaluation_id"], e["schema_version"], e["timestamp"], e["snapshot_id"],
                e["principle_id"], e["v9_status"], e["kind"], e["symbol"], e["timeframe"], e["currency"],
                e["triggered"], e["direction"], e["confidence"], e["anti_signal_bias"], e["reason"],
                # Règle 29 — DOCTRINE §29. Préserve le context_json calculé
                # par evaluate_principles (zone_type) au lieu du {} hardcodé.
                e.get("context_json", "{}"), self.source_type, now,
            ))
        conn.executemany(
            f"INSERT OR REPLACE INTO principle_evaluations ({columns}) VALUES ({placeholders})",
            rows,
        )
        conn.commit()


def _generate_evaluation_id(symbol: str, timeframe: str, currency: str, principle_id: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"peval_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_"
        f"{currency.lower()}_{principle_id.lower()}_{uuid.uuid4().hex[:6]}"
    )


# ── Helpers doctrine §29 — Lecture de marché (zone_type) ──────────────
# Règle 29 (DOCTRINE.md, import V8 §3.1+§3bis+§6+§8, 2026-07-07) :
# ajouter une lecture `zone_type` parmi les 6 dimensions de scène pour
# pondérer les patterns NODE_* par stade d'arrivée en zone.
# 4 catégories : naissance / 2e_jambe / continuation / respiration.
# N'altère pas les seuils existants (règle 11 = YAML gelés). Lecture seule.


def _detect_zone_type(context: dict) -> str:
    """Lecture heuristique du type d'arrivée en zone.

    Sources lues (toutes déjà chargées dans `context` par
    `_load_shared_context`, donc 0 coût additionnel) :

    - ``prev_state``  : scène précédente (NEUTRAL/EARLY_EXTREME/...)
    - ``state``       : scène courante
    - ``z_current``   : z-score courant (si propagé)
    - ``bars_in_extreme`` : durée en zone extrême
    - ``zone_state``  : idem state (alias sémantique)
    - ``compression_extension_etat`` : compression/extension ticks
    - ``bars_in_extreme`` : décompte zone (≤2 = naissance rapide)

    Règles de décision (ordre d'évaluation, conservatrices) :

    1. ``naissance``     — prev_state=NEUTRAL + state∈{EARLY_EXTREME, ACCUMULATING, LEAKING, RUPTURE}
    2. ``2e_jambe``      — bars_in_extreme ∈ [3,5] + state ∈ {EARLY_EXTREME, EXTENSION}
                          + compression_extension_etat ∉ {"COMPRESSING"}
    3. ``continuation``  — state ∈ {ACCUMULATING, LEAKING, RUPTURE} + prev_state identique
    4. ``respiration``   — state ∈ {ACCUMULATING} + compression_extension_etat="COMPRESSING"
    5. défaut           — "indetermine" (ne JAMAIS inventer, règle 25)

    La valeur "indetermine" est explicite pour permettre aux patterns YAML
    (zone_type filter futur) de distinguer absence d'info vs absence de pattern.
    """
    prev = str(context.get("prev_state") or context.get("zone_state_prev") or "").upper()
    cur = str(context.get("state") or context.get("zone_state") or "").upper()
    bars = context.get("bars_in_extreme")
    comp = str(context.get("compression_extension_etat") or "").upper()

    # 4. respiration — avant continuation pour traiter la compression en priorité
    if "ACCUMULATING" in cur and "COMPRESSING" in comp:
        return "respiration"

    # 1. naissance — NEUTRAL → zone active
    if "NEUTRAL" in prev and cur in {
        "EARLY_EXTREME", "ACCUMULATING", "LEAKING", "RUPTURE",
    }:
        return "naissance"

    # 2. 2e jambe — zone tenue 3-5 barres, en extension, sans compression
    try:
        if bars is not None and 3 <= int(bars) <= 5 and cur in {
            "EARLY_EXTREME", "EXTENSION", "RUPTURE",
        } and "COMPRESSING" not in comp:
            return "2e_jambe"
    except (TypeError, ValueError):
        pass

    # 3. continuation — re-entrée dans la même zone active
    if cur in {"ACCUMULATING", "LEAKING", "RUPTURE"} and prev == cur:
        return "continuation"

    return "indetermine"
