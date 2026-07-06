"""BehaviorAnalyzer — couche Comportements (3e couche cognitive) PowerFlow V9.

Chaîne cognitive officielle : Forces -> Scènes -> [Comportements] -> Fenêtres -> Exploitabilité.

Cette couche lit une scène (couche amont immédiate, table `scenes`) et
qualifie sa dynamique dans le temps. Elle ne lit jamais les forces
directement pour son interprétation : la seule exception est une
déréférence administrative étroite de `forces_snapshot_ref` vers les
colonnes `symbol`/`timeframe` de `forces_snapshots` — jamais les
valeurs de force elles-mêmes — nécessaire car une scène est multi-
devises/multi-timeframes par conception (FORMAT_SCENES.md) alors que
FORMAT_COMPORTEMENTS.md exige un périmètre d'observation (paire + TF)
au niveau racine du comportement.

Elle ne prédit jamais, elle décrit. Elle ne statue jamais sur une
fenêtre. La confiance basse est une réponse valide : elle n'empêche
jamais l'émission de l'objet comportement.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.config import (
    BEHAVIOR_HISTORY_LOOKBACK,
    CONFIANCE_BASCULE_NETTE,
    CONFIANCE_PLIURE_SEVERE,
    DB_PATH,
    ROOT_DIR,
    SCHEMA_VERSION,
    SIMILARITY_THRESHOLD,
)
from core.v9.db_schema import get_connection
from core.v9.scene_db import init_scene_db

QUALIFICATIONS = [
    "maintien", "bascule", "lutte_forces", "contraction", "extension",
    "tension", "rupture", "reequilibrage", "annulation",
    "preparation_ouverture_fenetre", "seconde_bosse", "rotation_leadership",
]

INTENSITES = ["faible", "moderee", "forte", "extreme"]
PHASES = ["initiation", "developpement", "culmination", "resolution"]
SENS_TRANSITIONS = ["escalade", "desescalade", "inversion", "neutre"]

_INTENSITY_RANK = {v: i for i, v in enumerate(INTENSITES)}
# Poids de phase utilisé uniquement comme départage secondaire (à
# intensité égale) pour sens_transition : la résolution referme le
# cycle, elle ne "monte" pas par rapport à la culmination.
_PHASE_WEIGHT = {"initiation": 0, "developpement": 1, "culmination": 2, "resolution": 0}

# Paires de qualifications considérées comme opposées : une transition
# de l'une vers l'autre est toujours une "inversion", quelle que soit
# l'intensité relative.
OPPOSITE_QUALIFICATIONS = {
    frozenset({"contraction", "extension"}),
    frozenset({"tension", "reequilibrage"}),
    frozenset({"lutte_forces", "reequilibrage"}),
    frozenset({"rupture", "maintien"}),
    frozenset({"annulation", "bascule"}),
}

QUALIFICATION_LABELS = {
    "maintien": "Maintien",
    "bascule": "Bascule",
    "lutte_forces": "Lutte de forces",
    "contraction": "Contraction",
    "extension": "Extension",
    "tension": "Tension",
    "rupture": "Rupture",
    "reequilibrage": "Rééquilibrage",
    "annulation": "Annulation (recroisement)",
    "preparation_ouverture_fenetre": "Préparation d'ouverture de fenêtre",
    "seconde_bosse": "Seconde bosse",
    "rotation_leadership": "Rotation de leadership",
}

# Seuils heuristiques internes (non exposés en config.py — spécifiques
# aux détecteurs de cette couche, pas à une calibration produit).
LUTTE_FORCES_INTENSITE_MIN = 40.0
PLIURE_SEVERE_MIN = 15.0
WEAK_EXTENSION_MAX = 12.0
PREPARATION_STREAK_MIN = 2


class BehaviorAnalyzerError(ValueError):
    """Erreur d'analyse comportementale (scène introuvable, etc.)."""


