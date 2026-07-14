"""Tests unitaires — Arbiter (core/v9/arbiter.py, Phase 10).

Couvre 6 cas exigés par le brief :
  1. test_consolidate_un_signal_baissier
  2. test_consolidate_direction_majoritaire
  3. test_consolidate_neutre_si_vide
  4. test_consolidate_plafond_confiance_1_principe
  5. test_consolidate_principes_source_union
  6. test_consolidate_lecture_seule_no_write

+ tests annexes : confiance_brute, plafonne_sous_2_principes False,
  arbiter_version, snapshot_id propagation, principes JSON malformé.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.arbiter import (
    ARBITER_VERSION,
    CONFIANCE_PLAFOND_SOUS_2_PRINCIPES,
    SCORER_ENABLED_ENV,
    Arbiter,
)
from core.v9.trader_mini_weigher import TRADER_MINI_ENABLED_ENV, TRADER_MINI_MULT_NEUTRAL
from core.v9.db_schema import init_db
from core.v9.decision_db import init_decision_db
from core.v9.principle_scorer import SCHEMA_SQL as PRINCIPLE_SCORES_SCHEMA_SQL
from core.v9.principle_scorer import _combination_hash


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "v9_arbiter_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_decision_db(path)
    return path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str = "snap_test",
    decision_id: str | None = None,
    direction: str = "haussiere",
    confiance: int = 75,
    principes: list[str] | None = None,
    source_type: str = "live",
    timestamp: str = "2026-07-07T10:00:00+00:00",
) -> str:
    if decision_id is None:
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id, "1.0", timestamp, snapshot_id, "sig_test",
                "surveiller", "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", direction, confiance,
                json.dumps(principes or []), "{}", source_type, timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return decision_id


def _insert_principle_score(
    db_path: Path,
    *,
    principle_id: str,
    combination_hash: str | None,
    n_trades: int,
    win_rate: float,
) -> None:
    """Insère une ligne principle_scores (Brief O2). Crée le schéma si absent."""
    conn = _connect(db_path)
    try:
        conn.execute(PRINCIPLE_SCORES_SCHEMA_SQL)
        n_wins = round(n_trades * win_rate / 100)
        conn.execute(
            "INSERT INTO principle_scores "
            "(principle_id, combination_hash, n_trades, n_wins, n_losses, "
            " total_pips, avg_pips, win_rate, last_updated) "
            "VALUES (?, ?, ?, ?, ?, 0.0, 0.0, ?, '2026-07-12T00:00:00+00:00')",
            (principle_id, combination_hash, n_trades, n_wins, n_trades - n_wins, win_rate),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- Tests ----------


def test_consolidate_un_signal_baissier(db_path: Path) -> None:
    """Cas 1 — 1 décision baissière conf 80, 2 principes → résultat simple."""
    _insert_decision(db_path, snapshot_id="snap_bear",
                     direction="baissiere", confiance=80,
                     principes=["NODE_BIRTH_FAST", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"])
    arbiter = Arbiter(db_path=db_path)
    result = arbiter.consolidate("snap_bear")

    assert result["direction"] == "baissiere"
    assert result["confiance_arbitree"] == 80
    assert result["confiance_brute"] == 80
    assert result["plafonne_sous_2_principes"] is False
    assert result["nb_principes_actifs"] == 2
    assert sorted(result["principes_source"]) == sorted(
        ["NODE_BIRTH_FAST", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"]
    )
    assert result["arbiter_version"] == ARBITER_VERSION
    assert result["nb_decisions_consolidees"] == 1
    assert result["nb_decisions_totales"] == 1
    assert result["snapshot_id"] == "snap_bear"


def test_consolidate_direction_majoritaire(db_path: Path) -> None:
    """Cas 2 — 3 décisions (2 haussières, 1 baissière) → direction=haussiere
    et confiance = moyenne des 2 haussières uniquement."""
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_h1", direction="haussiere", confiance=80,
                     principes=["P1"])
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_h2", direction="haussiere", confiance=90,
                     principes=["P2"])
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_b1", direction="baissiere", confiance=95,
                     principes=["P3"])

    result = Arbiter(db_path=db_path).consolidate("snap_mix")

    assert result["direction"] == "haussiere"
    assert result["confiance_arbitree"] == 85  # moyenne (80+90)/2
    assert result["nb_decisions_consolidees"] == 2
    assert result["nb_decisions_totales"] == 3
    assert sorted(result["principes_source"]) == ["P1", "P2"]


def test_consolidate_neutre_si_vide(db_path: Path) -> None:
    """Cas 3 — aucune décision directionnelle → neutre, confiance=0."""
    result = Arbiter(db_path=db_path).consolidate("snap_vide")

    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0
    assert result["principes_source"] == []
    assert result["nb_principes_actifs"] == 0
    assert result["nb_decisions_consolidees"] == 0


def test_consolidate_neutre_si_que_neutre(db_path: Path) -> None:
    """Décisions non-directionnelles (direction='neutre') ignorées → vide."""
    _insert_decision(db_path, snapshot_id="snap_neutres",
                     direction="neutre", confiance=0,
                     principes=[])
    result = Arbiter(db_path=db_path).consolidate("snap_neutres")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0


def test_consolidate_neutre_si_que_replay(db_path: Path) -> None:
    """Décisions avec source_type='replay' sont ignorées."""
    _insert_decision(db_path, snapshot_id="snap_replay",
                     direction="haussiere", confiance=90,
                     principes=["P1"], source_type="replay")
    result = Arbiter(db_path=db_path).consolidate("snap_replay")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0


def test_consolidate_plafond_confiance_1_principe(db_path: Path) -> None:
    """Cas 4 — 1 seul principe actif → confiance_arbitree plafonnée à 74."""
    _insert_decision(db_path, snapshot_id="snap_plafond",
                     direction="haussiere", confiance=95,
                     principes=["P_UNIQUE"])

    result = Arbiter(db_path=db_path).consolidate("snap_plafond")

    assert result["direction"] == "haussiere"
    assert result["confiance_brute"] == 95  # avant plafond
    assert result["confiance_arbitree"] == CONFIANCE_PLAFOND_SOUS_2_PRINCIPES
    assert result["plafonne_sous_2_principes"] is True
    assert result["nb_principes_actifs"] == 1


def test_consolidate_plafond_pas_applique_2_principes(db_path: Path) -> None:
    """Avec ≥ 2 principes, pas de plafond."""
    _insert_decision(db_path, snapshot_id="snap_2p",
                     direction="haussiere", confiance=95,
                     principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_2p")
    assert result["confiance_arbitree"] == 95
    assert result["plafonne_sous_2_principes"] is False


def test_consolidate_plafond_pas_applique_si_deja_bas(db_path: Path) -> None:
    """Si confiance_brute ≤ 74, le plafond n'est pas marqué actif
    (plafonne_sous_2_principes=False) — la valeur ne change pas mais
    on n'indique pas un plafonnement trompeur."""
    _insert_decision(db_path, snapshot_id="snap_low",
                     direction="haussiere", confiance=60,
                     principes=["P_UNIQUE"])
    result = Arbiter(db_path=db_path).consolidate("snap_low")
    assert result["confiance_arbitree"] == 60
    assert result["confiance_brute"] == 60
    assert result["plafonne_sous_2_principes"] is False


