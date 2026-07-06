"""test_news_context.py — Tests du module NewsContext (couche transversale V9).

Vérifie :
- les 4 phases (PRE_NEWS / NEWS_SHOCK / POST_NEWS / NEUTRE)
- les distances signées (futur +, passé -)
- news_session_clean (pas de HIGH dans 90 min)
- fallback NEUTRE sur calendrier vide / corrompu
- propagation des 5 champs via _load_shared_context

Le calendrier utilisé est data/economic_calendar.json (fixture réelle).
On peut aussi construire un calendrier en mémoire via calendar_path
temporaire pour les cas qui demandent une date précise sans polluer
le fichier canonique.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_db
from core.v9.news_context import NewsContext
from core.v9.principle_engine import PrincipleEngine
from core.v9.scene_db import init_scene_db
from core.v9.behavior_db import init_behavior_db
from core.v9.window_db import init_window_db
from core.v9.exploitability_db import init_exploitability_db


# ── Chemins ─────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
CALENDAR_CANON = REPO_ROOT / "data" / "economic_calendar.json"


def _write_calendar(tmp: Path, items: list[dict]) -> Path:
    """Helper : écrit un calendrier JSON personnalisé dans tmp et retourne le path."""
    p = tmp / "calendar.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def tmp_calendar_dir():
    """Dossier temporaire avec cleanup permissif (Windows WAL)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        yield Path(t)


# ── 1. PRE_NEWS : 45 min avant NFP (typical Friday 12:30 UTC) ──
def test_news_context_pre_news_45min_avant(tmp_calendar_dir):
    """NFP typique = 1er vendredi du mois, 12:30 UTC. À 11:45 UTC,
    on est pile 45 min avant → news_phase = PRE_NEWS, importance HIGH,
    distance_min = +45, news_type = "NFP"."""
    cal_path = _write_calendar(tmp_calendar_dir, [{
        "name": "NFP",
        "importance": "HIGH",
        "recurrence": "monthly_first_friday",
        "typical_utc_hour": 12,
        "typical_utc_minute": 30,
        "window_pre_min": 45,
        "window_shock_min": 15,
        "window_post_min": 90,
    }])
    nfp = NewsContext(cal_path)

    # Choisissons une date qui tombe un vendredi.
    # 2026-07-03 est un vendredi (1er vendredi de juillet 2026).
    nfp_dt = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    assess_dt = nfp_dt - timedelta(minutes=45)  # 11:45 UTC

    out = nfp.assess(assess_dt)
    assert out["news_type"] == "NFP"
    assert out["news_phase"] == "PRE_NEWS"
    assert out["news_importance"] == "HIGH"
    assert out["news_distance_min"] == 45
    # NFP HIGH à 45 min → session_clean = False (HIGH upcoming dans 90 min).
    assert out["news_session_clean"] is False


# ── 2. NEWS_SHOCK : 5 min après une news HIGH ───────────────────
def test_news_context_shock_5min_apres(tmp_calendar_dir):
    """5 min après la news → fenêtre shock (15 min par défaut) → NEWS_SHOCK."""
    cal_path = _write_calendar(tmp_calendar_dir, [{
        "name": "NFP",
        "importance": "HIGH",
        "recurrence": "monthly_first_friday",
        "typical_utc_hour": 12,
        "typical_utc_minute": 30,
        "window_pre_min": 45,
        "window_shock_min": 15,
        "window_post_min": 90,
    }])
    nfp = NewsContext(cal_path)

    nfp_dt = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    assess_dt = nfp_dt + timedelta(minutes=5)  # 12:35 UTC

    out = nfp.assess(assess_dt)
    assert out["news_type"] == "NFP"
    assert out["news_phase"] == "NEWS_SHOCK"
    assert out["news_importance"] == "HIGH"
    assert out["news_distance_min"] == -5


