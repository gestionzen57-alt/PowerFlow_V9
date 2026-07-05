"""WindowGate — couche Fenêtres (4e couche cognitive PowerFlow V9).

Chaîne cognitive officielle :
    Forces → Scènes → Comportements → [FENÊTRES] → Exploitabilité

La couche Fenêtres consomme UNIQUEMENT la sortie de la couche Comportements
(docs/architecture/formats/FORMAT_COMPORTEMENTS.md). Elle ne lit jamais les
forces ni les scènes directement (charte cognitive V9, règle "aucune couche
aval ne doit polluer ou court-circuiter une couche amont"). Elle qualifie le
MOMENT où une dynamique comportementale devient surveillable, potentiellement
exploitable, fragile ou invalide — elle ne prédit jamais et ne statue jamais
sur l'exploitabilité (couche aval suivante).

Aucune logique de trading ou d'exécution d'ordre.

Note de portage — Phase 4 (Comportements) non fusionnée au moment de cette
implémentation : `core/v9/behavior_analyzer.py` et `core/v9/behavior_db.py`
n'existent pas encore sur cette branche. Ce module lit donc une table
`behaviors` minimale (`_ensure_behaviors_table`), strict reflet plat de
`FORMAT_COMPORTEMENTS.md`, comme point d'entrée temporaire. Trois champs
auxiliaires (`confluence_mtf_confirmee`, `rejet_repulsion_detecte`, `stale`)
sont portés par cette table bien qu'absents du format v1.0 : ce sont des
signaux que la couche Comportements est censée transmettre en aval (calculés
en amont à partir de la scène source), nécessaires aux règles de bonus/malus
et de type "rebond" explicitement demandées pour la couche Fenêtres. Ils ne
sont jamais lus depuis une scène ou une force par ce module — uniquement
portés par l'objet Comportement reçu. Quand `core/v9/behavior_db.py` sera
fusionné, `_load_behavior`/`_load_behavior_history` devront être adaptés à
son schéma réel ; le reste de la logique (statut, type, fragilité,
invalidation, cycle de vie) reste inchangé.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9 import config as default_config
from core.v9.window_db import WINDOWS_COLUMNS
from core.v9.window_db import get_connection as get_windows_connection
from core.v9.window_db import init_window_db

SCHEMA_VERSION = "1.0"

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MEMORY_TEMP_PATH = ROOT_DIR / "memory" / "memory_temp.md"

# Qualifications reconnues par FORMAT_COMPORTEMENTS.md (LEXICON_V9).
BEHAVIOR_QUALIFICATIONS = {
    "maintien",
    "bascule",
    "lutte_forces",
    "contraction",
    "extension",
    "tension",
    "rupture",
    "reequilibrage",
    "annulation",
    "preparation_ouverture_fenetre",
    "seconde_bosse",
    "rotation_leadership",
}

WINDOW_STATUTS = {
    "absente",
    "en_preparation",
    "ouverte",
    "fragile",
    "invalidee",
    "ambigue",
}

# ── Shim table "behaviors" ────────────────────────────────
# Reflet plat de FORMAT_COMPORTEMENTS.md + 3 champs auxiliaires (voir
# docstring module). À retirer / remplacer par core.v9.behavior_db une fois
# la Phase 4 fusionnée.
BEHAVIORS_SHIM_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS behaviors (
    behavior_id TEXT PRIMARY KEY,
    schema_version TEXT,
    timestamp TEXT,
    scene_id_ref TEXT,
    scene_timestamp TEXT,
    symbol TEXT,
    timeframe TEXT,
    window_start TEXT,
    window_end TEXT,
    qualification TEXT,
    intensite TEXT,
    phase TEXT,
    confiance_qualification INTEGER,
    description_courte TEXT,
    comportement_precedent TEXT,
    point_de_rupture_detecte BOOLEAN,
    point_de_rupture_timestamp TEXT,
    point_de_rupture_declencheur TEXT,
    sens_transition TEXT,
    similarite_score REAL,
    confluence_mtf_confirmee BOOLEAN,
    rejet_repulsion_detecte BOOLEAN,
    stale BOOLEAN,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_behaviors_symbol_tf_timestamp
    ON behaviors (symbol, timeframe, timestamp);
"""


