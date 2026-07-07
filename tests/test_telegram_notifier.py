"""Tests — v9_telegram_notifier (alertes Telegram GBPUSD).

Vérifie :
- Filtre confiance > 65 (64% ne part pas, 66% part)
- Anti-doublon par decision_id (même id envoyé 2x → 1 seul message)
- Format message (tous les champs présents)

Aucun appel réel à Telegram API (mock urllib.request).
Aucune modification de core/v9/* ni de config.py.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.decision_db import DECISIONS_COLUMNS, init_decision_db
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS, init_principle_db
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db
from core.v9.signal_db import SIGNALS_COLUMNS, init_signal_db
from core.v9.window_db import WINDOWS_COLUMNS, init_window_db

from scripts.v9_telegram_notifier import (
    _fetch_new_decisions,
    _format_message,
    _read_last_sent_id,
    _write_last_sent_id,
    _enrich_decision,
    _format_tf_alignes,
    _format_cest_timestamp,
    _read_offset,
    _write_offset,
    _is_paused,
    _set_paused,
    _build_status_response,
    _build_last_response,
    _handle_command,
    CONFIANCE_MIN,
    SYMBOL,
)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    init_scene_db(path)
    init_behavior_db(path)
    init_window_db(path)
    init_exploitability_db(path)
    init_regime_db(path)
    init_principle_db(path)
    init_signal_db(path)
    init_decision_db(path)
    return path


def _insert_row(db_path: Path, table: str, columns: list[str], values: dict) -> None:
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conn.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            [values.get(c) for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_decision(
    db_path: Path,
    *,
    decision_id: str | None = None,
    symbol: str = "GBPUSD",
    direction: str = "haussiere",
    confiance: int = 80,
    regime_type: str = "NEUTRE",
    scene_id: str | None = None,
    behavior_id: str | None = None,
    snapshot_id: str | None = None,
    principes: list[str] | None = None,
    timestamp: str = "2026-07-06T14:35:29.463604+00:00",
) -> str:
    """Insère une décision de test et retourne son decision_id."""
    dec_id = decision_id or f"dec_test_{uuid.uuid4().hex[:8]}"
    snap_id = snapshot_id or f"v9-test-{uuid.uuid4().hex[:8]}"
    sc_id = scene_id or f"scene-test-{uuid.uuid4().hex[:8]}"
    beh_id = behavior_id or f"beh-test-{uuid.uuid4().hex[:8]}"

    conn = get_connection(db_path)
    try:
        principes_json = json.dumps(principes) if principes is not None else json.dumps(["POWER_ANGLE_BREAK_TO_PRICE_IMPACT"])
        conn.execute(
            """INSERT INTO decisions
               (decision_id, schema_version, timestamp, snapshot_id, signal_id,
                action, symbol, timeframe, currency, scene_id, behavior_id,
                window_id, exploitability_id, regime_type, direction, confiance,
                principes_json, contexte_complet_json, created_at, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dec_id, "1.0", timestamp, snap_id, f"sig_{uuid.uuid4().hex[:8]}",
                "preparer_entree", symbol, "M5", "GBP", sc_id, beh_id,
                f"win_{uuid.uuid4().hex[:8]}", f"exp_{uuid.uuid4().hex[:8]}",
                regime_type, direction, confiance,
                principes_json,
                "{}", timestamp, "live",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return dec_id


def _insert_scene(db_path: Path, scene_id: str, *, structure: str = "zone neutre") -> None:
    """Insère une scène de test."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO scenes
               (scene_id, schema_version, timestamp, timeframes_concernes,
                forces_snapshot_ref, zone_json, coalitions_json, antagonismes_json,
                cinematique_json, confluences_mtf_json, contexte_temporel_json,
                stale, created_at, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scene_id, "1.0", "2026-07-06T14:00:00.000Z", '["M5","H1","H4"]',
                f"v9-test-{uuid.uuid4().hex[:8]}",
                json.dumps({"prix": {}, "structure": structure, "niveau": "mineure"}),
                "[]", "[]", "{}",
                json.dumps({
                    "emboitement_detecte": True,
                    "cascades_temporelles": [
                        {"de_timeframe": "D1", "vers_timeframe": "H4",
                         "description": "coalition test D1→H4"},
                        {"de_timeframe": "H4", "vers_timeframe": "H1",
                         "description": "coalition test H4→H1"},
                    ],
                }),
                json.dumps({"session": "london", "fenetre": "pleine"}),
                False, "2026-07-06T14:00:00.000Z", "live",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_behavior(db_path: Path, behavior_id: str, *, qualification: str = "rotation_leadership") -> None:
    """Insère un comportement de test."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO behaviors
               (behavior_id, schema_version, timestamp, scene_id_ref, scene_timestamp,
                symbol, timeframe, window_start, window_end, qualification, intensite,
                phase, confiance_qualification, point_de_rupture_detecte, stale, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                behavior_id, "1.0", "2026-07-06T14:00:00.000Z",
                "scene-ignored", "2026-07-06T14:00:00.000Z",
                "GBPUSD", "M5", "2026-07-06T13:55:00.000Z", "2026-07-06T14:00:00.000Z",
                qualification, "extreme", "developpement", 70,
                False, False, "2026-07-06T14:00:00.000Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_principle_evaluation(
    db_path: Path,
    snapshot_id: str,
    *,
    principle_id: str = "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
    triggered: bool = True,
    confidence: int = 100,
    direction: str = "haussiere",
) -> None:
    """Insère une évaluation de principe de test."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO principle_evaluations
               (evaluation_id, schema_version, timestamp, snapshot_id, principle_id,
                v9_status, kind, symbol, timeframe, currency, triggered, direction,
                confidence, anti_signal_bias, reason, context_json, created_at, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"peval_test_{uuid.uuid4().hex[:8]}", "1.0",
                "2026-07-06T14:00:00.000Z", snapshot_id,
                principle_id, "ACTIVE", "node_rule",
                "GBPUSD", "M5", "GBP",
                1 if triggered else 0, direction, confidence,
                0, "conditions_remplies" if triggered else "condition_non_remplie",
                "{}", "2026-07-06T14:00:00.000Z", "live",
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ── Helper pour créer un environnement de test complet ─────────


def _build_test_env(db_path: Path, **overrides) -> dict:
    """Crée une décision avec scène, comportement et principes associés.

    Retourne un dict avec les clés nécessaires aux assertions.
    """
    scene_id = f"scene_test_{uuid.uuid4().hex[:8]}"
    behavior_id = f"beh_test_{uuid.uuid4().hex[:8]}"
    snapshot_id = f"v9_test_{uuid.uuid4().hex[:8]}"

    _insert_scene(db_path, scene_id, structure=overrides.get("scene_structure", "zone neutre"))
    _insert_behavior(db_path, behavior_id, qualification=overrides.get("behavior_qualification", "rotation_leadership"))
    _insert_principle_evaluation(
        db_path, snapshot_id,
        principle_id=overrides.get("principle_id", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"),
        triggered=True, confidence=100, direction=overrides.get("direction", "haussiere"),
    )

    dec_id = _insert_decision(
        db_path,
        decision_id=overrides.get("decision_id"),
        symbol=overrides.get("symbol", "GBPUSD"),
        direction=overrides.get("direction", "haussiere"),
        confiance=overrides.get("confiance", 80),
        regime_type=overrides.get("regime_type", "NEUTRE"),
        scene_id=scene_id,
        behavior_id=behavior_id,
        snapshot_id=snapshot_id,
        principes=overrides.get("principes", [overrides.get("principle_id", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT")]),
        timestamp=overrides.get("timestamp", "2026-07-06T14:35:29.463604+00:00"),
    )

    return {
        "decision_id": dec_id,
        "scene_id": scene_id,
        "behavior_id": behavior_id,
        "snapshot_id": snapshot_id,
    }


# ── Tests ──────────────────────────────────────────────────────


class TestFiltreConfiance:
    """Vérifie le filtre confiance > 65."""

    def test_confiance_66_part(self, db_path: Path) -> None:
        """Une décision à 66% doit être retournée par _fetch_new_decisions."""
        _build_test_env(db_path, confiance=66)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["confiance"] == 66

    def test_confiance_65_ne_part_pas(self, db_path: Path) -> None:
        """Une décision à 65% (<= 65) ne doit PAS être retournée."""
        _build_test_env(db_path, confiance=65)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 0

    def test_confiance_64_ne_part_pas(self, db_path: Path) -> None:
        """Une décision à 64% ne doit PAS être retournée."""
        _build_test_env(db_path, confiance=64)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 0

    def test_filtre_symbol_gbpusd(self, db_path: Path) -> None:
        """Seules les décisions GBPUSD sont retournées."""
        _build_test_env(db_path, symbol="EURUSD", confiance=80)
        _build_test_env(db_path, symbol="GBPUSD", confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "GBPUSD"  # _fetch_new_decisions ne retourne pas symbol, mais on vérifie la logique

    def test_filtre_direction_neutre_exclue(self, db_path: Path) -> None:
        """Les décisions neutres ne sont pas retournées."""
        _build_test_env(db_path, direction="neutre", confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 0

    def test_filtre_direction_nulle_exclue(self, db_path: Path) -> None:
        """Les décisions sans direction ne sont pas retournées."""
        _build_test_env(db_path, direction=None, confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 0


class TestAntiDoublon:
    """Vérifie l'anti-doublon par decision_id."""

    def test_meme_decision_id_envoye_une_fois(self, db_path: Path, tmp_path: Path) -> None:
        """Même decision_id avec last_id persistant → ignoré au second appel."""
        env = _build_test_env(db_path, confiance=80)
        last_sent = tmp_path / ".telegram_last_sent_id"
        last_sent.write_text(env["decision_id"], encoding="utf-8")

        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, env["decision_id"])
        finally:
            conn.close()
        assert len(rows) == 0, "La même décision ne doit pas être renvoyée"

    def test_deux_decisions_differentes_toutes_envoyees(self, db_path: Path) -> None:
        """Deux décisions différentes sont toutes retournées."""
        _build_test_env(db_path, decision_id="dec_A", confiance=80)
        _build_test_env(db_path, decision_id="dec_B", confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
        finally:
            conn.close()
        assert len(rows) == 2

    def test_last_id_filtre_anciennes(self, db_path: Path) -> None:
        """Avec un last_id, seules les décisions plus récentes sont retournées."""
        _build_test_env(db_path, decision_id="dec_ancienne", confiance=80,
                        timestamp="2026-07-06T12:00:00+00:00")
        _build_test_env(db_path, decision_id="dec_recente", confiance=80,
                        timestamp="2026-07-06T14:00:00+00:00")
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, "dec_ancienne")
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["decision_id"] == "dec_recente"

    def test_persistance_last_sent_id(self, tmp_path: Path) -> None:
        """_write_last_sent_id puis _read_last_sent_id retourne la même valeur."""
        sent_path = tmp_path / ".telegram_last_sent_id"
        # On patche le chemin pour le test
        with patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", sent_path):
            _write_last_sent_id("dec_test_123")
            assert _read_last_sent_id() == "dec_test_123"

    def test_read_last_sent_id_inexistant(self, tmp_path: Path) -> None:
        """_read_last_sent_id retourne None si le fichier n'existe pas."""
        sent_path = tmp_path / ".telegram_last_sent_id"
        with patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", sent_path):
            assert _read_last_sent_id() is None


