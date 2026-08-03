"""Tests pour v9_news_shock_attenuator.py (Phase 141 — L19 News Shock Attenuator).

Couvre les cas critiques :
1. Kill switch OFF -> pass-through (multiplier=1.0, label=kill_switch_off)
2. minutes_to_news = 30 (pre_news) -> ×0.5
3. minutes_to_news = 5 (imminent / HALT) -> ×0.0
4. minutes_to_news = -10 (post_news) -> ×0.5
5. minutes_to_news = -30 (normalisation) -> ×0.8
6. minutes_to_news = 100 (normal, hors fenetre) -> ×1.0
7. minutes_to_news = -100 (normal, post-fenetre) -> ×1.0
8. Bornes : 60 (frontiere haute pre_news), 15 (frontiere basse pre_news),
   0 (debut imminent), -15 (debut post_news), -60 (debut normalisation)
9. classify_news_window() retourne un dataclass coherent
10. summarize_phase_distribution agrege correctement
11. R6 fail-open : entree invalide (str) -> multiplier=1.0, label=normal
12. Audit SQL live : wide_spread regime (proxy news) doit etre significativement
    moins profitable que normal (justification empirique R14)
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.v9 import v9_news_shock_attenuator as nsa
from core.v9.v9_news_shock_attenuator import (
    MULT_IMMINENT,
    MULT_NORMAL,
    MULT_NORMALISATION,
    MULT_POST_NEWS,
    MULT_PRE_NEWS,
    NewsWindowVerdict,
    classify_news_window,
    get_news_window_multiplier,
    news_shock_attenuator_enabled,
    summarize_phase_distribution,
)


# ── Fixture : kill switch ON pour les tests metier ──────────────────
@pytest.fixture
def nsa_on(monkeypatch):
    """Active le kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED=1."""
    monkeypatch.setenv("V9_NEWS_SHOCK_ATTENUATOR_ENABLED", "1")
    # Invalider le cache process-local du chargeur.
    from core.v9 import kill_switches as ks
    ks._switches = None
    yield
    ks._switches = None


@pytest.fixture
def nsa_off(monkeypatch):
    """Force le kill switch OFF (defaut)."""
    monkeypatch.delenv("V9_NEWS_SHOCK_ATTENUATOR_ENABLED", raising=False)
    from core.v9 import kill_switches as ks
    ks._switches = None
    yield
    ks._switches = None


# ── 1. Kill switch OFF -> pass-through ─────────────────────────────
class TestKillSwitchOff:
    def test_kill_switch_off_returns_1x(self, nsa_off):
        """OFF : toute entree doit retourner (1.0, 'kill_switch_off')."""
        for m in [-120, -60, -30, -15, -1, 0, 5, 15, 30, 60, 120, 1000]:
            mult, label = get_news_window_multiplier(m)
            assert mult == 1.0, f"minutes={m} should be 1.0 (OFF), got {mult}"
            assert label == "kill_switch_off"

    def test_kill_switch_off_helper(self, nsa_off):
        assert news_shock_attenuator_enabled() is False

    def test_classify_returns_kill_switch_off(self, nsa_off):
        v = classify_news_window(30)
        assert v.multiplier == 1.0
        assert v.phase_label == "kill_switch_off"
        assert v.enabled is False
        assert v.minutes_to_news == 30


# ── 2. Logique metier (kill switch ON) ─────────────────────────────
class TestLogic:
    def test_pre_news_30min(self, nsa_on):
        """30 min avant news → ×0.5 (pre_news)."""
        mult, label = get_news_window_multiplier(30)
        assert mult == 0.5
        assert label == "pre_news"

    def test_pre_news_15min_frontiere_basse(self, nsa_on):
        """15 min avant news → encore pre_news (×0.5)."""
        mult, label = get_news_window_multiplier(15)
        assert mult == 0.5
        assert label == "pre_news"

    def test_pre_news_60min_frontiere_haute(self, nsa_on):
        """60 min avant news → encore pre_news (×0.5)."""
        mult, label = get_news_window_multiplier(60)
        assert mult == 0.5
        assert label == "pre_news"

    def test_imminent_5min(self, nsa_on):
        """5 min avant news → ×0.0 (HALT)."""
        mult, label = get_news_window_multiplier(5)
        assert mult == 0.0
        assert label == "imminent"

    def test_imminent_0min(self, nsa_on):
        """0 min (release pile) → ×0.0 (HALT)."""
        mult, label = get_news_window_multiplier(0)
        assert mult == 0.0
        assert label == "imminent"

    def test_post_news_minus_10(self, nsa_on):
        """-10 min (10 min apres release) → ×0.5 (post_news)."""
        mult, label = get_news_window_multiplier(-10)
        assert mult == 0.5
        assert label == "post_news"

    def test_post_news_minus_1(self, nsa_on):
        """-1 min (juste apres release) → ×0.5 (post_news)."""
        mult, label = get_news_window_multiplier(-1)
        assert mult == 0.5
        assert label == "post_news"

    def test_normalisation_minus_30(self, nsa_on):
        """-30 min (30 min apres release) → ×0.8 (normalisation)."""
        mult, label = get_news_window_multiplier(-30)
        assert mult == 0.8
        assert label == "normalisation"

    def test_normalisation_minus_15_frontiere(self, nsa_on):
        """-15 min pile (frontiere post_news) → post_news ×0.5
        (la borne -15 <= m < 0 inclut m=-15 dans post_news selon spec prompt)."""
        mult, label = get_news_window_multiplier(-15)
        assert mult == 0.5
        assert label == "post_news"

    def test_normalisation_minus_16_just_after(self, nsa_on):
        """-16 min (juste apres la frontiere post_news) → normalisation ×0.8."""
        mult, label = get_news_window_multiplier(-16)
        assert mult == 0.8
        assert label == "normalisation"

    def test_normalisation_minus_60_frontiere(self, nsa_on):
        """-60 min (frontiere basse normalisation) → ×0.8."""
        mult, label = get_news_window_multiplier(-60)
        assert mult == 0.8
        assert label == "normalisation"

    def test_normal_100min_avant(self, nsa_on):
        """100 min avant news → ×1.0 (normal)."""
        mult, label = get_news_window_multiplier(100)
        assert mult == 1.0
        assert label == "normal"

    def test_normal_minus_100_apres(self, nsa_on):
        """100 min apres news → ×1.0 (normal)."""
        mult, label = get_news_window_multiplier(-100)
        assert mult == 1.0
        assert label == "normal"

    def test_normal_61min_juste_hors_pre_news(self, nsa_on):
        """61 min avant news → normal (juste au-dessus de la fenetre pre_news)."""
        mult, label = get_news_window_multiplier(61)
        assert mult == 1.0
        assert label == "normal"

    def test_normal_minus_61min_juste_hors_normalisation(self, nsa_on):
        """-61 min (61 min apres release) → normal (juste sous la fenetre)."""
        mult, label = get_news_window_multiplier(-61)
        assert mult == 1.0
        assert label == "normal"


# ── 3. Dataclass classify_news_window ──────────────────────────────
class TestClassify:
    def test_classify_pre_news(self, nsa_on):
        v = classify_news_window(30)
        assert isinstance(v, NewsWindowVerdict)
        assert v.multiplier == 0.5
        assert v.phase_label == "pre_news"
        assert v.enabled is True
        assert v.minutes_to_news == 30

    def test_classify_imminent(self, nsa_on):
        v = classify_news_window(10)
        assert v.multiplier == 0.0
        assert v.phase_label == "imminent"

    def test_classify_post_news(self, nsa_on):
        v = classify_news_window(-5)
        assert v.multiplier == 0.5
        assert v.phase_label == "post_news"

    def test_classify_normal(self, nsa_on):
        v = classify_news_window(200)
        assert v.multiplier == 1.0
        assert v.phase_label == "normal"

    def test_to_dict_roundtrip(self, nsa_on):
        v = classify_news_window(30)
        d = v.to_dict()
        assert d["minutes_to_news"] == 30
        assert d["multiplier"] == 0.5
        assert d["phase_label"] == "pre_news"
        assert d["enabled"] is True


# ── 4. summarize_phase_distribution ────────────────────────────────
class TestSummarize:
    def test_empty(self, nsa_on):
        s = summarize_phase_distribution([])
        assert s["n_total"] == 0
        assert s["multiplier_avg"] == 0.0
        assert s["n_pre_news"] == 0
        assert s["n_imminent"] == 0
        assert s["n_post_news"] == 0
        assert s["n_normalisation"] == 0
        assert s["n_normal"] == 0

    def test_mixed_phases(self, nsa_on):
        verdicts = [
            classify_news_window(30),    # pre_news
            classify_news_window(5),     # imminent
            classify_news_window(-10),   # post_news
            classify_news_window(-30),   # normalisation
            classify_news_window(200),   # normal
        ]
        s = summarize_phase_distribution(verdicts)
        assert s["n_total"] == 5
        assert s["n_pre_news"] == 1
        assert s["n_imminent"] == 1
        assert s["n_post_news"] == 1
        assert s["n_normalisation"] == 1
        assert s["n_normal"] == 1
        # Moyenne : (0.5 + 0.0 + 0.5 + 0.8 + 1.0) / 5 = 0.56
        assert abs(s["multiplier_avg"] - 0.56) < 0.01

    def test_all_kill_switch_off(self, nsa_off):
        verdicts = [classify_news_window(m) for m in [30, 5, -10, 200]]
        s = summarize_phase_distribution(verdicts)
        assert s["n_total"] == 4
        assert s["n_kill_switch_off"] == 4
        assert s["multiplier_avg"] == 1.0


# ── 5. R6 fail-open ────────────────────────────────────────────────
class TestFailOpen:
    def test_str_input_returns_normal(self, nsa_on):
        """Entree str invalide → pass-through normal (R6)."""
        mult, label = get_news_window_multiplier("abc")  # type: ignore[arg-type]
        assert mult == MULT_NORMAL
        assert label == "normal"

    def test_none_input_returns_normal(self, nsa_on):
        mult, label = get_news_window_multiplier(None)  # type: ignore[arg-type]
        assert mult == MULT_NORMAL
        assert label == "normal"

    def test_float_input_truncated(self, nsa_on):
        """Float 30.7 → converti en 30 (pre_news)."""
        mult, label = get_news_window_multiplier(30.7)  # type: ignore[arg-type]
        assert mult == MULT_PRE_NEWS
        assert label == "pre_news"


# ── 6. Constantes API ──────────────────────────────────────────────
class TestConstants:
    def test_multipliers(self):
        assert MULT_PRE_NEWS == 0.5
        assert MULT_IMMINENT == 0.0
        assert MULT_POST_NEWS == 0.5
        assert MULT_NORMALISATION == 0.8
        assert MULT_NORMAL == 1.0

    def test_kill_switch_env(self):
        assert nsa.NEWS_SHOCK_ATTENUATOR_ENV == "V9_NEWS_SHOCK_ATTENUATOR_ENABLED"


# ── 7. Audit SQL live (R14 — justification empirique) ──────────────
class TestLiveAudit:
    """Justifie l'existence du module par les chiffres reels de la DB.

    Ces tests SONT EXECUTES contre data/v9_forces.db. Ils valident que :
      - wide_spread (proxy news shock) a un WR < 25% sur 30j
      - wide_spread detruit plus de pips par trade que normal
    Si la DB n'existe pas (CI dev), les tests sont skip.
    """

    DB_PATH = Path("C:/projet/V9/data/v9_forces.db")

    @pytest.mark.skipif(
        not DB_PATH.exists(),
        reason="DB live absente (dev/CI) — skip audit R14",
    )
    def test_wide_spread_wr_lt_25pct(self):
        """wide_spread (proxy news) doit avoir un WR desastreux (< 25%)."""
        con = sqlite3.connect(str(self.DB_PATH), timeout=30)
        try:
            r = con.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  ROUND(100.0*SUM(CASE WHEN pips_net_of_spread > 0
                                       THEN 1 ELSE 0 END)/COUNT(*), 2) AS wr
                FROM paper_trades
                WHERE closed_at > datetime('now', '-30 day')
                  AND spread_pips >= 2.0
                """
            ).fetchone()
            n, wr = r[0], r[1]
        finally:
            con.close()
        assert n is not None and n >= 20, (
            f"Besoin d'au moins 20 trades wide_spread, got {n}"
        )
        assert wr < 25.0, (
            f"Audit R14 KO : wide_spread WR={wr}% devrait etre < 25% "
            f"(sinon attenuateur inutile). Mesure sur n={n} trades."
        )

    @pytest.mark.skipif(
        not DB_PATH.exists(),
        reason="DB live absente (dev/CI) — skip audit R14",
    )
    def test_wide_spread_avg_pips_lt_normal(self):
        """wide_spread doit avoir un avg_pips < avg_pips normal (justification)."""
        con = sqlite3.connect(str(self.DB_PATH), timeout=30)
        try:
            r_wide = con.execute(
                """
                SELECT ROUND(AVG(pips_net_of_spread), 3) AS avg_pips
                FROM paper_trades
                WHERE closed_at > datetime('now', '-30 day')
                  AND spread_pips >= 2.0
                """
            ).fetchone()
            r_normal = con.execute(
                """
                SELECT ROUND(AVG(pips_net_of_spread), 3) AS avg_pips
                FROM paper_trades
                WHERE closed_at > datetime('now', '-30 day')
                  AND spread_pips < 2.0
                """
            ).fetchone()
        finally:
            con.close()
        avg_wide = r_wide[0] if r_wide and r_wide[0] is not None else 0.0
        avg_normal = r_normal[0] if r_normal and r_normal[0] is not None else 0.0
        assert avg_wide < avg_normal, (
            f"Audit R14 KO : avg_pips wide_spread={avg_wide} devrait etre "
            f"< normal={avg_normal} (sinon pas de justification a l'attenuateur)."
        )