@dataclass
class Scene:
    """Scène désérialisée depuis la table `scenes` (FORMAT_SCENES.md)."""

    scene_id: str
    schema_version: str
    timestamp: str
    symbol: str
    timeframe: str
    timeframes_concernes: list[str]
    forces_snapshot_ref: dict
    zone: dict
    coalitions: list[dict]
    antagonismes: list[dict]
    cinematique_locale: dict
    confluences_mtf: dict
    contexte_temporel: dict
    stale: bool

    @classmethod
    def from_row(cls, row: dict, symbol: str, timeframe: str) -> "Scene":
        return cls(
            scene_id=row["scene_id"],
            schema_version=row["schema_version"],
            timestamp=row["timestamp"],
            symbol=symbol,
            timeframe=timeframe,
            timeframes_concernes=json.loads(row["timeframes_concernes"]),
            forces_snapshot_ref={
                "snapshot_id": row["forces_snapshot_ref"],
                "timestamp": row["forces_snapshot_timestamp"],
            },
            zone=json.loads(row["zone_json"]),
            coalitions=json.loads(row["coalitions_json"]),
            antagonismes=json.loads(row["antagonismes_json"]),
            cinematique_locale=json.loads(row["cinematique_json"]),
            confluences_mtf=json.loads(row["confluences_mtf_json"]),
            contexte_temporel=json.loads(row["contexte_temporel_json"]),
            stale=bool(row["stale"]),
        )


def _max_antagonisme_intensite(scene: Scene) -> float:
    return max((a["intensite_conflit"] for a in scene.antagonismes), default=0.0)


def _max_coalition_intensite(scene: Scene) -> float:
    return max((c["intensite_alignement"] for c in scene.coalitions), default=0.0)


def _any_bascule(scene: Scene) -> bool:
    return any(a["bascule_equilibre"]["detectee"] for a in scene.antagonismes)


def _any_rotation_leadership(scene: Scene) -> bool:
    return any(c["rotation_leadership"]["detectee"] for c in scene.coalitions)


def _devise_pairs(scene: Scene) -> frozenset[str]:
    pairs: set[str] = set()
    for c in scene.coalitions:
        pairs.update(c["devises_alignees"])
    for a in scene.antagonismes:
        pairs.update(a["devises_en_conflit"])
    return frozenset(pairs)


