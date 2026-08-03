"""kill_switches.py — Chargeur central des kill switches V9.

Lit `config/v9_kill_switches.env` et expose les valeurs via des fonctions
pures. Utilisé par tous les modules qui ont besoin de connaître l'état
des switches (orchestrator, principle_engine, shadow_evaluator, etc.).

Avant : chaque module lisait `os.environ.get("V9_xxx", "0")` — mais personne
ne chargeait le fichier `.env` dans l'environnement au runtime. Les switches
n'étaient effectifs que dans les tests (conftest).

Doctrine : R6 (ne jamais lever), R18 (zéro LLM), R25' (OFF par défaut).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / "config" / "v9_kill_switches.env"

# Cache process-local (lu une seule fois)
_switches: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _switches
    if _switches is not None:
        return _switches
    _switches = {}
    if not ENV_PATH.exists():
        return _switches
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        _switches[key.strip()] = val.strip()
    return _switches


def get(key: str, default: str = "0") -> str:
    """Retourne la valeur d'un kill switch.
    Priorité : variable d'environnement > fichier > défaut.
    """
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return _load().get(key, default)


def is_enabled(key: str) -> bool:
    """Retourne True si le kill switch est activé (=="1")."""
    return get(key) == "1"


# ── Switches nommés ────────────────────────────────────────────────
def shadow_mode_enabled() -> bool:
    return is_enabled("V9_SHADOW_MODE_ENABLED")


def adaptive_thresholds_wired_enabled() -> bool:
    return is_enabled("V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED")


def trader_mini_enabled() -> bool:
    return is_enabled("V9_TRADER_MINI_ENABLED")


def auto_calibrator_enabled() -> bool:
    return is_enabled("V9_AUTO_CALIBRATOR_ENABLED")


def execution_enabled() -> bool:
    return is_enabled("V9_EXECUTION_ENABLED")


def auto_resolve_enabled() -> bool:
    return is_enabled("V9_AUTO_RESOLVE_ENABLED")


def arbiter_scorer_enabled() -> bool:
    return is_enabled("V9_ARBITER_SCORER_ENABLED")


def hitl_branching_enabled() -> bool:
    return is_enabled("V9_HITL_BRANCHING_ENABLED")


def regime_gate_enabled() -> bool:
    """Kill switch V9_REGIME_GATE_ENABLED (défaut '0' = OFF).

    Chantier A (2026-07-18) : quand OFF, le gate régime de
    l'exploitabilité est passthrough (aucun blocage) — zéro régression.
    """
    return is_enabled("V9_REGIME_GATE_ENABLED")


def kelly_cvar_enabled() -> bool:
    """Kill switch V9_KELLY_CVAR_ENABLED (défaut '0' = OFF).

    Chantier B (2026-07-18) : quand OFF, le plafond CVaR sur le sizing
    Kelly existant est inactif — sizing inchangé, zéro régression.
    """
    return is_enabled("V9_KELLY_CVAR_ENABLED")


def cvd_enabled() -> bool:
    """Kill switch V9_CVD_ENABLED (défaut '0' = OFF).

    Chantier C (2026-07-18) : quand OFF, le CVD (Cumulative Volume Delta) n'est
    pas exposé dans la scène (cvd_cumul / cvd_divergence). La couche forces
    reste passive (parse ce que l'EA envoie, ou NULL). Zéro régression.
    """
    return is_enabled("V9_CVD_ENABLED")


def loop_breaker_enabled() -> bool:
    """Kill switch V9_LOOP_BREAKER_ENABLED — garde-fou anti-boucle re-entry.

    Câblage P0.4 (2026-07-19) : source de vérité = fichier `.env` (via get()),
    pas `os.environ` seul. Le cron paper-trade lançait le supervisor sans
    charger le `.env` → le switch était lu OFF alors que le fichier dit ON.
    """
    return is_enabled("V9_LOOP_BREAKER_ENABLED")


def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED — watchdog live edgefund (Axe 6).

    Défaut OFF tant que pas d'activation explicite dans le `.env`. Activé
    2026-07-19 (motion CEO « Construis le watchdog » = mandat runtime).
    """
    return is_enabled("V9_LIVE_WATCHDOG_ENABLED")


def bayesian_calibrator_enabled() -> bool:
    """Kill switch V9_BAYESIAN_CALIBRATOR_ENABLED (défaut '0' = OFF).

    Axe 1.1 J1 (2026-07-21) : quand OFF, la calibration bayésienne
    (BayesianCalibrator, `signal_generator.calibrate_confidence`) n'est pas
    consommée par le pipeline — la confiance déclarée reste inchangée, zéro
    régression. Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_BAYESIAN_CALIBRATOR_ENABLED")


def kelly_fractional_enabled() -> bool:
    """Kill switch V9_KELLY_FRACTIONAL_ENABLED (défaut '0' = OFF).

    Axe 1.2 J2 (2026-07-21) : quand OFF, le multiplicateur Kelly bayésien-borné
    (`v9_kelly_sizing.KellySizingEngine`) n'est PAS appliqué au sizing du
    trade_engine — la composition `base × dynamic_risk × kelly` dégénère en
    `base × dynamic_risk` (kelly=1.0 neutre), zéro régression. Composition
    multiplicative avec le DynamicRiskManager (jamais un remplacement).
    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_KELLY_FRACTIONAL_ENABLED")


def bayesian_predictor_enabled() -> bool:
    """Kill switch V9_BAYESIAN_PREDICTOR_ENABLED (défaut '0' = OFF).

    Axe 2.3 J5 (2026-07-21) : active le câblage du prédicteur bayésien
    (`v9_bayesian_predictor.predict()`) dans le pipeline live.
    Quand OFF, le prédicteur reste **invoquable manuellement** (CLI, scripts,
    tests) mais **NON câblé** dans `signal_generator` / `trade_engine`.
    Zéro régression : la confiance déclarée reste la source de vérité.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_BAYESIAN_PREDICTOR_ENABLED")


def drawdown_protector_enabled() -> bool:
    """Kill switch V9_DRAWDOWN_PROTECTOR_ENABLED (défaut '0' = OFF).

    Axe 3.2 J11 (2026-07-21) : active le câblage du Drawdown Protector
    (`v9_drawdown_protector.DrawdownProtector`) dans le pipeline live.
    Implémente 5 paliers de protection (volatility targeting, DD circuit
    breaker, recovery mode, Kelly adaptive, hedging).

    Quand OFF, le module reste invocable manuellement (CLI/scripts/tests)
    mais **NON câblé** dans `trade_engine`. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_DRAWDOWN_PROTECTOR_ENABLED")


def risk_parity_enabled() -> bool:
    """Kill switch V9_RISK_PARITY_ENABLED (défaut '0' = OFF).

    Axe 3.3 J12 (2026-07-21) : active le câblage du Risk Parity
    (`v9_risk_parity.RiskParityEngine`) pour allocation risque-budget
    proportionnelle à la variance (standard AQR / Bridgewater) sur 5 paires
    actives (USDCAD blacklisté).

    Quand OFF, le module reste invocable manuellement mais **NON câblé**.
    Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_RISK_PARITY_ENABLED")


def cycle_memory_enabled() -> bool:
    """Kill switch V9_CYCLE_MEMORY_ENABLED (défaut '0' = OFF).

    Axe 4 J14 (2026-07-21) : active le câblage de la mémoire inter-cycles
    (`v9_cycle_memory.CycleMemory`) dans le pipeline live. Permet au
    système de rappeler les patterns historiques des décisions résolues
    par contexte opérationnel (symbol, timeframe, regime, phase, vol_bucket).

    Quand OFF, le module reste invocable manuellement mais **NON câblé**.
    Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_CYCLE_MEMORY_ENABLED")


def meta_strategy_optimizer_enabled() -> bool:
    """Kill switch V9_META_STRATEGY_OPTIMIZER_ENABLED (défaut '0' = OFF,
    actuellement **ON** par motion CEO 04h58 du 2026-07-21).

    Axe 4 J15 (2026-07-21) : active le câblage du méta-strategy optimizer
    (`v9_meta_strategy_optimizer.MetaStrategyOptimizer`) — couche au-dessus
    du StrategySelector qui re-balance les stratégies par contexte.

    Quand OFF, le meta_strategy_optimizer ne tourne PAS et le
    StrategySelector standard prend le relais. Zéro régression.
    """
    return is_enabled("V9_META_STRATEGY_OPTIMIZER_ENABLED")


def learn_loop_enabled() -> bool:
    """Kill switch V9_LEARN_LOOP_ENABLED (défaut '0' = OFF, actuellement **ON**
    par motion CEO antérieure).

    Axe 4 J16 (2026-07-21) : active la boucle d'apprentissage continue
    (`v9_learn_loop`) — orchestration ingestion décisions résolues +
    fit Platt + walk-forward + mise à jour state.

    Quand OFF, la boucle ne tourne PAS ; les décisions sont toujours
    résolues mais le système n'apprend pas de l'historique. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_LEARN_LOOP_ENABLED")


def cross_pair_metrics_enabled() -> bool:
    """Kill switch V9_CROSS_PAIR_METRICS_ENABLED (défaut '0' = OFF).

    Axe 4 J17-J18 (2026-07-21) : active le câblage des métriques cross-pair
    (`v9_cross_pair_metrics`) — cross_pair_dispersion, pair_force_ratio,
    neutre_rate_24h. Utilisé par le regime_detector (motion CEO #8 audit
    Opus) et le watchdog live.

    Quand OFF, les métriques sont désactivées et le regime_detector
    retombe sur le mode basique. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_CROSS_PAIR_METRICS_ENABLED")


def walk_forward_enabled() -> bool:
    """Kill switch V9_WALK_FORWARD_ENABLED (défaut '0' = OFF).

    Axe 1.3 J3 (2026-07-21) : active la validation walk-forward anchored en
    mode shadow dans le pipeline live. Le walk-forward reste **toujours** un
    outil de diagnostic lecture seule (le module `walk_forward.py` ne fait
    aucun write sur la calibration live) — le kill switch contrôle
    uniquement son déclenchement automatique par le cron `V9_WalkForward`.

    Sans kill switch ON : le module est invocable manuellement via
    `scripts/v9_walk_forward.py` (CLI), ce qui produit un rapport Markdown
    dans docs/reports/. Le cron quotidien NE tourne PAS (R25' strict).

    Promotion cron AUTO = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_WALK_FORWARD_ENABLED")


def paper_trade_halt_enabled() -> bool:
    """Kill switch V9_PAPER_TRADE_HALT — HALT TOTAL du paper-trading (R6 fail-safe).

    Défaut OFF. Quand ON, le moteur de paper-trade ne doit rien ouvrir.
    C'est l'action de niveau P0 recommandée par le watchdog critique
    (remplace l'ancienne reco `V9_GBPUSD_LONG_ONLY=0` qui ré-autorisait
    les shorts au lieu d'arrêter — cf. audit edgefund 2026-07-19).
    """
    return is_enabled("V9_PAPER_TRADE_HALT")


# ──────────────────────────────────────────────────────────────────────────────
# Nouveaux kill switches (2026-07-25) — Unified Meta-Learning & Sizing
# ──────────────────────────────────────────────────────────────────────────────

def meta_learning_enabled() -> bool:
    """Kill switch V9_META_LEARNING_ENABLED — Orchestrateur unique meta-learning.

    Remplace les 4 crons séparés (auto_calibrator, auto_optimizer, learn_loop,
    walk_forward) par un cycle unifié avec état partagé et gatings croisés.
    Défaut ON (motion CEO 2026-07-25).
    """
    return is_enabled("V9_META_LEARNING_ENABLED")


def unified_sizing_enabled() -> bool:
    """Kill switch V9_UNIFIED_SIZING_ENABLED — Moteur de sizing unifié.

    Composition multiplicative cohérente : base × portfolio_risk × dd_protector
    × risk_parity × kelly × meta_strategy. Bornes finales [0.1, 3.0].
    OFF par défaut pour migration progressive (R25' strict).
    """
    return is_enabled("V9_UNIFIED_SIZING_ENABLED")


def edge_decay_monitor_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_MONITOR_ENABLED — Surveillance dégradation edge.

    Détection proactive dégradation edge par principe × session × régime.
    Auto-actions : blacklist, démotion, observation mode.
    Défaut ON (motion CEO 2026-07-25).
    """
    return is_enabled("V9_EDGE_DECAY_MONITOR_ENABLED")


def anti_serie_perdante_enabled() -> bool:
    """Kill switch V9_ANTI_SERIE_PERDANTE_ENABLED — Filtre anti-série perdante J2.

    Bloque un trade si 3 paper_trades consécutifs sur (symbol, direction)
    sont tousperdants. Additif (R2), R6 jamais bloquant (DB indisponible →
    skip silencieux). Défaut ON (motion CEO « GO MAX » 28/07).
    """
    # Désactivé explicitement ? défaut = ON pour autopilot CEO.
    return os.environ.get("V9_ANTI_SERIE_PERDANTE_ENABLED", "1") == "1"


def kill_dd_wr_enabled() -> bool:
    """Kill switch V9_KILL_DD_WR_ENABLED — Kill switch DD 24h + WR plancher J2.

    HALT si DD 24h < V9_KILL_DD_PIPS (défaut -100) OU si WR sur 20 derniers
    trades < V9_KILL_WR_FLOOR (défaut 0.40). Additif (R2), R6 jamais
    bloquant. Défaut ON (motion CEO « GO MAX » 28/07).
    """
    # FIX anti-pattern R31 (audit v2 Perplexity 01/08) : utiliser get()
    return get("V9_KILL_DD_WR_ENABLED", "1") == "1"


def kill_dd_pips() -> float:
    """Seuil DD 24h (pips) pour declencher le kill switch (defaut -100).

    Lecture depuis .env via kill_switches.get() (anti-pattern R31 fix).
    """
    try:
        return float(get("V9_KILL_DD_PIPS", "-100"))
    except (ValueError, TypeError):
        return -100.0


def kill_wr_floor() -> float:
    """WR plancher sur 20 derniers trades (defaut 0.40).

    Lecture depuis .env via kill_switches.get() (anti-pattern R31 fix).
    """
    try:
        return float(get("V9_KILL_WR_FLOOR", "0.40"))
    except (ValueError, TypeError):
        return 0.40


def bayesian_consumer_enabled() -> bool:
    """Kill switch V9_BAYESIAN_CALIBRATOR_CONSUMER — Câblage live J4.

    Active le remplacement de la confiance déclarée par la confiance
    postérieure Beta dans SignalGenerator.generate(). Additif (R2),
    R6 jamais bloquant (si calibrator absent ou None → déclaratif conservé).
    Défaut ON (motion CEO « GO MAX » 28/07).
    """
    return os.environ.get("V9_BAYESIAN_CALIBRATOR_CONSUMER", "1") == "1"


def drm_human_profile_enabled() -> bool:
    """Kill switch V9_DRM_HUMAN_PROFILE_ENABLED — Profil HUMAN_SCALP J5.

    Active la géométrie skewed TP=25/SL=8 (RR=3.1) par défaut dans
    DynamicRiskManager. Additif (R2), R6 fallback si désactivé.
    Défaut ON (motion CEO « GO MAX » 28/07).
    """
    return os.environ.get("V9_DRM_HUMAN_PROFILE_ENABLED", "1") == "1"


def mega_edge_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_ENABLED — Phase 2 edge fund filter (J8).

    Active le filtre MEGA-EDGE L1-L6 (audit SQL 90j, +336p/74 trades
    GBPUSD haussiere 11-13h UTC, -265p/60 trades 00-09h UTC). Additif
    (R2), R6 jamais bloquant. Défaut ON (motion CEO « EDGE FUND MAX »).
    """
    return os.environ.get("V9_MEGA_EDGE_ENABLED", "1") == "1"


def mega_edge_l7_grammar_pur_blacklist_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED — Phase 108 (01/08/2026).

    Blackliste les trades GRAMMAR pur et ELASTIC pur SANS etoile structurelle
    (PRICE_LAG_AT_NODE_BIRTH, POWER_ANGLE_BREAK_TO_PRICE_IMPACT, GRAVITY_RESPRING_NODE).

    Audit SQL 90j post-reparation V4 (OOS STABLE 01/08/2026) :
      - GRAMMAR pur (sans star) : n=203, WR=28.1%, pips=-546.7, -2.69p/trade
      - ELASTIC pur (sans star) : n=59,  WR=30.5%, pips=-107.3, -1.82p/trade
      - Edge reel uniquement sur les 3 stars : WR=100% sur 71 trades, +379.5 pips

    L5 (deja actif) bloque MIX GRAMMAR+ELASTIC, mais pas les purs.
    L7 complete L5 en bloquant aussi les purs no-stars, qui constituent
    80% de la perte totale (654/818 pips negatifs cumules sur 90j).

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant
    (mega_edge_enabled doit etre ON pour activer L7).
    """
    # Phase 117 fix : utiliser get() au lieu de os.environ.get pour lire le fichier
    return get("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "0") == "1"


def mega_edge_l8_principle_count_blacklist_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED — Phase 120 (01/08/2026).

    Blackliste les trades avec >= 5 principes totaux (mega-combinaisons).
    Audit SQL full DB post-reparation V4 :
      - n_principes 1-3 : n=85, WR=97.6%, PNL=+461.2p (+5.43/trade)
      - n_principes 4   : n=5,  WR=60.0%, PNL=+5.0p   (+1.00/trade)
      - n_principes 5+  : n=247, WR=23.5%, PNL=-752.7p (-3.05/trade)

    Point d'inflexion net a n=5. Au-dela, GRAMMAR/ZONE/NODE diluent l'edge.
    L8 transforme le systeme : -259.7p pre -> +466.2p post (gain +725.9p).

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant
    (mega_edge_enabled doit etre ON pour activer L8).
    """
    return get("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED", "0") == "1"


def mega_edge_l9_time_filter_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_L9_TIME_FILTER_ENABLED — Phase 125 (03/08/2026).

    Blackliste les trades ouverts avant 14h UTC (heures asiatiques creuses + debut Londres faible).
    Audit SQL full DB post-reparation V4 :
      - 0h-13h UTC : n=146, WR=15.5%, PNL=-520.1p (-3.56p/trade) — DRAIN SYSTEMATIQUE
      - 14h-19h UTC : n=144, WR=78.5%, PNL=+436.5p (+3.03p/trade) — EDGE AUTHENTIQUE
      - Pic de perte a 8h UTC : -149.1p, WR 15.8%

    Gain projete si L9 active : recuperation ~520 pips (somme pertes 0-13h).
    Cout : 13h/jour sans trading (54% temps marche), tres restrictif.

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant
    (mega_edge_enabled doit etre ON pour activer L9).
    NECESSITE MOTION CEO EXPLICITE pour activation (hors perimetre R22 standard).
    """
    return get("V9_MEGA_EDGE_L9_TIME_FILTER_ENABLED", "0") == "1"


def mega_edge_l11_dow_gbpusd_mer_boost_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_L11_DOW_GBPUSD_MER_BOOST_ENABLED — Phase 127 (03/08/2026).

    Boost sizing x1.3 sur GBPUSD le mercredi (audit SQL live 03/08 :
    n=111 WR=79.3% PNL=+423.1p). Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant (mega_edge_enabled doit etre ON).
    """
    return get("V9_MEGA_EDGE_L11_DOW_GBPUSD_MER_BOOST_ENABLED", "0") == "1"


def mega_edge_l11_dow_gbpusd_mar_blacklist_enabled() -> bool:
    """Kill switch V9_MEGA_EDGE_L11_DOW_GBPUSD_MAR_BLACKLIST_ENABLED — Phase 127.

    Blacklist GBPUSD mardi (extension du L14, audit SQL live 03/08 :
    n=20 WR=5.0% PNL=-136.9p). Defaut OFF (R25' strict motion CEO).
    """
    return get("V9_MEGA_EDGE_L11_DOW_GBPUSD_MAR_BLACKLIST_ENABLED", "0") == "1"


def vol_realized_tp_sl_enabled() -> bool:
    """Kill switch V9_HEATMAP_L13_VOL_REALIZED_TP_SL_ENABLED — Phase 130 (03/08).

    Active l'adaptation TP/SL par volatilité réalisée (vol spike ×1.5,
    vol calme ×0.7, vol normale ×1.0). Bornes strictes [0.7, 1.5].

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    """
    return get("V9_HEATMAP_L13_VOL_REALIZED_TP_SL_ENABLED", "0") == "1"


def cross_blacklist_enabled() -> bool:
    """Kill switch V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED — Phase 134 (03/08).

    Active la blacklist des croisements (principe_set, regime, session)
    identifiés comme concentrateurs de risque négatif (Phase 132).
    Top-5 croisements GRAMMAR_* × REJET × asie figés par motion CEO.

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    """
    return get("V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED", "0") == "1"


def pyramiding_v3_mtf_boost_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V3_MTF_BOOST_ENABLED — Phase 133 (03/08).

    Active le boost multi-timeframe ×1.2 si >=3 TF alignés dans PyramidingEngineV3.
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2), 0 modif core/ partagé.
    """
    return get("V9_PYRAMIDING_V3_MTF_BOOST_ENABLED", "0") == "1"


# ── Phase 128 — L12 Correlation inter-paires × regime (2026-08-03) ──────────
# Audit SQL live 03/08 (n=337 post-DROP) :
#   NEUTRE + 4 paires simultanees : n=218, WR=13.8%, PNL=-1163.8p (surexposition)
#   EXTENSION + 2 paires simultanees : n=28, WR=32.1%, PNL=-118.0p
#   RETOUR_EQUILIBRE + 2 paires simultanees : n=7, WR=0%, PNL=-53.4p
# Gain projete : 80-150 pips. Cout : ~50% sizing sur 5-10% des trades.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def correlation_filter_enabled() -> bool:
    """Kill switch V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED — Phase 128 (03/08/2026).

    Active le filtre correlation inter-paires × regime (PRM etendu, sizing ×0.5
    si paire correlee > V9_L12_CORR_THRESHOLD et meme regime, blocage si 2+
    positions deja ouvertes sur paires correlees meme regime).

    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    Module : core/v9/v9_correlation_filter.py (NEW).
    """
    return get("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "0") == "1"


# ── Phase 129 — L16 Asymetrie WR par direction (2026-08-03) ─────────────
# Audit SQL live 03/08 (n=337 post-DROP) :
#   Haussier (n=307) : WR=45.9% PNL=-682.0p avg=-2.22p/trade
#   Baissier (n= 30) : WR=30.0% PNL=-183.2p avg=-6.32p/trade (12x plus perdant)
#   GBPUSD haussier (n=163) : WR=63.8% PNL=-42.2p (top niche L1)
# Gain projete : 100-250 pips. Cout : ~30% sizing haussier, 30% reduction baissier.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def direction_asymmetry_enabled() -> bool:
    """Kill switch V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED — Phase 129 (03/08/2026).

    Active l'asymetrie WR par direction (sizing x1.3 haussier / x0.7 baissier,
    avec exceptions RETOUR_EQUILIBRE haussier et CASSURE baissier qui restent x1.0).

    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    Module : core/v9/v9_direction_asymmetry.py (NEW).
    """
    return get("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "0") == "1"


def pyramiding_v4_zones_state_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V4_ZONES_STATE_ENABLED — Phase 136 (03/08/2026).

    Active le boost zones_state du PyramidingEngine V4 (naissance ×1.2,
    2e_jambe ×1.1, retest ×1.0, range ×0.8). Composition multiplicative
    V2 × V3_MTF × V4_zones_state.

    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2) — herite de PyramidingEngineV3 sans modification.
    Module : core/v9/v9_pyramiding_engine_v4.py (NEW).
    """
    return get("V9_PYRAMIDING_V4_ZONES_STATE_ENABLED", "0") == "1"


def adaptive_dd_tracker_enabled() -> bool:
    """Kill switch V9_ADAPTIVE_DD_TRACKER_ENABLED — Phase 137 (03/08/2026).

    Active le tracker DD adaptatif par contexte (vol × regime × session).
    Seuils dynamiques : spike ×1.5, CASSURE ×1.2, asie ×0.5.
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2) — herite de v9_drawdown_protector sans modification.
    Module : core/v9/v9_adaptive_dd_tracker.py (NEW).
    """
    return get("V9_ADAPTIVE_DD_TRACKER_ENABLED", "0") == "1"


def regime_live_detector_enabled() -> bool:
    """Kill switch V9_REGIME_LIVE_DETECTOR_ENABLED — Phase 138 (03/08/2026).

    Active le detecteur live de regime (DOW × regime × vol) pour pre-decision
    adaptative de la prochaine heure. Defaut OFF (R25' strict motion CEO).
    R6 jamais bloquant. Additif (R2).
    Module : core/v9/v9_regime_live_detector.py (NEW).
    """
    return get("V9_REGIME_LIVE_DETECTOR_ENABLED", "0") == "1"


def edge_decay_sentinel_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_SENTINEL_ENABLED — Phase 140 (2026-08-03).

    Sentinel de degradation edge (proactif vs reactif). Detecte la chute
    de WR recent vs baseline par principe et recommande une action
    preventive (BLACKLIST_TEMP_24H / DEMOTION / OBSERVATION_ONLY).
    Defaut OFF (R25' strict motion CEO). Additif (R2). R6 fail-open.
    Module : core/v9/v9_edge_decay_sentinel.py (NEW).
    """
    return get("V9_EDGE_DECAY_SENTINEL_ENABLED", "0") == "1"


def news_shock_attenuator_enabled() -> bool:
    """Kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED — Phase 141 (2026-08-04).

    Active l'attenuateur news shock (fenetres NFP / CPI / FOMC / ECB).
    Module dedie a la modulation du sizing selon la fenetre news
    (pre_news ×0.5, imminent ×0.0 HALT, post_news ×0.5,
    normalisation ×0.8, normal ×1.0). Audit SQL live 03/08 (n=337) :
    wide_spread (proxy news) WR 18% vs normal 53% → pnl -619 pips
    sur 122 trades en fenetre news, soit -5.08 pips/trade vs -1.14
    en regime normal. Gain projeté : 40-80 pips / cycle.
    Defaut OFF (R25' strict motion CEO). Additif (R2), R6 fail-open.
    Module : core/v9/v9_news_shock_attenuator.py (NEW).
    """
    return get("V9_NEWS_SHOCK_ATTENUATOR_ENABLED", "0") == "1"


def news_heat_map_enabled() -> bool:
    """Kill switch V9_NEWS_HEAT_MAP_ENABLED — Phase 143 (2026-08-04).

    Active la heat map news x paire (NFP / CPI / FOMC / ECB x
    EURUSD / USDJPY / XAUUSD / GBPUSD / AUDUSD). Module additif (R2)
    qui module le sizing selon la chaleur historique d'une paire
    a un type de news, compose avec la fenetre news du L19 attenuator
    (composition MIN(base, minutes_factor) = plus restrictif gagne).
    Audit SQL live 03/08 (n=337 60j) : USDCHF WR 10.5% avg -5.92 pips,
    USDCAD 0% / -9.38 pips, EURUSD 16.3% / -4.69 pips → heat map
    ecrase ces paires sur news directes. Gain projeté : 60-100 pips.
    Defaut OFF (R25' strict motion CEO). Additif (R2), R6 fail-open.
    Module : core/v9/v9_news_heat_map.py (NEW).
    """
    return get("V9_NEWS_HEAT_MAP_ENABLED", "0") == "1"
