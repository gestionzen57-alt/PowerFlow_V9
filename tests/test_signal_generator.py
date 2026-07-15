"""Tests unitaires — SignalGenerator (couche Décision, Phase 9) PowerFlow V9."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.mtf_confirmation_db import MTF_CONFIRMATIONS_COLUMNS, init_mtf_confirmation_db
from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS, init_principle_db
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db
from core.v9.signal_generator import SignalGenerator, SignalGeneratorError, SymbolCurrencies
from core.v9.window_db import WINDOWS_COLUMNS, init_window_db


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
    init_mtf_confirmation_db(path)
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


def build_chain(
    db_path: Path,
    *,
    symbol: str = "GBPUSD",
    timeframe: str = "M15",
    exploitability_statut: str | None = "exploitable",
    regime_type: str | None = "CASSURE",
    triggered_principles: list[dict] | None = None,
    force_gbp: float = 62.0,
    force_usd: float = 50.0,
) -> str:
    """Construit une chaîne forces -> scene -> behavior -> window ->
    exploitability -> regime_snapshots(base+quote) -> principle_evaluations
    minimale, paramétrable pour exercer chaque filtre du SignalGenerator."""
    snapshot_id = f"v9-sig-{uuid.uuid4().hex[:8]}"
    forces_row = {c: None for c in FORCES_COLUMNS}
    forces_row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T16:00:00.000Z", "source": "MT4_SDI",
        "symbol": symbol, "timeframe": timeframe, "bar_time": 1, "is_closed_bar": True,
        "force_usd": force_usd, "force_gbp": force_gbp, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "stale": False, "created_at": "2026-07-05T16:00:00.100Z",
    })
    _insert_row(db_path, "forces_snapshots", FORCES_COLUMNS, forces_row)

    currencies = SymbolCurrencies.from_symbol(symbol)

    if exploitability_statut is not None:
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
        scene_row = {c: None for c in SCENES_COLUMNS}
        scene_row.update({
            "scene_id": scene_id, "schema_version": "1.0", "timestamp": "2026-07-05T16:00:00.000Z",
            "timeframes_concernes": timeframe, "forces_snapshot_ref": snapshot_id,
            "coalitions_json": "[]", "antagonismes_json": "[]", "stale": False,
            "created_at": "2026-07-05T16:00:00.200Z",
        })
        _insert_row(db_path, "scenes", SCENES_COLUMNS, scene_row)

        behavior_id = f"beh-{uuid.uuid4().hex[:8]}"
        behavior_row = {c: None for c in BEHAVIOR_COLUMNS}
        behavior_row.update({
            "behavior_id": behavior_id, "schema_version": "1.0", "timestamp": "2026-07-05T16:00:00.000Z",
            "scene_id_ref": scene_id, "symbol": symbol, "timeframe": timeframe,
            "qualification": "bascule", "intensite": "moderee", "phase": "developpement",
            "confiance_qualification": 70, "point_de_rupture_detecte": False,
            "stale": False, "created_at": "2026-07-05T16:00:00.300Z",
        })
        _insert_row(db_path, "behaviors", BEHAVIOR_COLUMNS, behavior_row)

        window_id = f"win-{uuid.uuid4().hex[:8]}"
        window_row = {c: None for c in WINDOWS_COLUMNS}
        window_row.update({
            "window_id": window_id, "schema_version": "1.0", "timestamp": "2026-07-05T16:00:00.000Z",
            "behavior_id": behavior_id, "behavior_qualification": "bascule", "behavior_confiance": 70,
            "statut": "ouverte", "niveau_confiance": 70, "fragilite_detectee": False,
            "conditions_invalidation_json": "[]", "stale": False, "created_at": "2026-07-05T16:00:00.400Z",
        })
        _insert_row(db_path, "windows", WINDOWS_COLUMNS, window_row)

        exploitability_id = f"exp-{uuid.uuid4().hex[:8]}"
        exploitability_row = {c: None for c in EXPLOITABILITY_COLUMNS}
        exploitability_row.update({
            "exploitability_id": exploitability_id, "schema_version": "1.0",
            "timestamp": "2026-07-05T16:00:00.000Z", "window_id": window_id,
            "window_statut": "ouverte", "window_niveau_confiance": 70,
            "statut": exploitability_statut, "niveau_confiance_global": 78,
            "validation_hitl_requise": False, "replay_nombre_cas": 0,
            "stale": False, "created_at": "2026-07-05T16:00:00.500Z",
        })
        _insert_row(db_path, "exploitability", EXPLOITABILITY_COLUMNS, exploitability_row)

    if regime_type is not None:
        for currency in (currencies.base, currencies.quote):
            regime_row = {c: None for c in REGIME_SNAPSHOTS_COLUMNS}
            regime_row.update({
                "regime_id": f"regime-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
                "timestamp": "2026-07-05T16:00:00.000Z", "forces_snapshot_ref": snapshot_id,
                "symbol": symbol, "timeframe": timeframe, "currency": currency,
                "force_value": 62.0, "regime_type": regime_type, "mean_reversion_zone": False,
                "stale": False, "created_at": "2026-07-05T16:00:00.600Z",
            })
            _insert_row(db_path, "regime_snapshots", REGIME_SNAPSHOTS_COLUMNS, regime_row)

    for i, p in enumerate(triggered_principles or []):
        row = {c: None for c in PRINCIPLE_EVALUATIONS_COLUMNS}
        row.update({
            "evaluation_id": f"peval-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
            "timestamp": "2026-07-05T16:00:00.000Z", "snapshot_id": snapshot_id,
            "principle_id": p.get("principle_id", f"P{i}"), "v9_status": p.get("v9_status", "ACTIVE"),
            "kind": "node_rule", "symbol": symbol, "timeframe": timeframe,
            "currency": p.get("currency", currencies.base),
            "triggered": p.get("triggered", True), "direction": p.get("direction", "haussiere"),
            "confidence": p.get("confidence", 70), "anti_signal_bias": False,
            "reason": "conditions_remplies", "context_json": "{}",
            "created_at": "2026-07-05T16:00:00.700Z",
        })
        _insert_row(db_path, "principle_evaluations", PRINCIPLE_EVALUATIONS_COLUMNS, row)

    return snapshot_id


# ── SymbolCurrencies ───────────────────────────────────────
def test_symbol_currencies_parses_base_and_quote():
    c = SymbolCurrencies.from_symbol("GBPUSD")
    assert c.base == "GBP"
    assert c.quote == "USD"


def test_symbol_currencies_raises_on_short_symbol():
    from core.v9.signal_generator import SignalGeneratorError as Err
    with pytest.raises(Err):
        SymbolCurrencies.from_symbol("GB")


# ── Filtres d'absence ──────────────────────────────────────
def test_no_signal_when_no_exploitability_chain(db_path: Path):
    snapshot_id = build_chain(db_path, exploitability_statut=None, regime_type="CASSURE")
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] is None
    assert signal["raison_absence"].startswith("exploitabilite_non_exploitable")


def test_no_signal_when_exploitability_not_exploitable(db_path: Path):
    snapshot_id = build_chain(db_path, exploitability_statut="watchlist", regime_type="CASSURE")
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] is None
    assert "watchlist" in signal["raison_absence"]


def test_no_signal_when_regime_inadequate(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="PALIER",
        triggered_principles=[{"principle_id": "X"}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] is None
    assert signal["raison_absence"].startswith("regime_inadequat")


def test_no_signal_when_regime_missing(db_path: Path):
    snapshot_id = build_chain(db_path, exploitability_statut="exploitable", regime_type=None)
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"].startswith("regime_inadequat")


def test_no_signal_when_no_active_principle_triggered(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] == "aucun_principe_actif_declenche"


def test_shadow_principle_triggered_is_ignored(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "SHADOW_ONE", "v9_status": "SHADOW"}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] == "aucun_principe_actif_declenche"


# ── Signal actif ───────────────────────────────────────────
def test_active_signal_when_conditions_met(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "direction": "haussiere", "confidence": 80}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] is None
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 80
    assert signal["principes_source"] == ["P1"]


def test_direction_majority_vote(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "P1", "direction": "haussiere", "confidence": 70},
            {"principle_id": "P2", "direction": "haussiere", "confidence": 60},
            {"principle_id": "P3", "direction": "baissiere", "confidence": 90},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == round((70 + 60 + 90) / 3)


def test_direction_tie_resolves_to_neutre(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "P1", "direction": "haussiere", "confidence": 70},
            {"principle_id": "P2", "direction": "baissiere", "confidence": 70},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "neutre"


def test_horizon_court_terme_above_threshold(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "confidence": 90}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["horizon"] == "court_terme"


def test_horizon_surveillance_below_threshold(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "confidence": 30}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["horizon"] == "surveillance"


def test_principes_source_sorted_and_unique(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "ZULU", "confidence": 70},
            {"principle_id": "ALPHA", "confidence": 70},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["principes_source"] == ["ALPHA", "ZULU"]


def test_signal_persisted_to_db(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "confidence": 70}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM signals WHERE signal_id = ?", (signal["signal_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_missing_forces_snapshot_raises(db_path: Path):
    with pytest.raises(SignalGeneratorError):
        SignalGenerator(db_path=db_path).generate("does-not-exist")


def test_stale_flag_propagated(db_path: Path):
    snapshot_id = f"v9-sig-{uuid.uuid4().hex[:8]}"
    forces_row = {c: None for c in FORCES_COLUMNS}
    forces_row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T16:00:00.000Z", "source": "MT4_SDI",
        "symbol": "GBPUSD", "timeframe": "M15", "bar_time": 1, "is_closed_bar": True,
        "force_usd": 50.0, "force_gbp": 62.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "stale": True, "created_at": "2026-07-05T16:00:00.100Z",
    })
    _insert_row(db_path, "forces_snapshots", FORCES_COLUMNS, forces_row)
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["stale"] is True


# ── Gap pipeline : principe déclenché sur devise tierce (NZD) ─────
def test_signal_generates_when_principle_currency_is_symbol(db_path: Path):
    """Un principe déclenché avec currency=NZD sur GBPUSD reste visible dans
    principes_source (régression du gap pipeline live 2026-07-07, doctrine
    de visibilité multi-devise préservée). Mise à jour 2026-07-15 : NZD
    n'a plus le droit de VOTER la direction de la paire (aucun mapping
    directionnel valide GBPUSD<->NZD) — direction retombe sur le fallback
    (vote vide, spread sous le seuil ici) plutôt que sur la valeur brute
    NZD. Voir test_third_currency_principle_never_votes_direction pour la
    régression ciblée sur le vote."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{
            "principle_id": "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
            "currency": "NZD", "direction": "haussiere", "confidence": 100,
        }],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] is None
    assert signal["direction"] == "neutre"
    assert signal["confiance"] == 100
    assert "POWER_ANGLE_BREAK_TO_PRICE_IMPACT" in signal["principes_source"]


