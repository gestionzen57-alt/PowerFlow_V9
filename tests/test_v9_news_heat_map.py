"""Tests pour v9_news_heat_map.py (Phase 143 — L20 News Heat Map).

Couvre les cas critiques :
1. Kill switch OFF -> pass-through (1.0)
2. Composition MIN(base, minutes_factor) — plus restrictif gagne
3. Heat map explicite par (symbol, news_type) — 7 paires x 4 news = 28 cas
4. Blacklist USDCHF/USDCAD sur NFP/CPI/FOMC (multiplier=0.0 → HALT)
5. EURUSD x ECB = 0.1 (choc direct BCE, plus restrictif)
6. GBPUSD le plus resilient (multipliers >= 0.5 partout)
7. Fallback safe : symbol inconnu OU news_type invalide → ×0.8
8. Bornes finales clampées [0.0, 1.0]
9. R6 fail-open : entree invalide (None, str vide, etc.) → 1.0
10. Composition avec fenetre news : imminent (0.0) > heat base → HALT
11. Dataclass classify_news_heat() coherente
12. get_heat_map_snapshot() retourne la map structuree
13. summarize_heat_verdicts agrege correctement
14. Audit SQL live : USDCHF doit etre le pire (sanity check R14)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9 import v9_news_heat_map as nhm
from core.v9.v9_news_heat_map import (
    DEFAULT_BASE_MULTIPLIER,
    HEAT_MAP,
    NEWS_TYPE_CPI,
    NEWS_TYPE_ECB,
    NEWS_TYPE_FOMC,
    NEWS_TYPE_NFP,
    NEWS_TYPES_VALID,
    NewsHeatVerdict,
    classify_news_heat,
    compute_news_heat_multiplier,
    get_heat_map_snapshot,
    news_heat_map_enabled,
    summarize_heat_verdicts,
)


# ── Fixture : kill switch ON pour les tests metier ──────────────────
@pytest.fixture
def nhm_on(monkeypatch):
    """Active le kill switch V9_NEWS_HEAT_MAP_ENABLED=1."""
    monkeypatch.setenv("V9_NEWS_HEAT_MAP_ENABLED", "1")
    from core.v9 import kill_switches as ks
    ks._switches = None
    yield
    ks._switches = None


@pytest.fixture
def nhm_off(monkeypatch):
    """Force le kill switch OFF (defaut)."""
    monkeypatch.delenv("V9_NEWS_HEAT_MAP_ENABLED", raising=False)
    from core.v9 import kill_switches as ks
    ks._switches = None
    yield
    ks._switches = None


# ── 1. Kill switch OFF -> pass-through ─────────────────────────────
class TestKillSwitchOff:
    def test_kill_switch_off_returns_1x(self, nhm_off):
        """OFF : tout couple (symbol, news, m) → 1.0."""
        for sym in ["EURUSD", "USDCHF", "GBPUSD", "XAUUSD", "AUDUSD", "BTCUSD"]:
            for nt in [NEWS_TYPE_NFP, NEWS_TYPE_CPI, NEWS_TYPE_FOMC, NEWS_TYPE_ECB]:
                for m in [-100, -30, -10, 0, 5, 30, 100]:
                    v = compute_news_heat_multiplier(sym, nt, m)
                    assert v == 1.0, (
                        f"OFF {sym}/{nt}/m={m} should be 1.0, got {v}"
                    )

    def test_kill_switch_off_helper(self, nhm_off):
        assert news_heat_map_enabled() is False

    def test_classify_returns_kill_switch_off(self, nhm_off):
        v = classify_news_heat("EURUSD", NEWS_TYPE_NFP, 30)
        assert v.final_multiplier == 1.0
        assert v.phase_label == "kill_switch_off"
        assert v.enabled is False
        assert v.base_multiplier == 1.0
        assert v.minutes_factor == 1.0
        assert v.fallback_used is False


# ── 2. Logique metier (kill switch ON) — composition MIN ───────────
class TestComposition:
    def test_min_wins_imminent_over_base(self, nhm_on):
        """En imminent (m=5, factor=0.0), meme heat base eleve → 0.0 HALT."""
        # GBPUSD x NFP : base=0.6, mais imminent factor=0.0 → 0.0
        v = compute_news_heat_multiplier("GBPUSD", NEWS_TYPE_NFP, 5)
        assert v == 0.0

    def test_min_wins_eurusd_ecb_base_low(self, nhm_on):
        """EURUSD x ECB : base=0.1, normal (m=100) factor=1.0 → 0.1."""
        v = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_ECB, 100)
        assert v == 0.1

    def test_min_wins_usdchf_nfp_blacklist(self, nhm_on):
        """USDCHF x NFP : base=0.0 (blacklist), normal factor=1.0 → 0.0 HALT."""
        v = compute_news_heat_multiplier("USDCHF", NEWS_TYPE_NFP, 100)
        assert v == 0.0

    def test_pre_news_factor_0_5(self, nhm_on):
        """m=30 (pre_news) : minutes_factor=0.5, applique a GBPUSD x ECB (base=0.7)."""
        v = compute_news_heat_multiplier("GBPUSD", NEWS_TYPE_ECB, 30)
        # min(0.7, 0.5) = 0.5
        assert v == 0.5

    def test_post_news_factor_0_5(self, nhm_on):
        """m=-10 (post_news) : minutes_factor=0.5."""
        v = compute_news_heat_multiplier("GBPUSD", NEWS_TYPE_CPI, -10)
        # min(0.7, 0.5) = 0.5
        assert v == 0.5

    def test_normalisation_factor_0_8(self, nhm_on):
        """m=-30 (normalisation) : minutes_factor=0.8."""
        v = compute_news_heat_multiplier("USDJPY", NEWS_TYPE_FOMC, -30)
        # USDJPY x FOMC base=0.4, min(0.4, 0.8) = 0.4
        assert v == 0.4

    def test_normal_full_factor(self, nhm_on):
        """Hors fenetre (m=100) : minutes_factor=1.0."""
        v = compute_news_heat_multiplier("GBPUSD", NEWS_TYPE_CPI, 100)
        # GBPUSD x CPI base=0.7, min(0.7, 1.0) = 0.7
        assert v == 0.7


# ── 3. Heat map explicite par paire × news ─────────────────────────
class TestHeatMapExplicit:
    """Sanity check sur les 28 cellules de la heat map (7 paires x 4 news)."""

    def test_usdchf_blacklist_us_news(self, nhm_on):
        """USDCHF blacklist sur NFP / CPI / FOMC (×0.0), ok sur ECB (×0.5)."""
        assert compute_news_heat_multiplier("USDCHF", NEWS_TYPE_NFP, 100) == 0.0
        assert compute_news_heat_multiplier("USDCHF", NEWS_TYPE_CPI, 100) == 0.0
        assert compute_news_heat_multiplier("USDCHF", NEWS_TYPE_FOMC, 100) == 0.0
        assert compute_news_heat_multiplier("USDCHF", NEWS_TYPE_ECB, 100) == 0.5

    def test_usdcad_blacklist_us_news(self, nhm_on):
        """USDCAD meme politique que USDCHF (blacklist historique cf. v9_risk_parity)."""
        assert compute_news_heat_multiplier("USDCAD", NEWS_TYPE_NFP, 100) == 0.0
        assert compute_news_heat_multiplier("USDCAD", NEWS_TYPE_CPI, 100) == 0.0
        assert compute_news_heat_multiplier("USDCAD", NEWS_TYPE_FOMC, 100) == 0.0
        assert compute_news_heat_multiplier("USDCAD", NEWS_TYPE_ECB, 100) == 0.5

    def test_eurusd_ecb_pire_qu_autres(self, nhm_on):
        """EURUSD x ECB doit etre le pire d'EURUSD (BCE = choc direct)."""
        ecb = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_ECB, 100)
        nfp = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_NFP, 100)
        cpi = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_CPI, 100)
        fomc = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_FOMC, 100)
        assert ecb <= nfp
        assert ecb <= cpi
        assert ecb <= fomc
        assert ecb == 0.1

    def test_gbpusd_le_plus_resilient(self, nhm_on):
        """GBPUSD doit avoir tous ses multipliers >= 0.5 (audit R14 WR 63%)."""
        for nt in NEWS_TYPES_VALID:
            v = compute_news_heat_multiplier("GBPUSD", nt, 100)
            assert v >= 0.5, f"GBPUSD x {nt} devrait etre >= 0.5, got {v}"

    def test_xauusd_safe(self, nhm_on):
        """XAUUSD (pas de data live) doit avoir des multipliers raisonnables [0.5, 0.7]."""
        for nt in NEWS_TYPES_VALID:
            v = compute_news_heat_multiplier("XAUUSD", nt, 100)
            assert 0.5 <= v <= 0.7, f"XAUUSD x {nt} hors borne, got {v}"

    def test_usdjpy_sensible_au_fomc(self, nhm_on):
        """USDJPY x FOMC doit etre le plus restrictif (BoJ suiveuse Fed)."""
        fomc = compute_news_heat_multiplier("USDJPY", NEWS_TYPE_FOMC, 100)
        nfp = compute_news_heat_multiplier("USDJPY", NEWS_TYPE_NFP, 100)
        cpi = compute_news_heat_multiplier("USDJPY", NEWS_TYPE_CPI, 100)
        ecb = compute_news_heat_multiplier("USDJPY", NEWS_TYPE_ECB, 100)
        assert fomc <= nfp
        assert fomc <= cpi
        assert fomc == 0.4

    def test_audusd_fragile_sur_us_news(self, nhm_on):
        """AUDUSD sensible aux news US (NFP, FOMC) plus qu'a ECB."""
        nfp = compute_news_heat_multiplier("AUDUSD", NEWS_TYPE_NFP, 100)
        fomc = compute_news_heat_multiplier("AUDUSD", NEWS_TYPE_FOMC, 100)
        ecb = compute_news_heat_multiplier("AUDUSD", NEWS_TYPE_ECB, 100)
        assert nfp <= ecb
        assert fomc <= ecb