class TestFormatMessage:
    """Vérifie le formatage du message Telegram."""

    def _fetch_and_enrich(self, db_path: Path) -> dict:
        """Helper: fetch + enrich en gardant la connexion ouverte."""
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
            assert len(rows) == 1
            return _enrich_decision(cursor, rows[0])
        finally:
            conn.close()

    def test_tous_champs_presents(self, db_path: Path) -> None:
        """Le message formaté contient tous les champs requis."""
        _build_test_env(db_path, confiance=80, direction="haussiere")
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "GBPUSD" in msg
        assert "HAUSSIERE" in msg
        assert "80%" in msg
        assert "TF alignés" in msg
        assert "Principes" in msg
        assert "Scène" in msg
        assert "Régime" in msg
        assert "NEUTRE" in msg

    def test_message_baissier(self, db_path: Path) -> None:
        """Le message pour une décision baissière contient 🔴 et BAISSIERE."""
        _build_test_env(db_path, confiance=90, direction="baissiere")
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "🔴" in msg
        assert "BAISSIERE" in msg
        assert "90%" in msg

    def test_message_haussier(self, db_path: Path) -> None:
        """Le message pour une décision haussière contient 🟢 et HAUSSIERE."""
        _build_test_env(db_path, confiance=100, direction="haussiere")
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "🟢" in msg
        assert "HAUSSIERE" in msg
        assert "100%" in msg

    def test_tf_alignes_dans_message(self, db_path: Path) -> None:
        """Les TF alignés apparaissent dédupliqués avec comptage dans le message."""
        _build_test_env(db_path, confiance=80)
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "D1→H4 ×1" in msg
        assert "H4→H1 ×1" in msg

    def test_principes_dans_message(self, db_path: Path) -> None:
        """Les noms des principes actifs apparaissent dans le message."""
        _build_test_env(
            db_path, confiance=80,
            principes=["POWER_ANGLE_BREAK_TO_PRICE_IMPACT", "ZONE_RETEST"],
        )
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "POWER_ANGLE_BREAK_TO_PRICE_IMPACT" in msg
        assert "ZONE_RETEST" in msg

    def test_behavior_qualification_dans_message(self, db_path: Path) -> None:
        """La qualification du comportement apparaît dans le message."""
        _build_test_env(
            db_path, confiance=80,
            behavior_qualification="bascule",
        )
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "bascule" in msg

    def test_timestamp_cest_dans_message(self, db_path: Path) -> None:
        """Le timestamp est formaté en CEST court (JJ/MM HHhMM CEST) dans le message."""
        _build_test_env(
            db_path, confiance=80,
            timestamp="2026-07-06T14:35:29.463604+00:00",
        )
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        # 14:35 UTC → 16:35 CEST, format court "06/07 16h35 CEST"
        assert "06/07 16h35 CEST" in msg

    def test_principes_actifs_enrichis(self, db_path: Path) -> None:
        """Les principes actifs depuis principle_evaluations sont dans le message."""
        _build_test_env(
            db_path, confiance=80,
            principle_id="GRAVITY_RESPRING_NODE",
            principes=[],  # vide → fallback sur principes_actifs enrichis
        )
        d = self._fetch_and_enrich(db_path)
        msg = _format_message(d)

        assert "GRAVITY_RESPRING_NODE" in msg