def test_third_currency_principle_never_votes_direction(db_path: Path):
    """Régression 2026-07-15 (audit régime GBPUSD, suite) : un principe
    déclenché sur une devise tierce (NZD) ne doit jamais faire pencher la
    direction de GBPUSD — même avec une confiance maximale et malgré un
    vote GBP (base) minoritaire dans l'autre sens. Cas réel observé :
    snapshot GBPUSD M15 17:15 UTC 15/07, 4 votes "baissiere" sur NZD
    dominaient le vote alors que GBP montait de +157 pips sur la journée."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "NZD_1", "currency": "NZD", "direction": "baissiere", "confidence": 100},
            {"principle_id": "NZD_2", "currency": "NZD", "direction": "baissiere", "confidence": 100},
            {"principle_id": "NZD_3", "currency": "NZD", "direction": "baissiere", "confidence": 100},
            {"principle_id": "GBP_1", "currency": "GBP", "direction": "haussiere", "confidence": 60},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert set(signal["principes_source"]) == {"NZD_1", "NZD_2", "NZD_3", "GBP_1"}


def test_quote_currency_principle_direction_is_inverted(db_path: Path):
    """USD (quote de GBPUSD) haussiere = USD se renforce = GBPUSD baissier.
    Le vote doit inverser la direction brute de la devise quote."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "USD_1", "currency": "USD", "direction": "haussiere", "confidence": 80},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "baissiere"