# ── 3. POST_NEWS : 30 min après la news ───────────────────────────
def test_news_context_post_news_30min_apres(tmp_calendar_dir):
    """30 min après la news → passé la fenêtre shock (15 min), dans
    la fenêtre post_news (90 min) → POST_NEWS."""
    cal_path = _write_calendar(tmp_calendar_dir, [{
        "name": "NFP",
        "importance": "HIGH",
        "recurrence": "monthly_first_friday",
        "typical_utc_hour": 12,
        "typical_utc_minute": 30,
        "window_pre_min": 45,
        "window_shock_min": 15,
        "window_post_min": 90,
    }])
    nfp = NewsContext(cal_path)

    nfp_dt = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    assess_dt = nfp_dt + timedelta(minutes=30)  # 13:00 UTC

    out = nfp.assess(assess_dt)
    assert out["news_type"] == "NFP"
    assert out["news_phase"] == "POST_NEWS"
    assert out["news_importance"] == "HIGH"
    assert out["news_distance_min"] == -30


# ── 4. NEUTRE hors fenêtre ───────────────────────────────────────
def test_news_context_neutre_hors_fenetre(tmp_calendar_dir):
    """120 min après la news > window_post_min (90) → NEUTRE. Et 200 min
    avant la news > window_pre_min (45) → NEUTRE."""
    cal_path = _write_calendar(tmp_calendar_dir, [{
        "name": "NFP",
        "importance": "HIGH",
        "recurrence": "monthly_first_friday",
        "typical_utc_hour": 12,
        "typical_utc_minute": 30,
        "window_pre_min": 45,
        "window_shock_min": 15,
        "window_post_min": 90,
    }])
    nfp = NewsContext(cal_path)

    nfp_dt = datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc)
    # Trop tard après la news → NEUTRE.
    out_late = nfp.assess(nfp_dt + timedelta(minutes=120))
    assert out_late["news_phase"] == "NEUTRE"
    assert out_late["news_distance_min"] is None
    assert out_late["news_type"] is None
    assert out_late["news_importance"] == "NEUTRE"
    # Trop tôt avant la news (> 45 min de pre) → NEUTRE.
    out_early = nfp.assess(nfp_dt - timedelta(minutes=200))
    assert out_early["news_phase"] == "NEUTRE"


# ── 5. Session clean : aucune news HIGH dans 90 min ────────────────
def test_news_context_clean_session_sans_news_proche(tmp_calendar_dir):
    """Pas de news HIGH dans 90 min → session_clean=True. On utilise
    une news MEDIUM éloignée dans le temps et on s'assure qu'on est
    loin."""
    cal_path = _write_calendar(tmp_calendar_dir, [{
        "name": "FOMC_MINUTES",
        "importance": "MEDIUM",
        "recurrence": "8x_year",
        "typical_utc_hour": 18,
        "typical_utc_minute": 0,
        "window_pre_min": 30,
        "window_shock_min": 10,
        "window_post_min": 60,
    }])
    nc = NewsContext(cal_path)

    # 10h00 UTC un jour sans FOMC à proximité.
    far_dt = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)
    out = nc.assess(far_dt)
    assert out["news_session_clean"] is True


# ── 6. Fallback calendrier vide / corrompu → NEUTRE garanti ───────
def test_news_context_fallback_calendar_vide(tmp_calendar_dir):
    """Calendrier vide (liste []) ou corrompu (fichier inexistant /
    JSON cassé) → assess() ne lève pas, retourne le fallback NEUTRE."""
    # a) Calendrier vide (liste []).
    empty_path = _write_calendar(tmp_calendar_dir, [])
    nc_empty = NewsContext(empty_path)
    out_empty = nc_empty.assess(datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))
    assert out_empty == {
        "news_type": None,
        "news_phase": "NEUTRE",
        "news_distance_min": None,
        "news_importance": "NEUTRE",
        "news_session_clean": True,
    }

    # b) Fichier inexistant.
    nc_missing = NewsContext(tmp_calendar_dir / "absent.json")
    out_missing = nc_missing.assess(datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))
    assert out_missing["news_phase"] == "NEUTRE"
    assert out_missing["news_type"] is None

    # c) Fichier corrompu.
    broken = tmp_calendar_dir / "broken.json"
    broken.write_text("{pas du JSON", encoding="utf-8")
    nc_broken = NewsContext(broken)
    out_broken = nc_broken.assess(datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))
    assert out_broken["news_phase"] == "NEUTRE"

    # d) assess() ne lève jamais, même sur datetime bizarre.
    out_weird = nc_broken.assess(datetime(2026, 7, 6))  # naive → OK
    assert "news_phase" in out_weird