class TestEnvoiTelegram:
    """Vérifie le comportement d'envoi (mocké)."""

    def test_send_appele_pour_nouvelle_decision(self, db_path: Path, tmp_path: Path) -> None:
        """send_telegram est appelé pour chaque nouvelle décision."""
        env = _build_test_env(db_path, confiance=80)
        last_sent = tmp_path / ".telegram_last_sent_id"
        if last_sent.exists():
            last_sent.unlink()

        config = {"token": "fake:token", "chat_id": "12345"}

        with (
            patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", last_sent),
            patch("scripts.v9_telegram_notifier.DB_PATH", db_path),
            patch("scripts.v9_telegram_notifier.send_telegram", return_value=True) as mock_send,
        ):
            from scripts.v9_telegram_notifier import _poll_once
            _poll_once(config, None)

        assert mock_send.called, "send_telegram doit être appelé"
        assert last_sent.read_text(encoding="utf-8").strip() == env["decision_id"]

    def test_send_pas_appele_si_aucune_nouvelle(self, db_path: Path, tmp_path: Path) -> None:
        """send_telegram n'est pas appelé s'il n'y a pas de nouvelle décision."""
        last_sent = tmp_path / ".telegram_last_sent_id"
        last_sent.write_text("zzz_aucune", encoding="utf-8")

        config = {"token": "fake:token", "chat_id": "12345"}

        with (
            patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", last_sent),
            patch("scripts.v9_telegram_notifier.DB_PATH", db_path),
            patch("scripts.v9_telegram_notifier.send_telegram", return_value=True) as mock_send,
        ):
            from scripts.v9_telegram_notifier import _poll_once
            _poll_once(config, "zzz_aucune")

        assert not mock_send.called, "send_telegram ne doit pas être appelé"

    def test_send_pas_appele_si_confiance_trop_basse(self, db_path: Path, tmp_path: Path) -> None:
        """send_telegram n'est pas appelé si confiance <= 65."""
        _build_test_env(db_path, confiance=65)
        last_sent = tmp_path / ".telegram_last_sent_id"
        if last_sent.exists():
            last_sent.unlink()

        config = {"token": "fake:token", "chat_id": "12345"}

        with (
            patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", last_sent),
            patch("scripts.v9_telegram_notifier.DB_PATH", db_path),
            patch("scripts.v9_telegram_notifier.send_telegram", return_value=True) as mock_send,
        ):
            from scripts.v9_telegram_notifier import _poll_once
            _poll_once(config, None)

        assert not mock_send.called, "send_telegram ne doit pas être appelé pour confiance <= 65"

    def test_send_http_error_logguee(self, db_path: Path, tmp_path: Path) -> None:
        """Une erreur HTTP n'interrompt pas le polling."""
        _build_test_env(db_path, confiance=80)
        last_sent = tmp_path / ".telegram_last_sent_id"
        if last_sent.exists():
            last_sent.unlink()

        config = {"token": "fake:token", "chat_id": "12345"}

        with (
            patch("scripts.v9_telegram_notifier.LAST_SENT_PATH", last_sent),
            patch("scripts.v9_telegram_notifier.DB_PATH", db_path),
            patch("scripts.v9_telegram_notifier.send_telegram", return_value=False),
        ):
            from scripts.v9_telegram_notifier import _poll_once
            # Ne doit pas lever d'exception
            result = _poll_once(config, None)
            # last_id ne doit pas être mis à jour si l'envoi échoue
            assert result is None or result == ""