def test_signal_deduplicates_principles_across_currencies(db_path: Path):
    """Même principle_id déclenché sur base et quote ne doit apparaître
    qu'une seule fois dans principes_source."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "P1", "currency": "GBP", "direction": "haussiere", "confidence": 80},
            {"principle_id": "P1", "currency": "USD", "direction": "haussiere", "confidence": 80},
        ],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] is None
    assert signal["principes_source"] == ["P1"]


def test_signal_absent_when_truly_no_principle(db_path: Path):
    """Aucun principe triggered=1 → raison_absence canonique."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] == "aucun_principe_actif_declenche"
    assert signal["direction"] is None


# ── Fallback forces sur vote vide (fix 2026-07-15, audit régime GBPUSD) ──
# Cas réel : seuls des principes grammar (direction=None, descriptifs) se
# déclenchent, le vote directionnel est vide, direction retombait à
# "neutre" malgré un spread GBP-USD sans ambiguïté (+157 pips le 15/07).
def test_forces_fallback_direction_when_vote_empty_and_spread_large(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "GRAMMAR_X", "direction": None, "confidence": None},
        ],
        force_gbp=90.0, force_usd=20.0,  # spread = +70
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["raison_absence"] is None
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 70


def test_forces_fallback_baissiere_direction(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "GRAMMAR_X", "direction": None, "confidence": None},
        ],
        force_gbp=15.0, force_usd=85.0,  # spread = -70
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "baissiere"
    assert signal["confiance"] == 70