# ── 4. Fallback safe (R6) ──────────────────────────────────────────
class TestFallback:
    def test_unknown_symbol_uses_default(self, nhm_on):
        """Paire inconnue (ex. BTCUSD) → DEFAULT_BASE_MULTIPLIER = 0.8."""
        v = compute_news_heat_multiplier("BTCUSD", NEWS_TYPE_NFP, 100)
        # min(0.8, 1.0) = 0.8
        assert v == 0.8

    def test_invalid_news_type_uses_default(self, nhm_on):
        """news_type invalide → DEFAULT × 1.0 (normal)."""
        v = compute_news_heat_multiplier("EURUSD", "INVALID_NEWS", 100)
        # min(0.8, 1.0) = 0.8
        assert v == 0.8

    def test_empty_news_type_uses_default(self, nhm_on):
        v = compute_news_heat_multiplier("EURUSD", "", 100)
        assert v == 0.8

    def test_lowercase_normalized(self, nhm_on):
        """Insensible a la casse : 'eurusd' / 'nfp' doivent etre reconnus."""
        v = compute_news_heat_multiplier("eurusd", "nfp", 100)
        # EURUSD x NFP base=0.2, normal factor=1.0 → 0.2
        assert v == 0.2


# ── 5. R6 fail-open ────────────────────────────────────────────────
class TestFailOpen:
    def test_none_symbol_returns_1x(self, nhm_on):
        v = compute_news_heat_multiplier(None, NEWS_TYPE_NFP, 30)  # type: ignore[arg-type]
        assert v == 1.0

    def test_none_news_type_returns_1x(self, nhm_on):
        v = compute_news_heat_multiplier("EURUSD", None, 30)  # type: ignore[arg-type]
        assert v == 1.0

    def test_none_minutes_returns_1x(self, nhm_on):
        v = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_NFP, None)  # type: ignore[arg-type]
        assert v == 1.0

    def test_garbage_minutes_returns_1x(self, nhm_on):
        v = compute_news_heat_multiplier("EURUSD", NEWS_TYPE_NFP, "abc")  # type: ignore[arg-type]
        assert v == 1.0