class TestEnrichissement:
    """Vérifie l'enrichissement des décisions avec les données associées."""

    def test_enrich_principes_actifs(self, db_path: Path) -> None:
        """_enrich_decision ajoute les principes actifs depuis principle_evaluations."""
        env = _build_test_env(db_path, confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
            assert len(rows) == 1
            d = _enrich_decision(cursor, rows[0])
        finally:
            conn.close()

        assert "principes_actifs" in d
        assert len(d["principes_actifs"]) >= 1
        assert d["principes_actifs"][0]["id"] == "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"

    def test_enrich_scene_type(self, db_path: Path) -> None:
        """_enrich_decision ajoute le type de scène depuis zone_json."""
        env = _build_test_env(db_path, confiance=80, scene_structure="zone d'extension")
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
            assert len(rows) == 1
            d = _enrich_decision(cursor, rows[0])
        finally:
            conn.close()

        assert d.get("scene_type") == "zone d'extension"

    def test_enrich_behavior_qualification(self, db_path: Path) -> None:
        """_enrich_decision ajoute la qualification du comportement."""
        env = _build_test_env(db_path, confiance=80, behavior_qualification="bascule")
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
            assert len(rows) == 1
            d = _enrich_decision(cursor, rows[0])
        finally:
            conn.close()

        assert d.get("behavior_qualification") == "bascule"

    def test_enrich_tf_alignes(self, db_path: Path) -> None:
        """_enrich_decision ajoute les TF alignés depuis confluences_mtf_json."""
        env = _build_test_env(db_path, confiance=80)
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()
            rows = _fetch_new_decisions(cursor, None)
            assert len(rows) == 1
            d = _enrich_decision(cursor, rows[0])
        finally:
            conn.close()

        assert "tf_alignes" in d
        assert "D1→H4" in d["tf_alignes"]
        assert "H4→H1" in d["tf_alignes"]