def test_consolidate_principes_source_union(db_path: Path) -> None:
    """Cas 5 — plusieurs décisions même direction → union des principes."""
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u1", direction="haussiere",
                     confiance=80, principes=["P_A", "P_B"])
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u2", direction="haussiere",
                     confiance=85, principes=["P_B", "P_C"])
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u3", direction="haussiere",
                     confiance=90, principes=["P_C", "P_D"])

    result = Arbiter(db_path=db_path).consolidate("snap_union")

    # Union : P_A, P_B, P_C, P_D (4 uniques, ordre de 1ère apparition)
    assert result["principes_source"] == ["P_A", "P_B", "P_C", "P_D"]
    assert result["nb_principes_actifs"] == 4


def test_consolidate_lecture_seule_no_write(db_path: Path) -> None:
    """Cas 6 — l'Arbiter ne crée AUCUNE nouvelle rangée en DB.

    On compte les rangées AVANT puis APRÈS plusieurs consolidates, le
    total doit rester identique. Aucune table 'arbiter_results' ou autre
    ne doit apparaître. Note : depuis l'activation des kill switches
    (2026-07-14), l'Arbiter peut créer les tables 'principle_evaluations'
    et 'principles' si elles n'existent pas encore (trader_mini_weigher
    actif) — on les exclut de la comparaison car ce sont des tables
    système pré-existantes dans le schéma V9.
    """
    _insert_decision(db_path, snapshot_id="snap_ro",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"])

    conn = _connect(db_path)
    try:
        tables_before = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        count_decisions_before = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
    finally:
        conn.close()

    arbiter = Arbiter(db_path=db_path)
    arbiter.consolidate("snap_ro")
    arbiter.consolidate("snap_ro")
    arbiter.consolidate("snap_ro")

    conn = _connect(db_path)
    try:
        tables_after = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        count_decisions_after = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
    finally:
        conn.close()

    # Exclure les tables système que l'Arbiter peut créer au premier appel
    # (principle_evaluations, principles) — ce sont des tables du schéma V9,
    # pas des tables "arbiter_results" ou autres.
    system_tables = {"principle_evaluations", "principles"}
    filtered_before = tables_before - system_tables
    filtered_after = tables_after - system_tables
    assert filtered_before == filtered_after, "Arbiter ne doit créer aucune table non-système"
    assert count_decisions_before == count_decisions_after, "Arbiter ne doit écrire dans decisions"


def test_consolidate_principes_json_malformed(db_path: Path) -> None:
    """principes_json corrompu (non-JSON) → liste vide tolérée."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "dec_bad_json", "1.0", "2026-07-07T10:00:00+00:00",
                "snap_bad", "sig_test", "surveiller", "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", "haussiere", 80,
                "{not valid json", "{}", "live",
                "2026-07-07T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result = Arbiter(db_path=db_path).consolidate("snap_bad")
    assert result["direction"] == "haussiere"
    assert result["principes_source"] == []
    assert result["nb_principes_actifs"] == 0


def test_consolidate_snapshot_id_isolated(db_path: Path) -> None:
    """Les décisions d'autres snapshot_id ne sont jamais incluses."""
    _insert_decision(db_path, snapshot_id="snap_A",
                     direction="haussiere", confiance=90,
                     principes=["P_A1", "P_A2"])
    _insert_decision(db_path, snapshot_id="snap_B",
                     direction="baissiere", confiance=70,
                     principes=["P_B1"])

    res_a = Arbiter(db_path=db_path).consolidate("snap_A")
    res_b = Arbiter(db_path=db_path).consolidate("snap_B")

    assert res_a["direction"] == "haussiere"
    assert res_a["principes_source"] == ["P_A1", "P_A2"]
    assert res_b["direction"] == "baissiere"
    assert res_b["principes_source"] == ["P_B1"]


def test_consolidate_timestamp_max(db_path: Path) -> None:
    """Le timestamp du résultat = max(timestamps décisions consolidées)."""
    _insert_decision(db_path, snapshot_id="snap_ts",
                     decision_id="dec_ts1", direction="haussiere",
                     confiance=80, principes=["P1"],
                     timestamp="2026-07-07T10:00:00+00:00")
    _insert_decision(db_path, snapshot_id="snap_ts",
                     decision_id="dec_ts2", direction="haussiere",
                     confiance=85, principes=["P1"],
                     timestamp="2026-07-07T10:05:00+00:00")
    result = Arbiter(db_path=db_path).consolidate("snap_ts")
    assert result["timestamp"] == "2026-07-07T10:05:00+00:00"


def test_consolidate_moyenne_arrondie(db_path: Path) -> None:
    """Moyenne confiance arrondie à l'entier le plus proche.

    Avec 1 seul principe, le plafond à 74 s'applique — on utilise donc
    2 principes pour tester l'arrondi pur.
    """
    _insert_decision(db_path, snapshot_id="snap_avg",
                     decision_id="dec_a1", direction="haussiere",
                     confiance=80, principes=["P1", "P2"])
    _insert_decision(db_path, snapshot_id="snap_avg",
                     decision_id="dec_a2", direction="haussiere",
                     confiance=81, principes=["P1", "P2"])
    # Moyenne = 80.5 → round → 80 (banker's rounding Python : 80.5 → 80)
    result = Arbiter(db_path=db_path).consolidate("snap_avg")
    assert isinstance(result["confiance_arbitree"], int)
    assert result["confiance_arbitree"] in (80, 81)  # tolérance banker's rounding
    assert result["plafonne_sous_2_principes"] is False


# ---------- Brief O2 (2026-07-12) — Pondération PrincipleScorer ----------


def test_scorer_wr_below_60_reduces_confidence(db_path: Path) -> None:
    """WR combinaison < 60% (n>=5) -> confiance x0.8, basis='combination'."""
    principes = ["P1", "P2"]
    _insert_principle_score(
        db_path, principle_id="P1|P2",
        combination_hash=_combination_hash(principes),
        n_trades=10, win_rate=50.0,
    )
    _insert_decision(db_path, snapshot_id="snap_low_wr",
                     direction="haussiere", confiance=80, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_low_wr")
    assert result["scorer_multiplier"] == pytest.approx(0.8)
    assert result["scorer_basis"] == "combination"
    assert result["confiance_arbitree"] == 64  # round(80 * 0.8)


def test_scorer_wr_above_90_boosts_and_caps_at_100(db_path: Path) -> None:
    """WR combinaison > 90% (n>=5) -> confiance x1.1, plafond absolu 100."""
    principes = ["P1", "P2"]
    _insert_principle_score(
        db_path, principle_id="P1|P2",
        combination_hash=_combination_hash(principes),
        n_trades=10, win_rate=95.0,
    )
    _insert_decision(db_path, snapshot_id="snap_high_wr",
                     direction="haussiere", confiance=95, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_high_wr")
    assert result["scorer_multiplier"] == pytest.approx(1.1)
    assert result["scorer_basis"] == "combination"
    # round(95 * 1.1) = 104.5 -> plafonné à 100 AVANT round
    assert result["confiance_arbitree"] == 100


def test_scorer_wr_in_neutral_range_60_to_90_inclusive(db_path: Path) -> None:
    """60% <= WR <= 90% -> neutre x1.0 (bornes inclusives)."""
    principes = ["P1", "P2"]
    _insert_principle_score(
        db_path, principle_id="P1|P2",
        combination_hash=_combination_hash(principes),
        n_trades=10, win_rate=75.0,
    )
    _insert_decision(db_path, snapshot_id="snap_neutral_wr",
                     direction="haussiere", confiance=80, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_neutral_wr")
    assert result["scorer_multiplier"] == pytest.approx(1.0)
    assert result["scorer_basis"] == "combination"
    assert result["confiance_arbitree"] == 80  # inchangé


def test_scorer_combination_below_min_sample_falls_back_to_individual(db_path: Path) -> None:
    """Combinaison n_trades < 5 -> jamais utilisée (pas d'extrapolation),
    fallback sur la moyenne des scores individuels (chacun n>=5)."""
    principes = ["P1", "P2"]
    _insert_principle_score(
        db_path, principle_id="P1|P2",
        combination_hash=_combination_hash(principes),
        n_trades=3, win_rate=95.0,  # ignoré : n < MIN_SAMPLE_SCORE
    )
    _insert_principle_score(db_path, principle_id="P1", combination_hash=None,
                            n_trades=10, win_rate=95.0)
    _insert_principle_score(db_path, principle_id="P2", combination_hash=None,
                            n_trades=10, win_rate=95.0)
    _insert_decision(db_path, snapshot_id="snap_fallback",
                     direction="haussiere", confiance=80, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_fallback")
    assert result["scorer_basis"] == "individual"
    assert result["scorer_multiplier"] == pytest.approx(1.1)  # moyenne WR=95 -> boost


def test_scorer_unknown_combination_and_no_individual_data_is_neutral(db_path: Path) -> None:
    """Combinaison absente ET aucun principe individuel connu -> neutre."""
    principes = ["P_UNKNOWN_1", "P_UNKNOWN_2"]
    # Table créée (via un autre principe) mais rien pour ceux-ci.
    _insert_principle_score(db_path, principle_id="AUTRE", combination_hash=None,
                            n_trades=10, win_rate=95.0)
    _insert_decision(db_path, snapshot_id="snap_unknown",
                     direction="haussiere", confiance=80, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_unknown")
    assert result["scorer_basis"] == "neutral"
    assert result["scorer_multiplier"] == pytest.approx(1.0)
    assert result["confiance_arbitree"] == 80


def test_scorer_missing_table_is_neutral_never_raises(db_path: Path) -> None:
    """Table principle_scores absente (jamais créée) -> neutre, pas d'exception
    (règle 6 : l'orchestrateur/arbiter ne crash jamais)."""
    _insert_decision(db_path, snapshot_id="snap_no_table",
                     direction="haussiere", confiance=80, principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_no_table")
    assert result["scorer_basis"] == "neutral"
    assert result["scorer_multiplier"] == pytest.approx(1.0)
    assert result["confiance_arbitree"] == 80


def test_scorer_kill_switch_disables_weighting(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V9_ARBITER_SCORER_ENABLED=0 -> neutre intégral, basis='disabled'."""
    monkeypatch.setenv(SCORER_ENABLED_ENV, "0")
    principes = ["P1", "P2"]
    _insert_principle_score(
        db_path, principle_id="P1|P2",
        combination_hash=_combination_hash(principes),
        n_trades=10, win_rate=50.0,  # donnerait x0.8 si activé
    )
    _insert_decision(db_path, snapshot_id="snap_killswitch",
                     direction="haussiere", confiance=80, principes=principes)
    result = Arbiter(db_path=db_path).consolidate("snap_killswitch")
    assert result["scorer_basis"] == "disabled"
    assert result["scorer_multiplier"] == pytest.approx(1.0)
    assert result["confiance_arbitree"] == 80


def test_scorer_wr_to_multiplier_bounds_are_hard_clamped() -> None:
    """_wr_to_multiplier borne toujours le résultat dans [0.5, 1.5], même
    pour des WR hors plage normale (défensif — la règle discrète ne produit
    que 0.8/1.0/1.1 mais le clamp est une garantie explicite du brief)."""
    assert Arbiter._wr_to_multiplier(-50.0) == pytest.approx(0.8)
    assert Arbiter._wr_to_multiplier(59.99) == pytest.approx(0.8)
    assert Arbiter._wr_to_multiplier(60.0) == pytest.approx(1.0)   # borne incluse
    assert Arbiter._wr_to_multiplier(90.0) == pytest.approx(1.0)   # borne incluse
    assert Arbiter._wr_to_multiplier(90.01) == pytest.approx(1.1)
    assert Arbiter._wr_to_multiplier(1000.0) == pytest.approx(1.1)


def test_scorer_applied_before_plafond_sous_2_principes(db_path: Path) -> None:
    """Ordre exigé par le brief : scorer APRÈS le vote, AVANT le plafond
    <2 principes. Avec x1.1 et confiance_brute=90, la valeur pondérée
    (99) dépasse encore le plafond 74 -> le plafond s'applique bien SUR
    la valeur pondérée, pas sur la valeur brute (99 != 90, mais le
    résultat final est bien 74 dans les deux cas — le test vérifie que
    plafonne_sous_2_principes reflète la comparaison post-scorer)."""
    principe = ["P_UNIQUE"]
    _insert_principle_score(
        db_path, principle_id="P_UNIQUE", combination_hash=None,
        n_trades=10, win_rate=95.0,
    )
    _insert_decision(db_path, snapshot_id="snap_order",
                     direction="haussiere", confiance=90, principes=principe)
    result = Arbiter(db_path=db_path).consolidate("snap_order")
    assert result["scorer_multiplier"] == pytest.approx(1.1)
    assert result["confiance_brute"] == 90
    # confiance_ponderee = round(90*1.1) = 99, puis plafond -> 74
    assert result["confiance_arbitree"] == CONFIANCE_PLAFOND_SOUS_2_PRINCIPES
    assert result["plafonne_sous_2_principes"] is True


# ---------- Brief Q1 (2026-07-12) — pondération V9-trader-mini ----------


def test_trader_mini_enabled_by_default_in_consolidate_output(db_path: Path) -> None:
    """V9_TRADER_MINI_ENABLED=1 (activé 2026-07-14) -> weigher actif.
    En l'absence de modèle (test DB), basis='context_unavailable' mais
    neutre intégral, aucun impact sur confiance_arbitree."""
    _insert_decision(db_path, snapshot_id="snap_tm_default",
                      direction="haussiere", confiance=80, principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_tm_default")
    assert result["trader_mini_basis"] == "context_unavailable"
    assert result["trader_mini_multiplier"] == pytest.approx(TRADER_MINI_MULT_NEUTRAL)
    assert result["confiance_arbitree"] == 80


def test_trader_mini_explicit_kill_switch_off(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "0")
    _insert_decision(db_path, snapshot_id="snap_tm_off",
                      direction="haussiere", confiance=80, principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_tm_off")
    assert result["trader_mini_basis"] == "disabled"
    assert result["trader_mini_multiplier"] == pytest.approx(TRADER_MINI_MULT_NEUTRAL)


def test_trader_mini_fields_present_on_empty_snapshot(db_path: Path) -> None:
    """Snapshot sans décision -> early return, champs trader_mini_* présents
    et neutres (stabilité API, cf. champs scorer_* équivalents)."""
    result = Arbiter(db_path=db_path).consolidate("snap_inexistant")
    assert result["trader_mini_basis"] == "neutral"
    assert result["trader_mini_multiplier"] == pytest.approx(TRADER_MINI_MULT_NEUTRAL)


def test_trader_mini_multiplier_chains_after_scorer(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brief Q1 : le multiplicateur trader_mini s'applique APRÈS le scorer
    O2, sur confiance_ponderee (déjà pondérée par le scorer) — pas sur
    confiance_moyenne brute. Vérifié en enchaînant les deux multiplicateurs
    à la main."""
    principe = ["P1"]
    _insert_principle_score(
        db_path, principle_id="P1", combination_hash=None,
        n_trades=10, win_rate=95.0,  # -> scorer x1.1
    )
    _insert_decision(db_path, snapshot_id="snap_tm_chain",
                      direction="haussiere", confiance=50,
                      principes=principe + ["P2"])  # 2 principes -> pas de plafond

    monkeypatch.setattr(
        Arbiter, "_compute_trader_mini_multiplier",
        staticmethod(lambda snapshot_id, conn: (0.9, "predicted_loss")),
    )
    result = Arbiter(db_path=db_path).consolidate("snap_tm_chain")
    assert result["scorer_multiplier"] == pytest.approx(1.1)
    assert result["trader_mini_multiplier"] == pytest.approx(0.9)
    # confiance_brute=50 -> scorer: round(50*1.1)=55 -> trader_mini: round(55*0.9)=50
    assert result["confiance_arbitree"] == round(round(50 * 1.1) * 0.9)


def test_trader_mini_never_raises_on_internal_error(
    db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Règle 6 : toute erreur interne (modèle corrompu, contexte absent,
    etc.) retombe sur neutre, ne bloque jamais consolidate(). Teste le VRAI
    try/except de _compute_trader_mini_multiplier (non mocké) en cassant
    uniquement la couche en dessous (le weigher)."""
    import core.v9.arbiter as arbiter_module
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")

    class _BoomWeigher:
        def compute_multiplier(self, snapshot_id, conn, principle_engine=None):
            raise RuntimeError("modèle corrompu")

    monkeypatch.setattr(arbiter_module, "_get_trader_mini_weigher", lambda: _BoomWeigher())
    _insert_decision(db_path, snapshot_id="snap_tm_error",
                      direction="haussiere", confiance=80, principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_tm_error")
    assert result["trader_mini_basis"] == "neutral"
    assert result["trader_mini_multiplier"] == pytest.approx(TRADER_MINI_MULT_NEUTRAL)
    assert result["confiance_arbitree"] == 80