# ── 6. Bornes finales ─────────────────────────────────────────────
class TestClamp:
    def test_clamp_lower(self, nhm_on):
        """Multiplicateur ne descend jamais sous 0.0."""
        v = compute_news_heat_multiplier("USDCHF", NEWS_TYPE_NFP, 0)
        assert v >= 0.0

    def test_clamp_upper(self, nhm_on):
        """Multiplicateur ne monte jamais au-dessus de 1.0."""
        v = compute_news_heat_multiplier("GBPUSD", NEWS_TYPE_ECB, 200)
        assert v <= 1.0

    def test_default_multiplier_value(self):
        assert DEFAULT_BASE_MULTIPLIER == 0.8

    def test_news_types_valid(self):
        assert NEWS_TYPES_VALID == frozenset({"NFP", "CPI", "FOMC", "ECB"})

    def test_heat_map_size(self):
        """La heat map doit contenir 7 paires x 4 news = 28 cellules."""
        assert len(HEAT_MAP) == 28


# ── 7. Dataclass classify_news_heat ───────────────────────────────
class TestClassify:
    def test_classify_eurusd_nfp_pre_news(self, nhm_on):
        v = classify_news_heat("EURUSD", NEWS_TYPE_NFP, 30)
        assert isinstance(v, NewsHeatVerdict)
        assert v.symbol == "EURUSD"
        assert v.news_type == "NFP"
        assert v.minutes_to_news == 30
        assert v.base_multiplier == 0.2
        assert v.minutes_factor == 0.5  # pre_news
        assert v.final_multiplier == 0.2  # min(0.2, 0.5) = 0.2
        assert v.phase_label == "pre_news"
        assert v.enabled is True
        assert v.fallback_used is False

    def test_classify_usdchf_nfp_normal(self, nhm_on):
        v = classify_news_heat("USDCHF", NEWS_TYPE_NFP, 100)
        assert v.base_multiplier == 0.0
        assert v.minutes_factor == 1.0
        assert v.final_multiplier == 0.0  # min(0.0, 1.0) = 0.0 HALT
        assert v.phase_label == "normal"

    def test_classify_unknown_symbol_fallback(self, nhm_on):
        v = classify_news_heat("DOGEUSD", NEWS_TYPE_NFP, 100)
        assert v.fallback_used is True
        assert v.base_multiplier == DEFAULT_BASE_MULTIPLIER

    def test_to_dict_roundtrip(self, nhm_on):
        v = classify_news_heat("EURUSD", NEWS_TYPE_CPI, 30)
        d = v.to_dict()
        assert d["symbol"] == "EURUSD"
        assert d["news_type"] == "CPI"
        assert d["minutes_to_news"] == 30
        assert d["base_multiplier"] == 0.3
        assert d["final_multiplier"] == 0.3
        assert d["phase_label"] == "pre_news"


