"""SceneBuilder — construit une scène à partir d'un snapshot de forces.

Aligné sur docs/architecture/formats/FORMAT_SCENES.md. Consomme
uniquement la sortie de la couche Forces (table forces_snapshots) — ne
duplique jamais les données de forces, les référence via
`forces_snapshot_ref`. Ne contient aucune logique de trading, aucune
qualification de comportement ni de fenêtre (rôle de la Phase 4).

Chaque ligne de forces_snapshots porte déjà les 8 valeurs de force
(force_usd..force_nzd) pour un timeframe donné à un instant donné (une
sonde EA par timeframe calcule le panier des 8 devises simultanément).
La couche Scènes calcule donc sa propre lecture de direction par devise
(comparaison au snapshot précédent du même timeframe, ou position par
rapport à la référence neutre 50.0 en l'absence d'historique) — une
lecture indépendante de celle de la couche Forces, pas une reprise.
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from core.v9.config import (
    ANTAGONISM_THRESHOLD,
    COALITION_THRESHOLD,
    COMPRESSION_RATIO,
    COMPRESSION_WINDOW_BARS,
    DB_PATH,
    DEVISES,
    EXTENSION_RATIO,
    MTF_LOOKBACK,
    PLIURE_THRESHOLD,
    ROOT_DIR,
    SCHEMA_VERSION,
    TIMEFRAME_TICK,
    TIMEFRAMES_CANDLE,
)
from core.v9.db_schema import get_connection
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db

# Timeframes du plus large (HTF) au plus fin (LTF) — ordre natif utilisé
# pour la construction des cascades temporelles MTF.
TF_ORDER = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]
ALL_TIMEFRAMES = TIMEFRAMES_CANDLE + TIMEFRAME_TICK

# Référence neutre utilisée pour inférer une direction par devise en
# l'absence de tout snapshot précédent pour ce timeframe.
NEUTRAL_REFERENCE = 50.0


class SceneBuilderError(ValueError):
    """Erreur de construction de scène (snapshot introuvable, etc.)."""


@dataclass
class TfSnapshot:
    """Lecture préparée d'un timeframe pour les confluences MTF."""

    row: dict
    coalitions: list[dict] = field(default_factory=list)
    antagonismes: list[dict] = field(default_factory=list)