# ── 7. Propagation des 5 champs dans _load_shared_context ─────────
def test_news_context_champs_propages_dans_shared_context(tmp_calendar_dir):
    """Garantit que les 5 champs NewsContext apparaissent bien dans le
    contexte retourné par PrincipleEngine._load_shared_context, même
    avec un snapshot sans scène.

    On utilise le calendrier canonique (existe dans data/) : s'il
    n'existe pas on en crée un minimal dans tmp.
    """
    # 1) Calendrier disponible (canonique ou temporaire).
    if CALENDAR_CANON.exists():
        cal_path = CALENDAR_CANON
    else:
        cal_path = _write_calendar(tmp_calendar_dir, [{
            "name": "NFP", "importance": "HIGH",
            "recurrence": "monthly_first_friday",
            "typical_utc_hour": 12, "typical_utc_minute": 30,
            "window_pre_min": 45, "window_shock_min": 15, "window_post_min": 90,
        }])

    # 2) Mini-DB avec 1 snapshot + chaîne complète.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_news.db"
        init_db(db_path)
        # S'assurer que les tables scènes/behaviors/windows/exploit existent.
        init_scene_db(db_path)
        init_behavior_db(db_path)
        init_window_db(db_path)
        init_exploitability_db(db_path)
        engine = PrincipleEngine(db_path=db_path)
        conn = get_connection(db_path)
        conn.row_factory = sqlite3.Row

        # 3) Insertion d'un snapshot minimal (sans scène).
        snap_id = f"snap_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots "
            "(snapshot_id, schema_version, timestamp, symbol, timeframe, "
            " force_usd, force_gbp, force_eur, force_jpy, force_cad, "
            " force_chf, force_aud, force_nzd, mid, stale, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snap_id, "v9", now, "GBPUSD", "M5",
             50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0,
             1.2700, 0, now),
        )
        conn.commit()
        engine.db_path = db_path

        try:
            result = engine._load_shared_context(conn, snap_id)
        finally:
            conn.close()

        context = result["context"]

        # 4) Vérification : 5 champs présents, types cohérents.
        for key in ("news_type", "news_phase", "news_distance_min",
                    "news_importance", "news_session_clean"):
            assert key in context, f"Champ manquant : {key}"

        # news_phase ∈ vocabulaires autorisés.
        assert context["news_phase"] in {"PRE_NEWS", "NEWS_SHOCK", "POST_NEWS", "NEUTRE"}
        # news_importance ∈ vocabulaires autorisés.
        assert context["news_importance"] in {"HIGH", "MEDIUM", "LOW", "NEUTRE"}
        # news_session_clean toujours bool.
        assert isinstance(context["news_session_clean"], bool)
        # news_type str ou None.
        assert context["news_type"] is None or isinstance(context["news_type"], str)
        # news_distance_min int ou None.
        assert (
            context["news_distance_min"] is None
            or isinstance(context["news_distance_min"], int)
        )

        # 5) Cohérence : si news_phase == "NEUTRE", alors distance_min == None.
        if context["news_phase"] == "NEUTRE":
            assert context["news_distance_min"] is None
            assert context["news_type"] is None