def test_forces_fallback_not_applied_below_threshold(db_path: Path):
    """Spread < SIGNAL_FORCES_FALLBACK_SPREAD_MIN (20) : reste neutre, le
    fallback ne force jamais une direction sur un déséquilibre ambigu."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "GRAMMAR_X", "direction": None, "confidence": None},
        ],
        force_gbp=58.0, force_usd=50.0,  # spread = +8
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "neutre"


def test_forces_fallback_never_overrides_real_tie(db_path: Path):
    """Un vote réellement partagé entre principes ACTIVE (haussiere vs
    baissiere) reste neutre même avec un spread massif — le fallback ne
    tranche jamais un désaccord entre principes, seulement une absence de
    vote directionnel."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[
            {"principle_id": "P1", "direction": "haussiere", "confidence": 70},
            {"principle_id": "P2", "direction": "baissiere", "confidence": 70},
        ],
        force_gbp=95.0, force_usd=10.0,  # spread = +85
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "neutre"


# ── MTF Confirmation Engine — propagation du confidence_boost ──────────
def _insert_mtf(db_path: Path, *, forces_snapshot_ref: str, direction: str,
                 aligned: bool, conflict: bool, confidence_boost: int) -> None:
    row = {c: None for c in MTF_CONFIRMATIONS_COLUMNS}
    row.update({
        "mtf_id": f"mtf-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T16:00:00.000Z", "forces_snapshot_ref": forces_snapshot_ref,
        "symbol": "GBPUSD", "trigger_tf": "M15", "context_tf": "H4",
        "mtf_setup": "sortie_zone_h4_croisement_m15" if aligned else "conflict",
        "aligned": aligned, "conflict": conflict, "confidence_boost": confidence_boost,
        "direction": direction, "reason": "test", "source_type": "live",
        "created_at": "2026-07-05T16:00:00.000Z",
    })
    _insert_row(db_path, "mtf_confirmations", MTF_CONFIRMATIONS_COLUMNS, row)


def test_mtf_boost_applied_when_direction_aligned(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "direction": "haussiere", "confidence": 60}],
    )
    _insert_mtf(
        db_path, forces_snapshot_ref=snapshot_id, direction="haussiere",
        aligned=True, conflict=False, confidence_boost=25,
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 85  # 60 + 25


def test_mtf_malus_applied_on_conflict_with_same_direction(db_path: Path):
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "direction": "haussiere", "confidence": 60}],
    )
    _insert_mtf(
        db_path, forces_snapshot_ref=snapshot_id, direction="haussiere",
        aligned=False, conflict=True, confidence_boost=-15,
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 45  # 60 - 15


def test_mtf_boost_ignored_when_direction_mismatch(db_path: Path):
    """Le boost MTF ne s'applique que si la direction MTF matche la
    direction déjà déterminée par le vote — un MTF sur une autre direction
    ne doit avoir aucun effet."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "direction": "haussiere", "confidence": 60}],
    )
    _insert_mtf(
        db_path, forces_snapshot_ref=snapshot_id, direction="baissiere",
        aligned=True, conflict=False, confidence_boost=25,
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 60


def test_signal_generation_unaffected_when_no_mtf_row(db_path: Path):
    """Absence de ligne mtf_confirmations (table vide, pas de MTF évalué)
    -> comportement pré-MTF inchangé (R2 additif)."""
    snapshot_id = build_chain(
        db_path, exploitability_statut="exploitable", regime_type="CASSURE",
        triggered_principles=[{"principle_id": "P1", "direction": "haussiere", "confidence": 60}],
    )
    signal = SignalGenerator(db_path=db_path).generate(snapshot_id)
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 60