class SceneBuilder:
    """Construit des scènes (FORMAT_SCENES.md) à partir de forces_snapshots."""

    def __init__(self, db_path: Path | str | None = None, config: dict | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_scene_db(self.db_path)

        cfg = dict(config) if config else {}
        self.coalition_threshold = cfg.get("coalition_threshold", COALITION_THRESHOLD)
        self.antagonism_threshold = cfg.get("antagonism_threshold", ANTAGONISM_THRESHOLD)
        self.pliure_threshold = cfg.get("pliure_threshold", PLIURE_THRESHOLD)
        self.mtf_lookback = cfg.get("mtf_lookback", MTF_LOOKBACK)
        self.compression_window = cfg.get("compression_window_bars", COMPRESSION_WINDOW_BARS)
        self.extension_ratio = cfg.get("extension_ratio", EXTENSION_RATIO)
        self.compression_ratio = cfg.get("compression_ratio", COMPRESSION_RATIO)
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

    # ── Lecture forces_snapshots ──────────────────────────
    def _load_row(self, snapshot_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _load_history(self, timeframe: str, upto_timestamp: str, limit: int) -> list[dict]:
        """N derniers snapshots non périmés (ou égaux) pour ce timeframe, ordre ascendant."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM forces_snapshots "
                "WHERE timeframe = ? AND timestamp <= ? AND stale = 0 "
                "ORDER BY timestamp DESC LIMIT ?",
                (timeframe, upto_timestamp, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def _load_latest_for_tf(self, timeframe: str, upto_timestamp: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM forces_snapshots "
                "WHERE timeframe = ? AND timestamp <= ? AND stale = 0 "
                "ORDER BY timestamp DESC LIMIT 1",
                (timeframe, upto_timestamp),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def _extract_forces(row: dict) -> dict[str, float]:
        return {d: float(row[f"force_{d.lower()}"]) for d in DEVISES}

    def _compute_directions(
        self, forces_now: dict[str, float], prev_forces: dict[str, float] | None
    ) -> dict[str, str]:
        directions: dict[str, str] = {}
        for devise in DEVISES:
            if prev_forces is not None:
                delta = forces_now[devise] - prev_forces[devise]
                if delta > 0:
                    directions[devise] = "haussiere"
                elif delta < 0:
                    directions[devise] = "baissiere"
                else:
                    directions[devise] = "neutre"
            else:
                value = forces_now[devise]
                if value > NEUTRAL_REFERENCE:
                    directions[devise] = "haussiere"
                elif value < NEUTRAL_REFERENCE:
                    directions[devise] = "baissiere"
                else:
                    directions[devise] = "neutre"
        return directions

    # ── Coalitions ─────────────────────────────────────────
    def _cluster_by_direction(
        self, forces: dict[str, float], directions: dict[str, str]
    ) -> list[list[str]]:
        clusters: list[list[str]] = []
        for direction in ("haussiere", "baissiere"):
            members = sorted(
                (d for d in DEVISES if directions.get(d) == direction),
                key=lambda d: forces[d],
            )
            if not members:
                continue
            current = [members[0]]
            for devise in members[1:]:
                if forces[devise] - forces[current[-1]] <= self.coalition_threshold:
                    current.append(devise)
                else:
                    if len(current) >= 2:
                        clusters.append(current)
                    current = [devise]
            if len(current) >= 2:
                clusters.append(current)
        return clusters

    def _detect_coalitions(
        self,
        forces: dict[str, float],
        directions: dict[str, str],
        prev_forces: dict[str, float] | None = None,
        prev_directions: dict[str, str] | None = None,
    ) -> list[dict]:
        clusters = self._cluster_by_direction(forces, directions)
        prev_clusters: list[list[str]] = []
        if prev_forces is not None and prev_directions is not None:
            prev_clusters = self._cluster_by_direction(prev_forces, prev_directions)

        coalitions = []
        for cluster in clusters:
            cluster_set = set(cluster)
            leader = max(cluster, key=lambda d: forces[d])
            intensite_alignement = round(
                sum(forces[d] for d in cluster) / len(cluster), 4
            )

            rotation_detectee = False
            ancien_leader = None
            nouveau_leader = None
            best_match = max(
                prev_clusters,
                key=lambda pc: len(cluster_set & set(pc)),
                default=None,
            )
            if best_match is not None and (cluster_set & set(best_match)):
                prev_leader = max(best_match, key=lambda d: prev_forces[d])
                if prev_leader != leader:
                    rotation_detectee = True
                    ancien_leader = prev_leader
                    nouveau_leader = leader

            coalitions.append(
                {
                    "devises_alignees": cluster,
                    "intensite_alignement": intensite_alignement,
                    "leader": leader,
                    "rotation_leadership": {
                        "detectee": rotation_detectee,
                        "ancien_leader": ancien_leader,
                        "nouveau_leader": nouveau_leader,
                    },
                }
            )

        coalitions.sort(key=lambda c: tuple(sorted(c["devises_alignees"])))
        return coalitions

    # ── Antagonismes ───────────────────────────────────────
    def _detect_antagonisms(
        self,
        forces: dict[str, float],
        directions: dict[str, str],
        prev_forces: dict[str, float] | None = None,
        prev_directions: dict[str, str] | None = None,
    ) -> list[dict]:
        antagonismes = []
        for a, b in combinations(sorted(DEVISES), 2):
            dir_a, dir_b = directions.get(a), directions.get(b)
            opposite = {dir_a, dir_b} == {"haussiere", "baissiere"}
            diff = abs(forces[a] - forces[b])

            crossing = False
            if prev_forces is not None:
                prev_diff = prev_forces[a] - prev_forces[b]
                curr_diff = forces[a] - forces[b]
                crossing = (
                    prev_diff != 0
                    and curr_diff != 0
                    and (prev_diff > 0) != (curr_diff > 0)
                )

            if not ((opposite and diff >= self.antagonism_threshold) or crossing):
                continue

            sens = None
            if crossing:
                sens = a if forces[a] > forces[b] else b

            antagonismes.append(
                {
                    "devises_en_conflit": [a, b],
                    "intensite_conflit": round(diff, 4),
                    "bascule_equilibre": {"detectee": crossing, "sens": sens},
                }
            )

        return antagonismes

    # ── Cinématique locale ─────────────────────────────────
    def _compute_cinematics(self, forces: dict[str, float], history: list[dict]) -> dict:
        # Cinématique exprimée par pas de snapshot (delta_time = 1 étape
        # entre deux lectures consécutives du même timeframe), pas en
        # secondes réelles : ceci garde pente/courbure dans la même
        # échelle de force brute que les seuils de config.py
        # (PLIURE_THRESHOLD, COALITION_THRESHOLD, ANTAGONISM_THRESHOLD).
        points = []
        for row in history:
            f = self._extract_forces(row)
            values = list(f.values())
            mean_val = sum(values) / len(values)
            amplitude = max(values) - min(values)
            points.append((mean_val, amplitude))

        n = len(points)
        mean_now, amp_now = points[-1]

        pente = 0.0
        angle = 0.0
        if n >= 2:
            mean_prev, amp_prev = points[-2]
            pente = mean_now - mean_prev
            angle = math.degrees(math.atan2(amp_now - amp_prev, mean_now - mean_prev))

        courbure = 0.0
        pente_prev = None
        if n >= 3:
            mean_prev, _ = points[-2]
            mean_prev2, _ = points[-3]
            pente_prev = mean_prev - mean_prev2
            courbure = pente - pente_prev

        pliure_detectee = False
        pliure_severite = None
        if pente_prev is not None:
            diff = abs(pente - pente_prev)
            if diff > self.pliure_threshold:
                pliure_detectee = True
                pliure_severite = round(diff, 4)

        if courbure > 0:
            acceleration_deceleration = "acceleration"
        elif courbure < 0:
            acceleration_deceleration = "deceleration"
        else:
            acceleration_deceleration = "stable"

        rotation_detectee = False
        rotation_sens = None
        if n >= 2:
            forces_prev = self._extract_forces(history[-2])
            rank_now = tuple(sorted(DEVISES, key=lambda d: forces[d], reverse=True))
            rank_prev = tuple(sorted(DEVISES, key=lambda d: forces_prev[d], reverse=True))
            if rank_now != rank_prev:
                rotation_detectee = True
                if rank_now[0] != rank_prev[0]:
                    rotation_sens = f"{rank_prev[0]}→{rank_now[0]}"
                else:
                    rotation_sens = "reordonnancement sans changement de leader"

        window = [p[1] for p in points[:-1]][-self.compression_window:]
        avg_amplitude = sum(window) / len(window) if window else amp_now
        if avg_amplitude > 0 and amp_now > avg_amplitude * self.extension_ratio:
            etat = "extension"
        elif avg_amplitude > 0 and amp_now < avg_amplitude * self.compression_ratio:
            etat = "compression"
        else:
            etat = "neutre"

        return {
            "angle": round(angle, 4),
            "courbure": round(courbure, 6),
            "pente": round(pente, 6),
            "pliure": {"detectee": pliure_detectee, "severite": pliure_severite},
            "acceleration_deceleration": acceleration_deceleration,
            "rotation_force": {"detectee": rotation_detectee, "sens": rotation_sens},
            "compression_extension": {
                "etat": etat,
                "intensite": round(abs(amp_now - avg_amplitude), 4),
            },
        }

    # ── Confluences MTF ────────────────────────────────────
    def _load_snapshots_by_tf(
        self, primary_tf: str, primary_row: dict, primary_coalitions: list[dict],
        primary_antagonismes: list[dict]
    ) -> dict[str, TfSnapshot]:
        result = {
            primary_tf: TfSnapshot(
                row=primary_row, coalitions=primary_coalitions, antagonismes=primary_antagonismes
            )
        }
        primary_ts = primary_row["timestamp"]

        for tf in ALL_TIMEFRAMES:
            if tf == primary_tf:
                continue
            history = self._load_history(tf, primary_ts, max(self.mtf_lookback, 2))
            if not history:
                continue

            row = history[-1]
            forces_now = self._extract_forces(row)
            prev_forces = self._extract_forces(history[-2]) if len(history) >= 2 else None
            prev_prev_forces = self._extract_forces(history[-3]) if len(history) >= 3 else None

            directions_now = self._compute_directions(forces_now, prev_forces)
            directions_prev = (
                self._compute_directions(prev_forces, prev_prev_forces)
                if prev_forces is not None
                else {}
            )

            coalitions = self._detect_coalitions(
                forces_now, directions_now, prev_forces, directions_prev
            )
            antagonismes = self._detect_antagonisms(
                forces_now, directions_now, prev_forces, directions_prev
            )
            result[tf] = TfSnapshot(row=row, coalitions=coalitions, antagonismes=antagonismes)

        return result

    def _detect_mtf_confluences(self, snapshots_by_tf: dict[str, TfSnapshot]) -> dict:
        present = [tf for tf in TF_ORDER if tf in snapshots_by_tf]
        cascades: list[dict] = []
        signatures: list[str] = []

        for i in range(len(present) - 1):
            htf, ltf = present[i], present[i + 1]
            htf_data, ltf_data = snapshots_by_tf[htf], snapshots_by_tf[ltf]

            for coalition in htf_data.coalitions:
                htf_set = set(coalition["devises_alignees"])
                match = next(
                    (
                        c
                        for c in ltf_data.coalitions
                        if htf_set & set(c["devises_alignees"])
                    ),
                    None,
                )
                label = "/".join(coalition["devises_alignees"])
                if match is not None:
                    cascades.append(
                        {
                            "de_timeframe": htf,
                            "vers_timeframe": ltf,
                            "description": (
                                f"la coalition {label} amorcee en {htf} "
                                f"se retrouve en {ltf}"
                            ),
                        }
                    )
                    signatures.append(f"alignement {label} confirme de {htf} vers {ltf}")
                else:
                    signatures.append(f"coalition {label} isolee au timeframe {htf}")

                if coalition["rotation_leadership"]["detectee"]:
                    signatures.append(
                        f"rotation de leadership {label} isolee au timeframe {htf}"
                    )

            for antagonisme in htf_data.antagonismes:
                pair = antagonisme["devises_en_conflit"]
                pair_set = set(pair)
                label = "/".join(pair)
                match = next(
                    (
                        a
                        for a in ltf_data.antagonismes
                        if pair_set == set(a["devises_en_conflit"])
                    ),
                    None,
                )
                if match is not None:
                    cascades.append(
                        {
                            "de_timeframe": htf,
                            "vers_timeframe": ltf,
                            "description": (
                                f"confirmation de la bascule d'equilibre {label} sur {ltf}"
                            ),
                        }
                    )
                    signatures.append(f"antagonisme {label} confirme de {htf} vers {ltf}")

        return {
            "emboitement_detecte": len(cascades) > 0,
            "cascades_temporelles": cascades,
            "signatures_coherence": signatures,
        }

    # ── Contexte temporel ──────────────────────────────────
    @staticmethod
    def _identify_context(timestamp: str) -> dict:
        ts = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

        def in_range(start: float, end: float) -> bool:
            if start <= end:
                return start <= hour < end
            return hour >= start or hour < end

        def position(start: float, end: float) -> str:
            duration = (end - start) % 24 or 24.0
            elapsed = (hour - start) % 24
            fraction = elapsed / duration
            if fraction < 1 / 3:
                return "ouverture de session"
            if fraction < 2 / 3:
                return "mi-session"
            return "cloture de session"

        if in_range(12.0, 16.0):
            session, bounds = "chevauchement", (12.0, 16.0)
        elif in_range(7.0, 16.0):
            session, bounds = "Londres", (7.0, 16.0)
        elif in_range(12.0, 21.0):
            session, bounds = "New York", (12.0, 21.0)
        elif in_range(0.0, 9.0):
            session, bounds = "Tokyo", (0.0, 9.0)
        else:
            session, bounds = "Sydney", (21.0, 6.0)

        return {"session": session, "fenetre": position(*bounds)}

    # ── Zone ────────────────────────────────────────────────
    @staticmethod
    def _build_zone(row: dict, cinematique: dict) -> dict:
        niveau_reference = row.get("close")
        if niveau_reference is None:
            niveau_reference = row.get("mid")

        etat = cinematique["compression_extension"]["etat"]
        if etat == "extension":
            structure = "zone d'extension autour du niveau de cloture"
        elif etat == "compression":
            structure = "zone de compression"
        else:
            structure = "zone neutre"

        timeframe = row["timeframe"]
        if timeframe in ("D1", "H4"):
            niveau = "majeure"
        elif timeframe in ("H1", "M30"):
            niveau = "intermediaire"
        else:
            niveau = "mineure"

        return {
            "prix": {
                "niveau_reference": niveau_reference,
                "borne_basse": row.get("low"),
                "borne_haute": row.get("high"),
            },
            "structure": structure,
            "niveau": niveau,
        }

    # ── Construction complète ──────────────────────────────
    def build_scene(self, snapshot_id: str) -> dict:
        primary_row = self._load_row(snapshot_id)
        if primary_row is None:
            raise SceneBuilderError(f"snapshot introuvable: {snapshot_id!r}")

        primary_tf = primary_row["timeframe"]
        primary_ts = primary_row["timestamp"]

        history = self._load_history(primary_tf, primary_ts, self.mtf_lookback)
        # Le snapshot demandé peut être lui-même stale ou absent de
        # l'historique non périmé (STALE_GATE) : il reste néanmoins le
        # point courant de la scène — le champ `stale` de la ligne DB le
        # rendra visible en aval, jamais masqué.
        history = [h for h in history if h["snapshot_id"] != snapshot_id]
        history.append(primary_row)
        history = history[-self.mtf_lookback :]

        forces_now = self._extract_forces(primary_row)
        prev_row = history[-2] if len(history) >= 2 else None
        prev_prev_row = history[-3] if len(history) >= 3 else None
        prev_forces = self._extract_forces(prev_row) if prev_row else None
        prev_prev_forces = self._extract_forces(prev_prev_row) if prev_prev_row else None

        directions_now = self._compute_directions(forces_now, prev_forces)
        directions_prev = (
            self._compute_directions(prev_forces, prev_prev_forces)
            if prev_forces is not None
            else {}
        )

        coalitions = self._detect_coalitions(
            forces_now, directions_now, prev_forces, directions_prev
        )
        antagonismes = self._detect_antagonisms(
            forces_now, directions_now, prev_forces, directions_prev
        )
        cinematique = self._compute_cinematics(forces_now, history)

        snapshots_by_tf = self._load_snapshots_by_tf(
            primary_tf, primary_row, coalitions, antagonismes
        )
        confluences = self._detect_mtf_confluences(snapshots_by_tf)
        contexte = self._identify_context(primary_ts)
        zone = self._build_zone(primary_row, cinematique)

        timeframes_concernes = [tf for tf in TF_ORDER if tf in snapshots_by_tf]

        dt = datetime.fromisoformat(primary_ts.replace("Z", "+00:00"))
        scene_id = f"scene-{dt.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        return {
            "schema_version": SCHEMA_VERSION,
            "scene_id": scene_id,
            "timestamp": primary_ts,
            "timeframes_concernes": timeframes_concernes,
            "forces_snapshot_ref": {
                "snapshot_id": primary_row["snapshot_id"],
                "timestamp": primary_ts,
            },
            "zone": zone,
            "coalitions": coalitions,
            "antagonismes": antagonismes,
            "cinematique_locale": cinematique,
            "confluences_mtf": confluences,
            "contexte_temporel": contexte,
        }

    # ── Écriture DB ─────────────────────────────────────────
    def _write_scene_to_db(self, scene: dict) -> None:
        conn = get_connection(self.db_path)
        try:
            ref = scene["forces_snapshot_ref"]
            source = conn.execute(
                "SELECT stale FROM forces_snapshots WHERE snapshot_id = ?",
                (ref["snapshot_id"],),
            ).fetchone()
            stale = bool(source[0]) if source else False

            values = [
                scene["scene_id"],
                scene["schema_version"],
                scene["timestamp"],
                json.dumps(scene["timeframes_concernes"]),
                ref["snapshot_id"],
                ref["timestamp"],
                json.dumps(scene["zone"]),
                json.dumps(scene["coalitions"]),
                json.dumps(scene["antagonismes"]),
                json.dumps(scene["cinematique_locale"]),
                json.dumps(scene["confluences_mtf"]),
                json.dumps(scene["contexte_temporel"]),
                stale,
                self.source_type,
                datetime.now(timezone.utc).isoformat(),
            ]
            col_names = ", ".join(SCENES_COLUMNS)
            placeholders = ", ".join(["?"] * len(SCENES_COLUMNS))
            conn.execute(
                f"INSERT OR IGNORE INTO scenes ({col_names}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    # ── Écriture mémoire ────────────────────────────────────
    def _build_memory_entries(self, scene: dict, statut: str) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        resolved_at = now if statut != "hypothese" else None
        reference = {"id": scene["scene_id"], "timestamp": scene["timestamp"]}

        def make_entry(entry_type: str, contenu: dict) -> dict:
            return {
                "schema_version": SCHEMA_VERSION,
                "entry_id": f"mem-{uuid.uuid4().hex[:12]}",
                "type": entry_type,
                "statut": statut,
                "couche_origine": "scenes",
                "created_at": now,
                "resolved_at": resolved_at,
                "reference": reference,
                "contenu": contenu,
                "justification": "" if statut == "hypothese" else "confrontation validee",
            }

        entries = [
            make_entry(
                "scene",
                {
                    "forces_snapshot_ref": scene["forces_snapshot_ref"],
                    "timeframes_concernes": scene["timeframes_concernes"],
                },
            )
        ]
        for coalition in scene["coalitions"]:
            entries.append(make_entry("hypothese_coalition", coalition))
        for antagonisme in scene["antagonismes"]:
            entries.append(make_entry("hypothese_antagonisme", antagonisme))
        for signature in scene["confluences_mtf"]["signatures_coherence"]:
            entries.append(make_entry("signature_coherence", {"libelle": signature}))

        return entries

    def _write_memory(self, scene: dict, statut: str = "hypothese") -> None:
        entries = self._build_memory_entries(scene, statut)
        target = self.memory_temp_path if statut == "hypothese" else self.memory_path

        with open(target, "a", encoding="utf-8") as f:
            f.write(
                f"\n### Scene {scene['scene_id']} "
                f"— {datetime.now(timezone.utc).isoformat()}\n\n"
            )
            for entry in entries:
                f.write("```json\n")
                f.write(json.dumps(entry, ensure_ascii=False, indent=2))
                f.write("\n```\n\n")