class BehaviorAnalyzer:
    """Qualifie la dynamique d'une scène dans le temps (FORMAT_COMPORTEMENTS.md)."""

    def __init__(self, db_path: Path | str | None = None, config: dict | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_scene_db(self.db_path)
        init_behavior_db(self.db_path)

        cfg = dict(config) if config else {}
        self.history_lookback = cfg.get("history_lookback", BEHAVIOR_HISTORY_LOOKBACK)
        self.similarity_threshold = cfg.get("similarity_threshold", SIMILARITY_THRESHOLD)
        self.confiance_pliure_severe = cfg.get("confiance_pliure_severe", CONFIANCE_PLIURE_SEVERE)
        self.confiance_bascule_nette = cfg.get("confiance_bascule_nette", CONFIANCE_BASCULE_NETTE)
        self.source_type = cfg.get("source_type", "live")

        memory_dir = cfg.get("memory_dir") or (ROOT_DIR / "memory")
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_temp_path = self.memory_dir / "memory_temp.md"
        self.memory_path = self.memory_dir / "memory.md"

    # ── Connexion DB ──────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Lecture scènes (couche amont) ──────────────────────
    def _resolve_symbol_timeframe(self, conn: sqlite3.Connection, snapshot_id: str) -> tuple[str, str]:
        row = conn.execute(
            "SELECT symbol, timeframe FROM forces_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise BehaviorAnalyzerError(
                f"forces_snapshot introuvable pour la reference {snapshot_id!r}"
            )
        return row["symbol"], row["timeframe"]

    def _load_scene(self, scene_id: str) -> Scene:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
            ).fetchone()
            if row is None:
                raise BehaviorAnalyzerError(f"scene introuvable: {scene_id!r}")
            row = dict(row)
            symbol, timeframe = self._resolve_symbol_timeframe(conn, row["forces_snapshot_ref"])
            return Scene.from_row(row, symbol, timeframe)
        finally:
            conn.close()

    def _load_scene_history(
        self, symbol: str, timeframe: str, upto_timestamp: str, exclude_scene_id: str
    ) -> list[Scene]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT s.* FROM scenes s "
                "JOIN forces_snapshots f ON f.snapshot_id = s.forces_snapshot_ref "
                "WHERE f.symbol = ? AND f.timeframe = ? AND s.timestamp <= ? "
                "AND s.scene_id != ? "
                "ORDER BY s.timestamp DESC LIMIT ?",
                (symbol, timeframe, upto_timestamp, exclude_scene_id, self.history_lookback),
            ).fetchall()
            return [Scene.from_row(dict(r), symbol, timeframe) for r in reversed(rows)]
        finally:
            conn.close()

    # ── Lecture comportements passés (propre production) ──
    def _load_behavior_history(self, symbol: str, timeframe: str, upto_timestamp: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM behaviors WHERE symbol = ? AND timeframe = ? "
                "AND timestamp < ? ORDER BY timestamp DESC LIMIT ?",
                (symbol, timeframe, upto_timestamp, self.history_lookback),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def _load_behaviors_by_qualification(
        self, qualification: str, exclude_behavior_id: str, limit: int = 50
    ) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM behaviors WHERE qualification = ? AND behavior_id != ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (qualification, exclude_behavior_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Analyse principale ──────────────────────────────────
    def analyze_scene(self, scene_id: str) -> dict:
        scene = self._load_scene(scene_id)
        scene_history = self._load_scene_history(
            scene.symbol, scene.timeframe, scene.timestamp, scene.scene_id
        )
        behavior_history = self._load_behavior_history(scene.symbol, scene.timeframe, scene.timestamp)

        comportement = self._qualify_behavior(scene, scene_history, behavior_history)
        transitions = self._detect_transitions(comportement, behavior_history, scene)

        behavior_id = (
            f"beh_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}Z_"
            f"{scene.symbol.lower()}_{scene.timeframe.lower()}_{uuid.uuid4().hex[:6]}"
        )
        window_start = scene_history[-1].timestamp if scene_history else scene.timestamp

        behavior = {
            "behavior_id": behavior_id,
            "schema_version": SCHEMA_VERSION,
            "timestamp": scene.timestamp,
            "scene_id_ref": scene.scene_id,
            "scene_timestamp": scene.timestamp,
            "symbol": scene.symbol,
            "timeframe": scene.timeframe,
            "window_start": window_start,
            "window_end": scene.timestamp,
            "comportement": comportement,
            "transitions": transitions,
            "meta": {
                "produit_par": "behavior-analyzer",
                "version_lexique": SCHEMA_VERSION,
            },
        }
        behavior["comparaison_cas_connus"] = self._compare_to_known_cases(
            behavior_id, comportement, scene
        )

        # ── Anomalie #1 — similarite_score booste confiance_qualification ──
        # Un comportement similaire >= 85% à un cas connu doit augmenter
        # la confiance de qualification : la qualification est corroborée
        # par l'historique, pas seulement par les heuristiques locales.
        # Bonus appliqué APRÈS _compute_confiance pour ne pas perturber
        # les autres bonus déjà calibrés.
        sim_score = behavior["comparaison_cas_connus"].get("similarite_score")
        if sim_score is not None and sim_score >= 0.85:
            bonus_similarite = 15
        elif sim_score is not None and sim_score >= 0.70:
            bonus_similarite = 8
        else:
            bonus_similarite = 0
        if bonus_similarite > 0:
            behavior["comportement"]["confiance_qualification"] = min(
                100,
                int(behavior["comportement"]["confiance_qualification"])
                + bonus_similarite,
            )

        self._write_behavior_to_db(behavior, stale=scene.stale)
        self._write_memory(behavior, statut="hypothese")
        return behavior

    # ── Qualification ───────────────────────────────────────
    def _qualify_behavior(
        self, scene: Scene, scene_history: list[Scene], behavior_history: list[dict]
    ) -> dict:
        qualification = self._determine_qualification(scene, scene_history, behavior_history)
        intensite = self._compute_intensite(scene)

        history_pairs = [
            (b["qualification"], _INTENSITY_RANK.get(b["intensite"], 0)) for b in behavior_history
        ]
        phase = self._determine_phase(qualification, _INTENSITY_RANK.get(intensite, 0), history_pairs)

        streak_len = 1
        for q, _ in reversed(history_pairs):
            if q == qualification:
                streak_len += 1
            else:
                break

        mtf_confirmed = bool(scene.confluences_mtf.get("emboitement_detecte", False))
        confiance = self._compute_confiance(qualification, scene, mtf_confirmed, streak_len)
        description = self._describe(qualification, scene)

        return {
            "qualification": qualification,
            "intensite": intensite,
            "phase": phase,
            "confiance_qualification": confiance,
            "description_courte": description,
        }

    def _determine_qualification(
        self, scene: Scene, scene_history: list[Scene], behavior_history: list[dict]
    ) -> str:
        cin = scene.cinematique_locale
        pliure_detectee = cin["pliure"]["detectee"]

        if _any_rotation_leadership(scene):
            return "rotation_leadership"
        if self._detect_annulation(scene, scene_history):
            return "annulation"
        if pliure_detectee and _any_bascule(scene):
            return "bascule"
        if pliure_detectee and cin["acceleration_deceleration"] == "acceleration":
            return "rupture"
        if self._detect_seconde_bosse(scene, behavior_history):
            return "seconde_bosse"
        if self._detect_preparation_ouverture(scene, behavior_history):
            return "preparation_ouverture_fenetre"
        if self._detect_reequilibrage(scene, scene_history, behavior_history):
            return "reequilibrage"
        if self._detect_tension(scene, scene_history):
            return "tension"
        if self._detect_lutte_forces(scene):
            return "lutte_forces"

        etat = cin["compression_extension"]["etat"]
        if etat == "compression":
            return "contraction"
        if etat == "extension":
            return "extension"
        return "maintien"

    @staticmethod
    def _detect_annulation(scene: Scene, scene_history: list[Scene]) -> bool:
        if not scene_history:
            return False
        prev = scene_history[-1]
        for ant in scene.antagonismes:
            if not ant["bascule_equilibre"]["detectee"]:
                continue
            pair = frozenset(ant["devises_en_conflit"])
            sens = ant["bascule_equilibre"]["sens"]
            for prev_ant in prev.antagonismes:
                if frozenset(prev_ant["devises_en_conflit"]) != pair:
                    continue
                if not prev_ant["bascule_equilibre"]["detectee"]:
                    continue
                prev_sens = prev_ant["bascule_equilibre"]["sens"]
                if prev_sens and sens and prev_sens != sens:
                    return True
        return False

    @staticmethod
    def _detect_tension(scene: Scene, scene_history: list[Scene]) -> bool:
        if len(scene_history) < 1:
            return False
        amp_first = scene_history[0].cinematique_locale["compression_extension"]["intensite"]
        amp_now = scene.cinematique_locale["compression_extension"]["intensite"]
        conflict_first = _max_antagonisme_intensite(scene_history[0])
        conflict_now = _max_antagonisme_intensite(scene)
        return amp_now < amp_first and conflict_now > conflict_first and conflict_now > 0

    @staticmethod
    def _detect_reequilibrage(
        scene: Scene, scene_history: list[Scene], behavior_history: list[dict]
    ) -> bool:
        if not behavior_history or not scene_history:
            return False
        if behavior_history[-1]["qualification"] != "tension":
            return False
        prev_conflict = _max_antagonisme_intensite(scene_history[-1])
        curr_conflict = _max_antagonisme_intensite(scene)
        return curr_conflict < prev_conflict

    @staticmethod
    def _detect_lutte_forces(scene: Scene) -> bool:
        strong = [a for a in scene.antagonismes if a["intensite_conflit"] >= LUTTE_FORCES_INTENSITE_MIN]
        if not strong:
            return False
        return not any(a["bascule_equilibre"]["detectee"] for a in strong)

    @staticmethod
    def _detect_preparation_ouverture(scene: Scene, behavior_history: list[dict]) -> bool:
        if len(behavior_history) < PREPARATION_STREAK_MIN:
            return False
        recent = [b["qualification"] for b in behavior_history[-PREPARATION_STREAK_MIN:]]
        if not all(q == "contraction" for q in recent):
            return False
        cext = scene.cinematique_locale["compression_extension"]
        return cext["etat"] == "extension" and cext["intensite"] < WEAK_EXTENSION_MAX

    @staticmethod
    def _detect_seconde_bosse(scene: Scene, behavior_history: list[dict]) -> bool:
        if len(behavior_history) < 1:
            return False
        last = behavior_history[-1]
        if last.get("phase") != "resolution":
            return False
        if last.get("qualification") not in {"reequilibrage", "maintien"}:
            return False
        current_strength = max(_max_antagonisme_intensite(scene), _max_coalition_intensite(scene))
        return current_strength > 0 and _INTENSITY_RANK.get(
            BehaviorAnalyzer._intensite_from_strength(current_strength), 0
        ) >= _INTENSITY_RANK.get(last.get("intensite", "faible"), 0)

    @staticmethod
    def _intensite_from_strength(strength: float) -> str:
        if strength >= 70:
            return "extreme"
        if strength >= 50:
            return "forte"
        if strength >= 25:
            return "moderee"
        return "faible"

    def _compute_intensite(self, scene: Scene) -> str:
        cin = scene.cinematique_locale
        strength = max(
            _max_antagonisme_intensite(scene),
            _max_coalition_intensite(scene),
            cin["pliure"]["severite"] or 0.0,
            cin["compression_extension"]["intensite"],
        )
        return self._intensite_from_strength(strength)

    @staticmethod
    def _determine_phase(
        qualification: str, intensity_score: int, recent: list[tuple[str, int]]
    ) -> str:
        if not recent or recent[-1][0] != qualification:
            return "initiation"

        streak = [intensity_score]
        for q, score in reversed(recent):
            if q == qualification:
                streak.insert(0, score)
            else:
                break

        if len(streak) <= 2:
            return "developpement"
        if streak[-1] >= max(streak[:-1]):
            return "culmination"
        return "resolution"

    def _compute_confiance(
        self, qualification: str, scene: Scene, mtf_confirmed: bool, streak_len: int
    ) -> int:
        base = 40
        pliure = scene.cinematique_locale["pliure"]
        if pliure["detectee"] and (pliure["severite"] or 0.0) >= PLIURE_SEVERE_MIN:
            base = max(base, self.confiance_pliure_severe)
        if qualification == "bascule":
            base = max(base, self.confiance_bascule_nette)
        if mtf_confirmed:
            base += 10
        if streak_len > 1:
            base += 5
        return min(100, base)

    @staticmethod
    def _describe(qualification: str, scene: Scene) -> str:
        label = QUALIFICATION_LABELS[qualification]
        structure = scene.zone.get("structure", "zone non caractérisée")
        return (
            f"{label} observée sur {scene.symbol} {scene.timeframe} — {structure}."
        )

    # ── Transitions ──────────────────────────────────────────
    def _detect_transitions(
        self, comportement: dict, behavior_history: list[dict], scene: Scene
    ) -> dict:
        if not behavior_history:
            return {
                "comportement_precedent": None,
                "point_de_rupture": {"detecte": False, "timestamp": None, "declencheur": None},
                "sens_transition": None,
            }

        prev = behavior_history[-1]
        comportement_precedent = prev["qualification"]
        qualification_changed = comportement_precedent != comportement["qualification"]

        point_de_rupture = {"detecte": False, "timestamp": None, "declencheur": None}
        if qualification_changed:
            point_de_rupture = {
                "detecte": True,
                "timestamp": scene.timestamp,
                "declencheur": self._describe_trigger(scene),
            }

        pair = frozenset({comportement_precedent, comportement["qualification"]})
        if pair in OPPOSITE_QUALIFICATIONS:
            sens_transition = "inversion"
        else:
            intensity_delta = _INTENSITY_RANK[comportement["intensite"]] - _INTENSITY_RANK.get(
                prev["intensite"], 0
            )
            if intensity_delta > 0:
                sens_transition = "escalade"
            elif intensity_delta < 0:
                sens_transition = "desescalade"
            else:
                phase_delta = _PHASE_WEIGHT[comportement["phase"]] - _PHASE_WEIGHT.get(
                    prev.get("phase", "initiation"), 0
                )
                if phase_delta > 0:
                    sens_transition = "escalade"
                elif phase_delta < 0:
                    sens_transition = "desescalade"
                else:
                    sens_transition = "neutre"

        return {
            "comportement_precedent": comportement_precedent,
            "point_de_rupture": point_de_rupture,
            "sens_transition": sens_transition,
        }

    @staticmethod
    def _describe_trigger(scene: Scene) -> str:
        cin = scene.cinematique_locale
        if cin["pliure"]["detectee"]:
            return (
                f"pliure de cinématique (sévérité {cin['pliure']['severite']}) "
                f"avec {cin['acceleration_deceleration']}"
            )
        bascule_ant = next(
            (a for a in scene.antagonismes if a["bascule_equilibre"]["detectee"]), None
        )
        if bascule_ant:
            pair = "/".join(bascule_ant["devises_en_conflit"])
            return f"franchissement de zone avec bascule d'équilibre {pair}"
        return "changement de qualification sans déclencheur cinématique marqué"

    # ── Comparaison aux cas connus (replay) ───────────────────
    def _compare_to_known_cases(self, behavior_id: str, comportement: dict, scene: Scene) -> dict:
        empty = {
            "similarite_score": None,
            "cas_references": [],
            "singularites_locales": [],
            "variante_de_comportement_connu": {
                "est_variante": False,
                "comportement_reference": None,
                "ecarts": [],
            },
        }

        candidates = self._load_behaviors_by_qualification(comportement["qualification"], behavior_id)
        if not candidates:
            return empty

        current_pairs = _devise_pairs(scene)
        scored: list[tuple[float, dict, Scene]] = []
        for cand in candidates:
            try:
                cand_scene = self._load_scene(cand["scene_id_ref"])
            except BehaviorAnalyzerError:
                continue
            score = self._similarity(scene, current_pairs, comportement, cand, cand_scene)
            scored.append((score, cand, cand_scene))

        if not scored:
            return empty

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:3]
        best_score = top[0][0]

        cas_references = [
            {"case_id": cand["behavior_id"], "similarite": round(score, 4)} for score, cand, _ in top
        ]
        singularites = self._detect_singularities(scene, top)

        est_variante = self.similarity_threshold <= best_score < 1.0
        variante = {
            "est_variante": est_variante,
            "comportement_reference": comportement["qualification"] if est_variante else None,
            "ecarts": singularites if est_variante else [],
        }

        return {
            "similarite_score": round(best_score, 4),
            "cas_references": cas_references,
            "singularites_locales": singularites,
            "variante_de_comportement_connu": variante,
        }

    @staticmethod
    def _dominant_coalition_set(scene: Scene) -> frozenset[str] | None:
        """Renvoie les devises_alignees de la coalition dominante (max
        intensite_alignement). Renvoie None si la scène n'a aucune
        coalition — sert à ``_similarity`` pour la dimension
        coalition_composition_sim (Anomalie #2)."""
        if not scene.coalitions:
            return None
        dominant = max(
            scene.coalitions,
            key=lambda c: float(c.get("intensite_alignement", 0.0) or 0.0),
        )
        devises = dominant.get("devises_alignees") or []
        return frozenset(devises) if devises else None

    @staticmethod
    def _similarity(
        scene: Scene,
        current_pairs: frozenset[str],
        comportement: dict,
        cand_row: dict,
        cand_scene: Scene,
    ) -> float:
        cand_pairs = _devise_pairs(cand_scene)
        union = current_pairs | cand_pairs
        jaccard = len(current_pairs & cand_pairs) / len(union) if union else 1.0

        same_tf = 1.0 if cand_row["timeframe"] == scene.timeframe else 0.0
        same_phase = 1.0 if cand_row["phase"] == comportement["phase"] else 0.0

        angle_now = scene.cinematique_locale["angle"]
        pente_now = scene.cinematique_locale["pente"]
        angle_cand = cand_scene.cinematique_locale["angle"]
        pente_cand = cand_scene.cinematique_locale["pente"]
        angle_sim = 1.0 - min(1.0, abs(angle_now - angle_cand) / 180.0)
        pente_scale = abs(pente_now) + abs(pente_cand) + 1e-6
        pente_sim = 1.0 - min(1.0, abs(pente_now - pente_cand) / pente_scale)
        cinematique_sim = (angle_sim + pente_sim) / 2.0

        # ── Anomalie #2 — coalition_composition_sim ──────────────
        # Jaccard sur les devises de la coalition dominante de chaque
        # scène. Fallback 0.5 si l'une des scènes n'a pas de coalition
        # (incertitude neutre, ne tire ni vers + ni vers -).
        dom_now = BehaviorAnalyzer._dominant_coalition_set(scene)
        dom_cand = BehaviorAnalyzer._dominant_coalition_set(cand_scene)
        if dom_now is None or dom_cand is None:
            coalition_sim = 0.5
        else:
            union_c = dom_now | dom_cand
            coalition_sim = (
                len(dom_now & dom_cand) / len(union_c) if union_c else 1.0
            )

        # Pondération (Anomalie #2) :
        # 0.30 jaccard + 0.20 same_tf + 0.20 same_phase
        # 0.15 cinematique + 0.15 coalition_composition
        score = (
            0.30 * jaccard
            + 0.20 * same_tf
            + 0.20 * same_phase
            + 0.15 * cinematique_sim
            + 0.15 * coalition_sim
        )
        return round(score, 6)

    @staticmethod
    def _detect_singularities(scene: Scene, top: list[tuple[float, dict, "Scene"]]) -> list[str]:
        notes: list[str] = []
        severites = [
            cand_scene.cinematique_locale["pliure"]["severite"]
            for _, _, cand_scene in top
            if cand_scene.cinematique_locale["pliure"]["severite"] is not None
        ]
        current_severite = scene.cinematique_locale["pliure"]["severite"]
        if severites and current_severite is not None:
            med = median(severites)
            if med > 0:
                delta_pct = (current_severite - med) / med * 100
                if abs(delta_pct) >= 30:
                    sens = "supérieure" if delta_pct > 0 else "inférieure"
                    notes.append(
                        f"sévérité de pliure {sens} de {abs(round(delta_pct))}% "
                        "à la médiane des cas comparés"
                    )
        return notes

    # ── Écriture DB ─────────────────────────────────────────
    def _write_behavior_to_db(self, behavior: dict, stale: bool) -> None:
        conn = get_connection(self.db_path)
        try:
            comp = behavior["comportement"]
            trans = behavior["transitions"]
            comp_cas = behavior["comparaison_cas_connus"]
            variante = comp_cas["variante_de_comportement_connu"]
            point_rupture = trans["point_de_rupture"]

            values = [
                behavior["behavior_id"],
                behavior["schema_version"],
                behavior["timestamp"],
                behavior["scene_id_ref"],
                behavior["scene_timestamp"],
                behavior["symbol"],
                behavior["timeframe"],
                behavior["window_start"],
                behavior["window_end"],
                comp["qualification"],
                comp["intensite"],
                comp["phase"],
                comp["confiance_qualification"],
                comp["description_courte"],
                trans["comportement_precedent"],
                point_rupture["detecte"],
                point_rupture["timestamp"],
                point_rupture["declencheur"],
                trans["sens_transition"],
                comp_cas["similarite_score"],
                json.dumps(comp_cas["cas_references"]),
                json.dumps(comp_cas["singularites_locales"]),
                variante["est_variante"],
                variante["comportement_reference"],
                json.dumps(variante["ecarts"]),
                stale,
                self.source_type,
                datetime.now(timezone.utc).isoformat(),
            ]
            col_names = ", ".join(BEHAVIOR_COLUMNS)
            placeholders = ", ".join(["?"] * len(BEHAVIOR_COLUMNS))
            conn.execute(
                f"INSERT OR IGNORE INTO behaviors ({col_names}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    # ── Écriture mémoire ────────────────────────────────────
    def _build_memory_entries(self, behavior: dict, statut: str) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        resolved_at = now if statut != "hypothese" else None
        reference = {"id": behavior["behavior_id"], "timestamp": behavior["scene_timestamp"]}

        def make_entry(entry_type: str, contenu: dict) -> dict:
            return {
                "schema_version": SCHEMA_VERSION,
                "entry_id": f"mem-{uuid.uuid4().hex[:12]}",
                "type": entry_type,
                "statut": statut,
                "couche_origine": "comportements",
                "created_at": now,
                "resolved_at": resolved_at,
                "reference": reference,
                "contenu": contenu,
                "justification": "" if statut == "hypothese" else "confrontation validee",
            }

        return [
            make_entry("comportement", behavior["comportement"]),
            make_entry("transition_comportement", behavior["transitions"]),
            make_entry("comparaison_cas_connus", behavior["comparaison_cas_connus"]),
        ]

    def _write_memory(self, behavior: dict, statut: str = "hypothese") -> None:
        entries = self._build_memory_entries(behavior, statut)
        target = self.memory_temp_path if statut == "hypothese" else self.memory_path

        with open(target, "a", encoding="utf-8") as f:
            f.write(
                f"\n### Comportement {behavior['behavior_id']} "
                f"— {datetime.now(timezone.utc).isoformat()}\n\n"
            )
            for entry in entries:
                f.write("```json\n")
                f.write(json.dumps(entry, ensure_ascii=False, indent=2))
                f.write("\n```\n\n")