# ── 8. get_heat_map_snapshot ─────────────────────────────────────
class TestSnapshot:
    def test_snapshot_structure(self):
        snap = get_heat_map_snapshot()
        assert isinstance(snap, dict)
        assert "EURUSD" in snap
        assert "USDCHF" in snap
        assert "XAUUSD" in snap
        assert "GBPUSD" in snap
        assert "AUDUSD" in snap
        assert "USDJPY" in snap
        assert "USDCAD" in snap

    def test_snapshot_eurusd_4_news(self):
        snap = get_heat_map_snapshot()
        assert set(snap["EURUSD"].keys()) == {"NFP", "CPI", "FOMC", "ECB"}

    def test_snapshot_all_values_in_bounds(self):
        snap = get_heat_map_snapshot()
        for sym, m in snap.items():
            for nt, v in m.items():
                assert 0.0 <= v <= 1.0, f"{sym}/{nt}={v} hors borne"


# ── 9. summarize_heat_verdicts ────────────────────────────────────
class TestSummarize:
    def test_empty(self, nhm_on):
        s = summarize_heat_verdicts([])
        assert s["n_total"] == 0
        assert s["n_enabled"] == 0
        assert s["multiplier_avg"] == 0.0

    def test_mixed(self, nhm_on):
        verdicts = [
            classify_news_heat("EURUSD", NEWS_TYPE_NFP, 100),    # 0.2
            classify_news_heat("USDCHF", NEWS_TYPE_CPI, 100),    # 0.0 HALT
            classify_news_heat("GBPUSD", NEWS_TYPE_ECB, 100),    # 0.7
            classify_news_heat("BTCUSD", NEWS_TYPE_NFP, 100),    # 0.8 fallback
        ]
        s = summarize_heat_verdicts(verdicts)
        assert s["n_total"] == 4
        assert s["n_enabled"] == 4
        assert s["n_halt"] == 1
        assert s["n_fallback"] == 1
        # avg = (0.2 + 0.0 + 0.7 + 0.8) / 4 = 0.425
        assert abs(s["multiplier_avg"] - 0.425) < 0.01

    def test_all_kill_switch_off(self, nhm_off):
        verdicts = [classify_news_heat("EURUSD", NEWS_TYPE_NFP, 30) for _ in range(3)]
        s = summarize_heat_verdicts(verdicts)
        assert s["n_total"] == 3
        assert s["n_kill_switch_off"] == 3
        assert s["multiplier_avg"] == 1.0


