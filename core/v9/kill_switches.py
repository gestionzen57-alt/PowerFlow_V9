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