class WindowGateError(ValueError):
    """Erreur d'évaluation (comportement introuvable, données invalides)."""


@dataclass
class Behavior:
    """Reflet plat d'un objet Comportement (FORMAT_COMPORTEMENTS.md)."""

    behavior_id: str
    symbol: str
    timeframe: str
    timestamp: str
    qualification: str
    confiance_qualification: int
    scene_id_ref: str
    scene_timestamp: str = ""
    window_start: str = ""
    window_end: str = ""
    intensite: str = "moderee"
    phase: str = "developpement"
    description_courte: str = ""
    comportement_precedent: str | None = None
    point_de_rupture_detecte: bool = False
    point_de_rupture_timestamp: str | None = None
    point_de_rupture_declencheur: str | None = None
    sens_transition: str | None = None
    similarite_score: float | None = None
    # Champs auxiliaires (voir docstring module) — pass-through amont.
    confluence_mtf_confirmee: bool = False
    rejet_repulsion_detecte: bool = False
    stale: bool = False

    @classmethod
    def from_format_comportements(cls, raw: dict) -> "Behavior":
        """Construit un Behavior depuis un dict au format FORMAT_COMPORTEMENTS.md."""
        if not raw.get("behavior_id"):
            raise WindowGateError("behavior_id manquant ou vide")
        comportement = raw.get("comportement") or {}
        transitions = raw.get("transitions") or {}
        point_de_rupture = transitions.get("point_de_rupture") or {}
        comparaison = raw.get("comparaison_cas_connus") or {}
        return cls(
            behavior_id=raw["behavior_id"],
            symbol=raw.get("symbol", ""),
            timeframe=raw.get("timeframe", ""),
            timestamp=raw.get("timestamp", ""),
            qualification=comportement.get("qualification", ""),
            confiance_qualification=int(comportement.get("confiance_qualification", 0)),
            scene_id_ref=raw.get("scene_id_ref", ""),
            scene_timestamp=raw.get("scene_timestamp", ""),
            window_start=raw.get("window_start", ""),
            window_end=raw.get("window_end", ""),
            intensite=comportement.get("intensite", "moderee"),
            phase=comportement.get("phase", "developpement"),
            description_courte=comportement.get("description_courte", ""),
            comportement_precedent=transitions.get("comportement_precedent"),
            point_de_rupture_detecte=bool(point_de_rupture.get("detecte", False)),
            point_de_rupture_timestamp=point_de_rupture.get("timestamp"),
            point_de_rupture_declencheur=point_de_rupture.get("declencheur"),
            sens_transition=transitions.get("sens_transition"),
            similarite_score=comparaison.get("similarite_score"),
            confluence_mtf_confirmee=bool(raw.get("confluence_mtf_confirmee", False)),
            rejet_repulsion_detecte=bool(raw.get("rejet_repulsion_detecte", False)),
            stale=bool(raw.get("stale", False)),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Behavior":
        return cls(
            behavior_id=row["behavior_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            timestamp=row["timestamp"],
            qualification=row["qualification"],
            confiance_qualification=row["confiance_qualification"],
            scene_id_ref=row["scene_id_ref"],
            scene_timestamp=row["scene_timestamp"] or "",
            window_start=row["window_start"] or "",
            window_end=row["window_end"] or "",
            intensite=row["intensite"] or "moderee",
            phase=row["phase"] or "developpement",
            description_courte=row["description_courte"] or "",
            comportement_precedent=row["comportement_precedent"],
            point_de_rupture_detecte=bool(row["point_de_rupture_detecte"]),
            point_de_rupture_timestamp=row["point_de_rupture_timestamp"],
            point_de_rupture_declencheur=row["point_de_rupture_declencheur"],
            sens_transition=row["sens_transition"],
            similarite_score=row["similarite_score"],
            confluence_mtf_confirmee=bool(row["confluence_mtf_confirmee"]),
            rejet_repulsion_detecte=bool(row["rejet_repulsion_detecte"]),
            stale=bool(row["stale"]),
        )


def insert_behavior(conn: sqlite3.Connection, raw: dict) -> Behavior:
    """Insère un comportement (format FORMAT_COMPORTEMENTS.md) dans la table shim.

    Helper de constitution de fixtures / tests. Une fois `behavior_db.py`
    (Phase 4) fusionné, cette fonction disparaît au profit de son
    équivalent officiel.
    """
    behavior = Behavior.from_format_comportements(raw)
    conn.execute(
        """
        INSERT OR REPLACE INTO behaviors (
            behavior_id, schema_version, timestamp, scene_id_ref, scene_timestamp,
            symbol, timeframe, window_start, window_end,
            qualification, intensite, phase, confiance_qualification, description_courte,
            comportement_precedent,
            point_de_rupture_detecte, point_de_rupture_timestamp, point_de_rupture_declencheur,
            sens_transition, similarite_score,
            confluence_mtf_confirmee, rejet_repulsion_detecte, stale, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            behavior.behavior_id,
            raw.get("schema_version", SCHEMA_VERSION),
            behavior.timestamp,
            behavior.scene_id_ref,
            behavior.scene_timestamp,
            behavior.symbol,
            behavior.timeframe,
            behavior.window_start,
            behavior.window_end,
            behavior.qualification,
            behavior.intensite,
            behavior.phase,
            behavior.confiance_qualification,
            behavior.description_courte,
            behavior.comportement_precedent,
            behavior.point_de_rupture_detecte,
            behavior.point_de_rupture_timestamp,
            behavior.point_de_rupture_declencheur,
            behavior.sens_transition,
            behavior.similarite_score,
            behavior.confluence_mtf_confirmee,
            behavior.rejet_repulsion_detecte,
            behavior.stale,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return behavior


# ── Types de fenêtre / conditions d'invalidation ─────────
_TYPE_BY_QUALIFICATION = {
    "bascule": "retournement",
    "rupture": "retournement",
    "extension": "continuation",
    "seconde_bosse": "continuation",
    "reequilibrage": "rupture_range",
}


class WindowGate:
    """Évalue le statut de fenêtre d'un comportement et gère son cycle de vie."""

    def __init__(
        self,
        db_path: Path | None = None,
        config: Any = None,
        memory_path: Path | None = None,
    ) -> None:
        self.db_path = db_path or default_config.DB_PATH
        self.config = config or default_config
        self.memory_path = memory_path or MEMORY_TEMP_PATH
        init_window_db(self.db_path)
        self._ensure_behaviors_table()

    # ── Connexion / schéma shim ───────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = get_windows_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_behaviors_table(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(BEHAVIORS_SHIM_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def insert_behavior(self, raw: dict) -> Behavior:
        """Insère un comportement de test/fixture dans la table shim."""
        conn = self._connect()
        try:
            return insert_behavior(conn, raw)
        finally:
            conn.close()

    # ── Chargement des comportements ──────────────────────
    def _load_behavior(self, behavior_id: str) -> Behavior:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM behaviors WHERE behavior_id = ?", (behavior_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise WindowGateError(f"comportement introuvable: {behavior_id!r}")
        return Behavior.from_row(row)

    def _load_behavior_history(self, behavior: Behavior) -> list[Behavior]:
        """Comportements précédents (même paire+TF), plus récent en premier."""
        lookback = getattr(self.config, "WINDOW_LIFECYCLE_LOOKBACK", 5)
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM behaviors
                WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (behavior.symbol, behavior.timeframe, behavior.timestamp, lookback),
            ).fetchall()
        finally:
            conn.close()
        return [Behavior.from_row(r) for r in rows]

    def _get_last_window(self, symbol: str, timeframe: str) -> dict | None:
        """Dernière fenêtre connue (toute statut confondu) pour paire+TF."""
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT w.* FROM windows w
                JOIN behaviors b ON b.behavior_id = w.behavior_id
                WHERE b.symbol = ? AND b.timeframe = ?
                ORDER BY w.id DESC
                LIMIT 1
                """,
                (symbol, timeframe),
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row is not None else None

    # ── Éligibilité ────────────────────────────────────────
    def _check_eligibility(self, behavior: Behavior) -> bool:
        """True si la confiance du comportement autorise une fenêtre active."""
        seuil = getattr(self.config, "CONFIANCE_MIN_FENETRE", 50)
        return behavior.confiance_qualification >= seuil

    # ── Statut ─────────────────────────────────────────────
    def _determine_status(self, behavior: Behavior, history: list[Behavior]) -> str:
        eligible = self._check_eligibility(behavior)
        qualification = behavior.qualification

        if qualification == "maintien":
            return "absente"

        if qualification == "preparation_ouverture_fenetre":
            return "en_preparation" if eligible else "ambigue"

        if qualification in ("bascule", "rupture", "extension"):
            return "ouverte" if eligible else "ambigue"

        if qualification == "annulation":
            return "invalidee"

        if qualification == "seconde_bosse":
            last_window = self._get_last_window(behavior.symbol, behavior.timeframe)
            window_was_open = bool(
                last_window
                and last_window.get("statut") in ("ouverte", "fragile")
                and last_window.get("timestamp_fermeture") is None
            )
            if not eligible:
                return "ambigue"
            return "fragile" if window_was_open else "ouverte"

        if qualification == "reequilibrage":
            last_window = self._get_last_window(behavior.symbol, behavior.timeframe)
            window_was_open = bool(
                last_window
                and last_window.get("statut") in ("ouverte", "fragile")
                and last_window.get("timestamp_fermeture") is None
            )
            return "invalidee" if window_was_open else "absente"

        if not eligible:
            return "ambigue"

        return "absente"

    # ── Type de fenêtre ────────────────────────────────────
    def _determine_type(self, behavior: Behavior) -> str | None:
        if behavior.rejet_repulsion_detecte:
            return "rebond"
        return _TYPE_BY_QUALIFICATION.get(behavior.qualification)

    # ── Fragilité ──────────────────────────────────────────
    def _detect_fragility(self, behavior: Behavior, history: list[Behavior]) -> dict:
        delta_seuil = getattr(self.config, "FRAGILITE_CONFIANDE_DELTA", 15)
        raisons: list[str] = []

        if behavior.stale:
            raisons.append("comportement source marque stale")

        if history:
            precedent = history[0]
            baisse = precedent.confiance_qualification - behavior.confiance_qualification
            if baisse >= delta_seuil:
                raisons.append(
                    "confiance_qualification en baisse par rapport au comportement precedent"
                    f" ({precedent.confiance_qualification} -> {behavior.confiance_qualification})"
                )
            if precedent.qualification == "annulation":
                raisons.append("comportement precedent en transition vers annulation")

        for past in history:
            if past.qualification == "rotation_leadership" and past.sens_transition == "inversion":
                raisons.append("rotation de leadership detectee qui contredit le sens")
                break

        if not raisons:
            return {"detectee": False, "raison": None}
        return {"detectee": True, "raison": "; ".join(raisons)}

    # ── Confiance globale ──────────────────────────────────
    def _calculate_confidence(
        self, behavior: Behavior, history: list[Behavior], fragilite: dict
    ) -> int:
        niveau = behavior.confiance_qualification

        if behavior.confluence_mtf_confirmee:
            niveau += getattr(self.config, "BONUS_CONFLUENCE_MTF", 10)

        seuil_similarite = getattr(self.config, "SIMILARITE_BONUS_THRESHOLD", 0.75)
        if behavior.similarite_score is not None and behavior.similarite_score >= seuil_similarite:
            niveau += getattr(self.config, "BONUS_SIMILARITE", 8)

        if behavior.stale:
            niveau -= getattr(self.config, "MALUS_STALE", 20)

        if fragilite.get("detectee"):
            niveau -= getattr(self.config, "MALUS_FRAGILITE", 15)

        return max(0, min(100, niveau))

    # ── Conditions d'invalidation ──────────────────────────
    def _define_invalidation_conditions(
        self, behavior: Behavior, statut: str, type_fenetre: str | None
    ) -> list[dict]:
        if statut == "absente":
            return []

        conditions: list[dict] = []
        qualification = behavior.qualification

        if qualification == "bascule":
            conditions.append({
                "condition": "retour_zone_origine",
                "description": "prix referme sous la zone de bascule dans les 3 bougies suivantes",
            })
            conditions.append({
                "condition": "rotation_leadership_inverse",
                "description": (
                    "un nouveau comportement rotation_leadership contredit le sens de la bascule"
                ),
            })
        if qualification == "extension":
            conditions.append({
                "condition": "contraction_suivante",
                "description": "un comportement contraction survient avant confirmation",
            })
        if qualification == "rupture":
            conditions.append({
                "condition": "reequilibrage_rapide",
                "description": "un reequilibrage survient dans les 2 bougies suivantes",
            })
        if qualification == "seconde_bosse":
            conditions.append({
                "condition": "intensite_insuffisante",
                "description": "l'intensite du comportement devient faible",
            })
        if type_fenetre == "continuation":
            conditions.append({
                "condition": "bascule_inverse",
                "description": "un comportement bascule de sens oppose survient",
            })

        return conditions

    # ── Cycle de vie ───────────────────────────────────────
    def _manage_lifecycle(self, behavior: Behavior, statut: str) -> dict:
        last_window = self._get_last_window(behavior.symbol, behavior.timeframe)
        timestamp_ouverture: str | None = None
        timestamp_fermeture: str | None = None

        window_was_open = bool(
            last_window
            and last_window.get("statut") in ("ouverte", "fragile")
            and last_window.get("timestamp_fermeture") is None
        )

        if statut in ("ouverte", "fragile"):
            if window_was_open and last_window.get("timestamp_ouverture"):
                timestamp_ouverture = last_window["timestamp_ouverture"]
            else:
                timestamp_ouverture = behavior.timestamp
        elif statut == "invalidee":
            if window_was_open and last_window.get("timestamp_ouverture"):
                timestamp_ouverture = last_window["timestamp_ouverture"]
            timestamp_fermeture = behavior.timestamp

        return {
            "timestamp_ouverture": timestamp_ouverture,
            "timestamp_fermeture": timestamp_fermeture,
        }

    # ── Assemblage / écriture ──────────────────────────────
    def evaluate_behavior(self, behavior_id: str) -> dict:
        """Évalue un comportement et produit une fenêtre au format FORMAT_FENETRES.md."""
        behavior = self._load_behavior(behavior_id)
        history = self._load_behavior_history(behavior)

        statut = self._determine_status(behavior, history)
        type_fenetre = self._determine_type(behavior) if statut != "absente" else None
        fragilite = self._detect_fragility(behavior, history)

        if fragilite["detectee"] and statut == "ouverte":
            statut = "fragile"
        if statut == "absente":
            type_fenetre = None

        niveau_confiance = self._calculate_confidence(behavior, history, fragilite)
        conditions = self._define_invalidation_conditions(behavior, statut, type_fenetre)
        lifecycle = self._manage_lifecycle(behavior, statut)

        window = self._build_window(behavior, statut, type_fenetre, niveau_confiance, fragilite, conditions, lifecycle)

        self._write_window_to_db(window)
        self._write_memory(window, statut="hypothese")

        return window

    def _build_window(
        self,
        behavior: Behavior,
        statut: str,
        type_fenetre: str | None,
        niveau_confiance: int,
        fragilite: dict,
        conditions: list[dict],
        lifecycle: dict,
    ) -> dict:
        return {
            "window_id": _generate_window_id(behavior),
            "schema_version": SCHEMA_VERSION,
            "timestamp": behavior.timestamp,
            "behavior_source": {
                "behavior_id": behavior.behavior_id,
                "qualification": behavior.qualification,
                "confiance_qualification": behavior.confiance_qualification,
            },
            "statut": statut,
            "type_fenetre": type_fenetre,
            "niveau_confiance": niveau_confiance,
            "duree_de_vie": {
                "timestamp_ouverture": lifecycle["timestamp_ouverture"],
                "timestamp_fermeture": lifecycle["timestamp_fermeture"],
                "fragilite": {
                    "detectee": fragilite["detectee"],
                    "raison": fragilite["raison"],
                },
            },
            "conditions_invalidation": conditions,
            "meta": {
                "produit_par": "window-gate",
            },
            # champ interne, non-FORMAT_FENETRES.md, utile au cycle de vie/DB.
            "_stale": behavior.stale,
        }

    def _write_window_to_db(self, window: dict) -> None:
        behavior_source = window["behavior_source"]
        fragilite = window["duree_de_vie"]["fragilite"]
        values = (
            window["window_id"],
            window["schema_version"],
            window["timestamp"],
            behavior_source["behavior_id"],
            behavior_source["qualification"],
            behavior_source["confiance_qualification"],
            window["statut"],
            window["type_fenetre"],
            window["niveau_confiance"],
            window["duree_de_vie"]["timestamp_ouverture"],
            window["duree_de_vie"]["timestamp_fermeture"],
            fragilite["detectee"],
            fragilite["raison"],
            json.dumps(window["conditions_invalidation"], ensure_ascii=False),
            window.get("_stale", False),
            datetime.now(timezone.utc).isoformat(),
        )
        conn = self._connect()
        try:
            placeholders = ", ".join("?" for _ in WINDOWS_COLUMNS)
            columns = ", ".join(WINDOWS_COLUMNS)
            conn.execute(
                f"INSERT OR REPLACE INTO windows ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    def _write_memory(self, window: dict, statut: str = "hypothese") -> dict:
        """Écrit une entrée mémoire (MEMORY_CONTRACT.md) dans memory_temp.md."""
        entry = {
            "schema_version": SCHEMA_VERSION,
            "entry_id": f"mem-{_compact_timestamp(window['timestamp'])}-{uuid.uuid4().hex[:6]}",
            "type": "fenetre",
            "statut": statut,
            "couche_origine": "fenetres",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "reference": {
                "id": window["behavior_source"]["behavior_id"],
                "timestamp": window["timestamp"],
            },
            "contenu": window,
            "justification": "",
        }
        self._append_memory_entry(entry)
        return entry

    def _append_memory_entry(self, entry: dict) -> None:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_path.exists():
            self.memory_path.write_text(
                "# memory_temp.md — Journal de travail temporaire PowerFlow V9\n\n"
                "### Fenetres (hypotheses)\n\n",
                encoding="utf-8",
            )
        block = "```json\n" + json.dumps(entry, ensure_ascii=False, indent=2) + "\n```\n\n"
        with self.memory_path.open("a", encoding="utf-8") as fh:
            fh.write(block)


def _generate_window_id(behavior: Behavior) -> str:
    compact_ts = _compact_timestamp(behavior.timestamp)
    symbol = (behavior.symbol or "unknown").lower()
    timeframe = (behavior.timeframe or "na").lower()
    return f"win_{compact_ts}_{symbol}_{timeframe}_{uuid.uuid4().hex[:6]}"


def _compact_timestamp(timestamp: str) -> str:
    if not timestamp:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .rstrip("Z")
        + "Z"
    )