# ── 10. Audit SQL live (R14 — sanity check empirique) ─────────────
class TestLiveAudit:
    """Sanity check : USDCHF doit avoir le WR le plus bas (audit 60j).

    Si ce test echoue, soit la heat map n'est pas calibree sur le reel,
    soit le marche a change. Skip si DB absente (CI/dev).
    """
    DB_PATH = Path("C:/projet/V9/data/v9_forces.db")

    @pytest.mark.skipif(
        not DB_PATH.exists(),
        reason="DB live absente (dev/CI) — skip audit R14",
    )
    def test_usdchf_is_worst_symbol(self):
        """USDCHF doit avoir le WR le plus bas parmi les paires du screener."""
        con = sqlite3.connect(str(self.DB_PATH), timeout=30)
        try:
            r = con.execute(
                """
                SELECT s.symbol,
                  COUNT(*) AS n,
                  ROUND(100.0*SUM(CASE WHEN t.pips_net_of_spread > 0
                                       THEN 1 ELSE 0 END)/COUNT(*), 2) AS wr,
                  ROUND(AVG(t.pips_net_of_spread), 3) AS avg
                FROM paper_trades t
                JOIN forces_snapshots s ON t.snapshot_id = s.snapshot_id
                WHERE t.closed_at > datetime('now', '-60 day')
                GROUP BY s.symbol
                HAVING COUNT(*) >= 20
                ORDER BY wr ASC
                """
            ).fetchall()
        finally:
            con.close()
        if not r:
            pytest.skip("Pas assez de data pour l'audit R14")
        worst_symbol = r[0][0]
        worst_wr = r[0][1]
        # USDCHF doit etre dans le top 2 pires (sinon heat map KO)
        assert worst_symbol in ("USDCHF", "USDCAD"), (
            f"Audit R14 KO : pire paire = {worst_symbol} (WR {worst_wr}%), "
            f"devrait etre USDCHF ou USDCAD. Top 3 : {r[:3]}"
        )


# ── 11. Constantes API ───────────────────────────────────────────
class TestConstants:
    def test_env_var(self):
        assert nhm.NEWS_HEAT_MAP_ENV == "V9_NEWS_HEAT_MAP_ENABLED"

    def test_news_types(self):
        assert NEWS_TYPE_NFP == "NFP"
        assert NEWS_TYPE_CPI == "CPI"
        assert NEWS_TYPE_FOMC == "FOMC"
        assert NEWS_TYPE_ECB == "ECB"

    def test_heat_map_immutable_type(self):
        """La heat map doit etre un dict (non-FrozenDict pour permettre extension)."""
        assert isinstance(HEAT_MAP, dict)
        assert len(HEAT_MAP) > 0
