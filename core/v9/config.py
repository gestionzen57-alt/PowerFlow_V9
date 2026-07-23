"""Configuration centrale — PowerFlow V9, couche Forces (capture)."""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "1.0"

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

DB_PATH = ROOT_DIR / "data" / "v9_forces.db"

LISTEN_HOST = "127.0.0.1"
# NOTE (Phase 7) : V8 utilisait 31685 en production. V9 est désormais seul
# sur cette machine — le port 31685 est le port de référence V9 définitif.
# Les EA V9 doivent configurer ServerPort=31685 (valeur par défaut des EA).
# Pour un test isolé sans interrompre le serveur actif, utiliser 31690.
LISTEN_PORT = 31685  # Port de référence V9 (production)

LOG_PATH = ROOT_DIR / "logs" / "v9_capture.log"

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]

TIMEFRAMES_CANDLE = ["M5", "M15", "M30", "H1", "H4", "D1"]
TIMEFRAME_TICK = ["M1"]

# Seuils de péremption STALE_GATE par timeframe, en millisecondes.
STALE_THRESHOLDS_MS: dict[str, int] = {
    "M1": 5_000,
    "M5": 35_000,
    "M15": 95_000,
    "M30": 185_000,
    "H1": 365_000,
    "H4": 1_450_000,
    "D1": 9_000_000,
}

# ── Calibration ForcesReader ─────────────────────────────
# Fenêtre (en nombre de snapshots consécutifs) sur laquelle un croisement
# récent est recherché pour qualifier un recroisement.
RECROISEMENT_LOOKBACK_BARS = 5

# Fenêtre (en nombre de snapshots) sur laquelle un extrême local est
# recherché pour qualifier un rejet_repulsion.
REJET_EXTREME_WINDOW_BARS = 10
# Rebond minimal (en unités de force) depuis un extrême local pour
# qualifier un rejet_repulsion.
REJET_MIN_REBOUND = 5.0

# Fenêtre (en nombre de snapshots) sur laquelle la moyenne mobile
# d'amplitude (max-min des 8 forces) est calculée pour compression_extension.
COMPRESSION_WINDOW_BARS = 10
# Ratios déclenchant respectivement extension et compression par rapport
# à la moyenne mobile d'amplitude.
EXTENSION_RATIO = 1.2
COMPRESSION_RATIO = 0.8

# Noms de champs tels qu'envoyés par l'EA (ea/V9_Sonde_TF.mq4) : préfixe
# "force_" + code devise en minuscule.
FORCE_KEYS = [f"force_{d.lower()}" for d in DEVISES]

# ── Calibration SceneBuilder (couche Scènes) ─────────────
# Écart maximal (en unités de force) entre deux devises de même direction
# pour les considérer comme alignées au sein d'une coalition.
COALITION_THRESHOLD = 5.38
# Écart minimal (en unités de force) entre deux devises de direction
# opposée pour qualifier un antagonisme.
ANTAGONISM_THRESHOLD = 31.39
# Écart minimal entre deux pentes consécutives pour qualifier une pliure
# (rupture brutale de dynamique) dans la cinématique locale.
PLIURE_THRESHOLD = 1.7
# Nombre de snapshots consécutifs (par timeframe) chargés depuis la DB
# comme historique pour la cinématique, les coalitions/antagonismes
# (comparaison au snapshot précédent) et les confluences MTF.
MTF_LOOKBACK = 10

# ── Calibration BehaviorAnalyzer (couche Comportements) ──
# Nombre de scènes / comportements précédents (même paire + même
# timeframe) chargés comme historique pour qualifier une dynamique,
# détecter une transition ou déterminer une phase.
# Autopilot P5 CEO 2026-07-13 : 10 → 50, capture plus de saisonnalité
# intra-journalière (≈ 12h d'historique M5 ou 25h H1). KISS — pas
# d'env var dédiée, override direct dans ce fichier si besoin (R25'
# descriptif). Réversibilité : 50 → 10 = rollback de 1 caractère.
BEHAVIOR_HISTORY_LOOKBACK = 50
# Seuil de similarité (0.0-1.0) au-delà duquel un comportement est
# considéré comme une variante d'un comportement déjà catalogué.
SIMILARITY_THRESHOLD = 0.65
# Confiance de qualification (0-100) attribuée quand une pliure sévère
# de la cinématique locale de la scène est détectée.
CONFIANCE_PLIURE_SEVERE = 70
# Confiance de qualification (0-100) attribuée quand une bascule
# d'équilibre nette est détectée dans un antagonisme de la scène.
CONFIANCE_BASCULE_NETTE = 75

# ── Calibration WindowGate (couche Fenêtres) ─────────────
# Confiance minimale (comportement.confiance_qualification) pour qu'une
# fenêtre puisse passer à un statut autre que "absente" / "ambigue".
CONFIANCE_MIN_FENETRE = 50

# Chute de confiance (en points) entre le comportement précédent et le
# comportement courant, sur la même paire+TF, qui déclenche une fragilité.
FRAGILITE_CONFIANDE_DELTA = 15

# Nombre de comportements précédents (même paire+TF) consultés pour le
# cycle de vie et la détection de fragilité.
WINDOW_LIFECYCLE_LOOKBACK = 5

# Bonus/malus appliqués au niveau_confiance de la fenêtre (clampé 0-100).
# NOTE (revalidation fusion Phase 4+5) : BONUS_CONFLUENCE_MTF n'est plus
# appliqué par WindowGate. BehaviorAnalyzer (Phase 4 réelle) intègre déjà la
# confluence MTF (scene.confluences_mtf.emboitement_detecte) dans
# confiance_qualification en amont (cf. behavior_analyzer._compute_confiance) ;
# un second bonus ici ferait double-compte. Constante conservée pour mémoire
# de calibration, non appliquée dans window_gate.py.
#
# 2026-07-07 sprint Søn β : audit a confirmé la constante n'est référencée
# NULLE PART dans le code (que dans window_gate.py:26 docstring + ce bloc).
# Marquée DEPRECATED à supprimer à la prochaine itération de config.py.
# Ne PAS l'utiliser dans de nouveaux modules.
BONUS_CONFLUENCE_MTF = 10  # DEPRECATED 2026-07-07 — non appliqué, voir NOTE ci-dessus
BONUS_SIMILARITE = 8
MALUS_STALE = 20
MALUS_FRAGILITE = 15

# Seuil de similarite_score (comparaison_cas_connus) au-delà duquel le
# bonus de similarité est appliqué.
SIMILARITE_BONUS_THRESHOLD = 0.75

# ── Calibration ExploitabilityEvaluator (couche Exploitabilité) ──
# Niveau de confiance globale (0-100) à partir duquel une fenêtre
# ouverte devient "exploitable".
SEUIL_EXPLOITABLE = 65
# Niveau de confiance globale (0-100) à partir duquel une fenêtre
# ouverte (ou fragile) reste au moins en "watchlist".
SEUIL_WATCHLIST = 45
# Nombre minimal de cas comparés dans le replay_context pour que
# l'échantillon soit jugé suffisant.
REPLAY_MIN_CAS = 3
# Taux de réussite (WIN / (WIN+LOSS)) minimal parmi les cas comparés
# pour juger l'historique favorable.
REPLAY_MIN_WIN_RATE = 0.55
# Bonus de confiance globale si le comportement source a une
# confiance_qualification élevée.
BONUS_CONFIANCE_COMPORTEMENT = 8
# Bonus de confiance globale si une confluence MTF est confirmée sur
# la scène à l'origine du comportement.
BONUS_CONFLUENCE_MTF_EXPLOIT = 10
# Bonus de confiance globale si un cas comparé à forte similarité est
# une issue gagnante (WIN).
BONUS_SIMILARITE_EXPLOIT = 7
# Malus de confiance globale si la fenêtre source est marquée stale.
MALUS_STALE_EXPLOIT = 25
# Malus de confiance globale si une fragilité est détectée sur la
# fenêtre source.
MALUS_FRAGILITE_EXPLOIT = 15
# Malus de confiance globale si le nombre de cas comparés est
# inférieur à REPLAY_MIN_CAS.
MALUS_REPLAY_INSUFFISANT = 10

# Fichier optionnel d'issues de replay (behavior_id -> "WIN"|"LOSS"|"UNKNOWN"),
# alimenté hors périmètre de cette couche (aucune logique d'exécution ici).
REPLAY_OUTCOMES_PATH = ROOT_DIR / "data" / "replay_outcomes.json"

# ── Référentiel temporel V9 (Phase 7 — déploiement live) ─
# Broker Tickmill MT4 / FTMO MT4 : GMT+3 (été comme hiver, pas de DST broker).
BROKER_UTC_OFFSET_HOURS = 3
# Fuseau de l'opérateur, pour affichage / conversion uniquement (gère le
# passage CEST/CET automatiquement via zoneinfo — voir market_calendar.py).
LOCAL_TIMEZONE = "Europe/Paris"

# Heures d'ouverture/fermeture du marché Forex, exprimées en UTC.
MARKET_OPEN_UTC_DAY = 6      # Dimanche (Python: Monday=0 ... Sunday=6)
MARKET_OPEN_UTC_HOUR = 22    # 22h UTC = 23h Paris (CEST) = 01h broker (lundi, GMT+3)
MARKET_CLOSE_UTC_DAY = 4     # Vendredi
MARKET_CLOSE_UTC_HOUR = 22   # 22h UTC = 23h Paris (CEST) = 01h broker (samedi, GMT+3)

# NOTE : les timestamps DB V9 (forces_snapshots.timestamp, created_at, etc.)
# sont TOUJOURS en UTC (ISO 8601). L'EA MT4 envoie bar_time/server_time/
# capture_time en heure broker (GMT+3) ; forces_reader.py convertit en UTC
# (ToISO8601UTC côté EA, avant insertion) avant toute écriture DB. Voir
# core/v9/market_calendar.py pour les utilitaires de conversion.

# ── Orchestrateur (Phase 9 — déclenchement live de la chaîne) ────
# Si True, capture_server.py déclenche la chaîne cognitive complète
# (Scènes → Comportements → Fenêtres → Exploitabilité) après chaque
# insertion non-stale dans forces_snapshots. Si False, le serveur ne
# fait que capturer (comportement Phase 7/8 d'origine).
ENABLE_CHAIN = True

# ── Couche Décision (Phase 9 — principes, signaux, décisions) ────
# Répertoire des grammaires de principes migrées telles quelles depuis
# V8 (docs/audit_v8_v9_migration.md §4.3, 27 fichiers ACTIVE).
PRINCIPLES_DIR = ROOT_DIR / "core" / "v9" / "principles"

# 27 principes activés : les 9 seuls principes `kind=node_rule` migrés
# (logique conditionnelle réelle) + 16 principes `kind=grammar` promus
# SHADOW→ACTIVE le 2026-07-10 + 2 promus le 2026-07-14 (SIGNAL_OPEN +
# ADAPTIVE_VOL_GATE, audit ZCode motion CEO « go priorité 1 »).
# Les 2 archivés (GRAMMAR_GRAVITE, GRAMMAR_INVERSION) restent hors catalogue.
PRINCIPLE_ACTIVE_IDS = [
    # ── 7 node_rule ACTIVE (détecteurs de zone) ──────────────
    # DIVERSIFY 2026-07-16 (décision CEO Søn, rollout « Mix ») :
    # ANTAGONIST_NODE rétrogradé ACTIVE→SHADOW le temps d'observer 24-48h
    # le fix moteur (dérivation cross-TF par-devise). Promotion ACTIVE
    # conditionnée à un taux de déclenchement sain observé (R25').
    # "ANTAGONIST_NODE",  # SHADOW jusqu'à validation observation (voir DECISIONS_LOG 2026-07-16)
    "GRAVITY_RESPRING_NODE",
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
    "PRICE_LAG_AT_NODE_BIRTH",
    "ZONE_RETEST",
    # ── 16 grammar ACTIVE (vocabulaire descriptif) ────────────
    "GRAMMAR_REGIME",
    "GRAMMAR_ABSORPTION",
    "GRAMMAR_ANTAGONISME",
    "GRAMMAR_BREAK",
    "GRAMMAR_COALITION",
    "GRAMMAR_CROISEMENT",
    "GRAMMAR_EXHAUSTION",
    "GRAMMAR_EXTENSION",
    "GRAMMAR_LEADER_FOLLOWER",
    # DIVERSIFY 2026-07-16 (Mix CEO) : GRAMMAR_LOCK + GRAMMAR_RESPIRATION
    # rétrogradés ACTIVE→SHADOW le temps d'observer le fix moteur
    # (_detect_zone_type vocab + propagation compression_extension_etat).
    "GRAMMAR_LOCK",         # ACTIVE 2026-07-17 (motion CEO, 191/191 décls)
    "GRAMMAR_OPPOSITION",
    "GRAMMAR_PULLBACK",
    "GRAMMAR_RESPIRATION",  # ACTIVE 2026-07-17 (motion CEO, 191/191 décls)
    "GRAMMAR_SQUEEZE",
    "GRAMMAR_TENSION",
    # ── 2 promus SHADOW→ACTIVE le 2026-07-14 ─────────────────
    "SIGNAL_OPEN",
    # DIVERSIFY 2026-07-16 (Mix CEO) : ADAPTIVE_VOL_GATE rétrogradé
    # ACTIVE→SHADOW le temps d'observer le fix d'échelle coalition
    # (seuil normalisé 0-1). Promotion conditionnée (R25').
    # "ADAPTIVE_VOL_GATE",  # SHADOW jusqu'à validation (voir DECISIONS_LOG 2026-07-16)
    # ── 1 promu SHADOW→ACTIVE le 2026-07-15 ─────────────────
    "GRAMMAR_CONTEXTE_ADAPTIVE",
    # ── 2 promus SHADOW→ACTIVE le 2026-07-15 ─────────────────
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",
    "ZONE_RETEST_ADAPTIVE",
    # ═══════════════════════════════════════════════════════════
    # PROMOTION MASSIVE SHADOW→ACTIVE — Mandat CEO 2026-07-16
    # « enlève les interdits, active tout, boucle fermée »
    # R25'' : auto-promotion par l'auto-calibrateur
    # ═══════════════════════════════════════════════════════════
    # ── SHADOW node_rule promus ──────────────────────────────
    "COALITION_NODE",              # 2026-07-16 — n=73 triggered, conf=72.3
    "NODE_BIRTH_FAST",             # 2026-07-16 — n=154 triggered, conf=65.5
    "RAW_NODE_BIRTH",              # 2026-07-16 — n=154 triggered, conf=50
    "ELASTIC_BREATH",              # 2026-07-16 — n=65 triggered, conf=60
    # ── SHADOW grammar promus ────────────────────────────────
    "GRAMMAR_CONTEXTE",            # 2026-07-16 — n=4811 triggered, conf=56.3
    # ── SHADOW _ADAPTIVE promus (consommateurs P3-WIRE) ─────
    "COALITION_NODE_ADAPTIVE",              # n=19, conf=70.5
    "ELASTIC_BREATH_ADAPTIVE",              # n=60, conf=60
    "GRAMMAR_ABSORPTION_ADAPTIVE",          # n=77, conf=60
    "GRAMMAR_ANTAGONISME_ADAPTIVE",         # n=9, conf=60
    "GRAMMAR_BREAK_ADAPTIVE",               # n=36, conf=61.5
    "GRAMMAR_COALITION_ADAPTIVE",           # n=728, conf=55.1
    "GRAMMAR_CROISEMENT_ADAPTIVE",          # n=1024, conf=60
    "GRAMMAR_EXTENSION_ADAPTIVE",           # n=35, conf=60
    "GRAMMAR_LEADER_FOLLOWER_ADAPTIVE",     # n=668, conf=60
    "GRAMMAR_OPPOSITION_ADAPTIVE",          # n=15, conf=76
    "GRAMMAR_PULLBACK_ADAPTIVE",            # n=797, conf=50
    "GRAMMAR_REGIME_ADAPTIVE",              # n=20, conf=55.5
    "GRAMMAR_SQUEEZE_ADAPTIVE",             # n=40, conf=60
    "GRAMMAR_TENSION_ADAPTIVE",             # n=61, conf=77.6
    "GRAVITY_RESPRING_NODE_ADAPTIVE",       # n=76, conf=60
    "NODE_BIRTH_FAST_ADAPTIVE",             # n=24, conf=54.5
    "PRICE_LAG_AT_NODE_BIRTH_ADAPTIVE",     # n=731, conf=92.9
    "RAW_NODE_BIRTH_ADAPTIVE",              # n=24, conf=50
]

# DIVERSIFY 2026-07-16 (décision CEO Søn) — principes réanimés tenus HORS
# auto-promotion le temps de l'observation 24-48h. Sans cette exclusion, le
# cycle R30 « Auto-promotion » (SHADOW→ACTIVE si n≥20 + conf≥60, tous les 100
# trades) les repasserait ACTIVE dès qu'ils accumulent des triggers — ce qu'ils
# font désormais (1-19 %) —, court-circuitant l'observation voulue. Retirer ces
# IDs de ce set après validation observée (WR/taux sains) pour rendre la main à
# la boucle fermée. Consommé par core/v9/auto_calibrator.py.
AUTO_PROMOTION_EXCLUDE = {
    "ANTAGONIST_NODE",
    "ADAPTIVE_VOL_GATE",
}

# Correspondance timeframes V8 (minutes, `scope.timeframes` des YAML) ->
# noms V9 (`forces_snapshots.timeframe`).
PRINCIPLE_TIMEFRAME_MINUTES_TO_V9 = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1",
}

# Confiance par défaut attribuée à un principe déclenché sans `bounds`
# exploitable pour un scoring proportionnel (0-100).
PRINCIPLE_CONFIDENCE_DEFAULT = 60

# ── Calibration RegimeDetector (Phase 9 — bonus, gap V8 comblé) ──
# Seuils portés de core/pf_regime_detector.py (V8, PROVISIONAL — à
# recalibrer à n>=50 comme en V8). Le détecteur V9 tourne par snapshot
# sur une fenêtre glissante (REGIME_LOOKBACK_BARS) au lieu d'un batch
# historique complet, mais la machine à états (palier/cassure/extension/
# retour_equilibre/rejet) est identique.
#
# 2026-07-20 motion CEO #10 (audit Opus Phase 2 — RECALIBRAGE DATA-DRIVEN) :
# les seuils globaux (0.5/1.5/3/2.0) sont statistiquement absurdes :
# P50 |step| = 1.5-2.0 sur M1-H4, donc SEUIL_PALIER=0.5 ne capture que
# P10-P15 = ~10% de la distribution, PALIER=0.5% observé, NEUTRE=91%.
# Motion CEO #10 §1-§5 : seuils par TF + D1=QUIET. Voir
# workspace/perplexity/PROMPT_OPUS_REGIME_RECALIBRATION_20260720.md.
#
# Activation motion CEO #11 (R2 additif) : override par TF via env
# (REGIME_SEUIL_PALIER_M5=0.9 par ex). Si env absent, fallback sur le
# dict ci-dessous. Migration douce : on garde les constantes globales
# en fallback rétro-compatible (tests legacy).
REGIME_LOOKBACK_BARS = 20
SEUIL_PALIER = 0.5   # legacy fallback (cf. REGIME_SEUILS_BY_TF)
SEUIL_CASSURE = 1.5  # legacy fallback
REGIME_N_MIN = 3     # legacy fallback
REGIME_M_MIN = 2
REGIME_MR_LOW = 20.0
REGIME_MR_HIGH = 80.0
SEUIL_REJET = 2.0
REGIME_K_REJET = 1

# Seuils par TF (audit Opus motion CEO #10, 2026-07-20).
# Format : {timeframe: (SEUIL_PALIER, SEUIL_CASSURE, REGIME_N_MIN, SEUIL_REJET, enabled)}
# - enabled=False : PALIER désactivé (D1 : P50=0.02 → 72% faux PALIER)
# - N_MIN=2 sur M1-H1 (au lieu de 3) : proba jointe (P10)^3 trop stricte
REGIME_SEUILS_BY_TF: dict[str, tuple[float, float, int, float, bool]] = {
    "M1":  (1.0, 1.5, 2, 8.0, True),
    "M5":  (0.9, 2.0, 2, 8.0, True),
    "M15": (0.9, 2.0, 2, 8.0, True),
    "M30": (0.9, 2.0, 2, 8.0, True),
    "H1":  (0.9, 2.0, 2, 8.0, True),
    "H4":  (0.7, 1.5, 1, 8.0, True),
    "D1":  (0.5, 1.0, 2, 8.0, False),  # D1 PALIER désactivé
}


def get_regime_seuils_for_tf(timeframe: str) -> tuple[float, float, int, float, bool]:
    """Retourne (SEUIL_PALIER, SEUIL_CASSURE, N_MIN, SEUIL_REJET, enabled)
    pour le timeframe donné.

    Ordre de résolution (R2 additif) :
      1. Override env var : REGIME_SEUIL_PALIER_<TF>, REGIME_SEUIL_CASSURE_<TF>,
         REGIME_N_MIN_<TF>, REGIME_SEUIL_REJET_<TF>
      2. Dict REGIME_SEUILS_BY_TF (motion CEO #10)
      3. Fallback legacy (SEUIL_PALIER, SEUIL_CASSURE, REGIME_N_MIN, SEUIL_REJET)

    L'override env permet le tuning runtime sans toucher au code (live
    motion CEO §5 validation 2 semaines).
    """
    import os
    tf = timeframe.upper()
    # Override env (per-TF, format REGIME_<param>_<TF>)
    env_palier = os.environ.get(f"REGIME_SEUIL_PALIER_{tf}")
    env_cassure = os.environ.get(f"REGIME_SEUIL_CASSURE_{tf}")
    env_nmin = os.environ.get(f"REGIME_N_MIN_{tf}")
    env_rejet = os.environ.get(f"REGIME_SEUIL_REJET_{tf}")
    env_enabled = os.environ.get(f"REGIME_ENABLED_{tf}")

    if env_palier is not None or env_cassure is not None or env_nmin is not None \
            or env_rejet is not None or env_enabled is not None:
        # Au moins un override → construire depuis dict + override
        base = REGIME_SEUILS_BY_TF.get(tf, REGIME_SEUILS_BY_TF["M5"])
        return (
            float(env_palier) if env_palier is not None else base[0],
            float(env_cassure) if env_cassure is not None else base[1],
            int(env_nmin) if env_nmin is not None else base[2],
            float(env_rejet) if env_rejet is not None else base[3],
            (env_enabled == "1") if env_enabled is not None else base[4],
        )

    base = REGIME_SEUILS_BY_TF.get(tf)
    if base is not None:
        return base

    # Fallback legacy
    return (SEUIL_PALIER, SEUIL_CASSURE, REGIME_N_MIN, SEUIL_REJET, True)

# ── Recalibration H1/H4 (2026-07-16 — diagnostic MTF dormant) ──────
# Constat live 2026-07-06 -> 2026-07-16 (GBPUSD, devise GBP — seule
# devise lue par mtf_confirmation_engine.THESIS_REGIMES via
# `base = symbol[:3]`) : CASSURE/EXTENSION = 0 sur H1/H4 en source_type
# live (les 13 seules occurrences historiques viennent du seed replay
# du 05/07). M1-M30, mêmes seuils, mêmes distributions de pas de force
# (percentiles quasi identiques par TF sur ce dataset) : taux
# CASSURE+EXTENSION sain de 4.9%-14.6% évalué au même grain (une
# évaluation par barre fermée). Cause : REGIME_N_MIN=3 exige 3 barres
# consécutives quasi-immobiles pour ancrer un palier ; M1-M30 sont
# capturés plusieurs fois par barre (intra-barre) et cumulent des
# dizaines de tentatives par barre fermée, H1/H4 n'en ont qu'une seule
# — la probabilité jointe de voir 3 pas < SEUIL_PALIER d'affilée ne se
# matérialise quasi jamais sur les ~25-100 barres H1/H4 disponibles en
# 10 jours. Recalibré par backtest sur l'historique réel (GBP,
# n=83 barres H1 / n=23 barres H4, 2026-07-06->16) : H1 n_min=2 ->
# 10.8% (aligné sur M1-M30) ; H4 seuil_palier=0.7 + n_min=2 -> 17.4%.
# M1/M5/M15/M30/D1 non touchés (déjà sains, R2 additif — voir
# RegimeDetector._effective_thresholds).
REGIME_TIMEFRAME_OVERRIDES: dict[str, dict[str, float | int]] = {
    "H1": {"n_min": 2},
    "H4": {"seuil_palier": 0.7, "n_min": 2},
    # 2026-07-20 motion CEO #10 (audit Opus Phase 2) : recalibrage data-driven
    # disponible mais **NON ACTIF** (R25' strict). Activation runtime =
    # validation 2 semaines paper-trade (motion CEO future). Pour activer
    # sans attendre : décommenter les lignes M1/M5/M15/M30/H1 ci-dessous.
    #
    # "M1":  {"seuil_palier": 1.0, "seuil_cassure": 1.5, "n_min": 2},
    # "M5":  {"seuil_palier": 0.9, "seuil_cassure": 2.0, "n_min": 2},
    # "M15": {"seuil_palier": 0.9, "seuil_cassure": 2.0, "n_min": 2},
    # "M30": {"seuil_palier": 0.9, "seuil_cassure": 2.0, "n_min": 2},
    # "H1":  {"seuil_palier": 0.9, "seuil_cassure": 2.0, "n_min": 2},
    # "H4":  {"seuil_palier": 0.7, "seuil_cassure": 1.5, "n_min": 1},
}

# ── Regime gate (Chantier A, 2026-07-18) ──────────────────────────
# Seuil de confiance (part des 8 devises en régime dominant) au-delà
# duquel un régime "volatile" bloque l'exploitabilité (statut -> refuse).
# Paramétrable — jamais hardcodé dans exploitability_evaluator. Actif
# seulement sous kill switch V9_REGIME_GATE_ENABLED (défaut OFF).
REGIME_GATE_VOLATILE_CONF = 0.7

# ── Calibration SignalGenerator (Phase 9) ────────────────────────
# Régimes jugés porteurs d'une dynamique directionnelle exploitable —
# filtre "régime de marché inadéquat" (gap V8 identifié dans l'audit,
# absent de la couche Exploitabilité). PALIER = pas d'énergie
# directionnelle libérée -> aucun signal, quels que soient les principes
# déclenchés.
#
# 2026-07-06 — Retrait de NEUTRE de REGIMES_INADEQUATS (urgence ISM PMI
# 14h UTC). Constat live : sur GBPUSD 2026-07-06, regime_type=NEUTRE sur
# la quasi-totalité des snapshots, y compris les fenêtres exploitables
# (n=234, window ouverte, 1-3 principes ACTIVE déclenchés
# POWER_ANGLE_BREAK/PRICE_LAG/ZONE_RETEST avec confiance 60-100). Le
# filtre NEUTRE bloquait 100% des signaux malgré tous les autres critères
# OK. Risque résiduel : faux signaux sur régime NEUTRE — accepté car
# (1) l'exploitabilité reste un pré-filtre strict (niveau_confiance
# >= 65 + 3 cas WIN comparés), (2) NEUTRE peut signaler une transition
# imminente (oscillation sans direction nette = signal précurseur),
# (3) le scanner --principes + heatmap 30j live reste l'autorité pour
# recalibrer si WR < 50%. PALIER conservé (énergie complètement absente).
# 2026-07-22 — Remise de NEUTRE dans REGIMES_INADEQUATS (motion CEO « fait tout »).
# Données 7j : NEUTRE = 78% des decisions, WR=44.4%, -624 pips (perte structurelle).
# RETOUR_EQUILIBRE = 11%, WR=57.7%, +10 pips (seul regime profitable).
# EXTENSION = WR=41.5%, -160 pips. CASSURE = WR=20%, -89 pips.
# Le système trade du bruit en NEUTRE. Filtrage NEUTRE = -78% volume mais
# élimine la source principale de pertes. Les signaux sur NEUTRE qui étaient
# "exploitables" étaient en réalité du bruit de range (window=absente + confiance
# inflationnée à 100, désormais plafonnée à 70).
# 2026-07-22 23h00 — Bilan semaine : NEUTRE était gagnant le 16/07 (WR 74%)
# mais perdant 20-22/07 (WR 34-48%). Le vrai problème est le VOLUME (72
# decisions gagnant vs 210+ perdant), pas le régime. Mais NEUTRE génère
# massivement plus de decisions que les autres régimes → garder filtré.
REGIMES_ADEQUATS = {"CASSURE", "EXTENSION", "REJET", "RETOUR_EQUILIBRE"}
REGIMES_INADEQUATS = {"PALIER", "NEUTRE"}

# Confiance globale minimale du signal pour être journalisé avec un
# horizon "court_terme" plutôt que "surveillance".
SIGNAL_CONFIANCE_HORIZON_COURT = 65

# Fix 2026-07-15 (audit régime GBPUSD) — fallback direction quand le vote
# des principes ACTIVE triggered est vide (seuls des principes grammar
# descriptifs, direction=None, se déclenchent — cas observé sur GBPUSD
# M15 le 15/07 : spread GBP-USD jusqu'à +74 sur ~15h, vote toujours
# EGALITE/vide, direction=neutre malgré +157 pips). `force_<devise>` est
# borné [0,100] (vérifié empiriquement) : un écart de spread >= ce seuil
# est un déséquilibre de force sans ambiguïté, même sans principe
# directionnel déclenché. La confiance du fallback est directement
# `abs(spread)` (même échelle 0-100) — pas de principe ne l'endosse,
# donc elle reste strictement dérivée des forces, jamais inventée.
SIGNAL_FORCES_FALLBACK_SPREAD_MIN = 20.0

# 2026-07-23 — Seuils spread par paire (étude DB 3j).
# GBPUSD avg=5.5 (plus large), EURUSD avg=1.5 (plus tight).
# Au lieu d'un seuil global de 5, on adapte par paire.
# Au-dessus du seuil → slippage destructeur d'edge → blocage.
SPREAD_MAX_PAR_PAIRE = {
    "EURUSD": 4,
    "GBPUSD": 8,   # spread structurellement plus large
    "USDCHF": 5,
    "USDJPY": 5,
    "USDCAD": 5,
    "AUDUSD": 4,
}
SPREAD_MAX_DEFAULT = 5  # fallback si paire non listée

# 2026-07-23 — Tick volume minimum (liquidité).
# Si tick_volume < ce seuil → pas de transactions réelles → bloquer.
TICK_VOLUME_MIN = 5

# 2026-07-23 — WR par qualification behavior (étude DB 7j).
# Boost/malus basé sur le comportement observé du marché.
BEHAVIOR_QUALIFICATION_BOOST = {
    # Gagnants (WR > 50% et pips > 0)
    "reequilibrage": +5,    # WR=52%, +6.8 pips
    "seconde_bosse": +5,    # WR=55%, +25.3 pips
    # Perdants (WR < 40% ou pips < -100)
    "contraction": -10,     # WR=23%, -135 pips
    "tension": -5,           # WR=37%, -300 pips
    "bascule": -5,           # WR=36%, -62 pips
    "rupture": -5,           # WR=25%, -24 pips
}

# 2026-07-23 — Order flow proxy (absorption detection).
# Absorption = volume haut + prix stable (close≈open) + spread tight.
# Indique que des limit orders absorbent le marché (pas de mouvement malgré
# le volume) → précède souvent une cassure directionnelle.
ORDER_FLOW_VOLUME_MIN = 50      # tick_volume minimum pour absorption
ORDER_FLOW_PRICE_STABLE_MAX = 0.0002  # |close - open| < seuil = prix stable
ORDER_FLOW_SPREAD_MAX = 3       # spread tight = liquidité présente

# 2026-07-23 — Régime detection v2 (NEUTRE nuancé).
# NEUTRE est filtré globalement, mais un NEUTRE avec compression naissante
# est différent d'un NEUTRE profond. Quand compression_extension_etat est
# "compression" ou "extension" en régime NEUTRE, on ne bloque pas le signal
# (le squeeze indique qu'un mouvement se prépare). Le filtre regime reste
# strict sauf dans ce cas précis.
NEUTRE_AVEC_ENERGIE_AUTORISE = True  # autoriser NEUTRE si compression/extension

# ── Multi-paires (Brief Q4, 2026-07-13) ──────────────────────────
# `symbol` a toujours été un champ libre threadé depuis l'EA (Symbol()
# natif, cf. ea/V9_Sonde_TF.mq4) jusqu'à la DB (forces_snapshots.symbol,
# index UNIQUE déjà composite symbol+timeframe+bar_time) et tout le
# pipeline perceptuel (SceneBuilder filtre déjà par symbol en paramètre
# de requête) — aucune restructuration nécessaire pour supporter plusieurs
# paires. GBPUSD reste la paire de référence, comportement strictement
# inchangé (aucune de ces paires n'apparaît dans aucune table spéciale).
# Registre informatif (dashboards/scripts/validation) — l'attachement
# effectif de l'EA à un graphique EURUSD/USDJPY/GBPJPY reste une action
# opérateur MT4, hors périmètre de ce dépôt.
SUPPORTED_SYMBOLS = ["GBPUSD", "EURUSD", "USDJPY", "GBPJPY"]

# ── P4 TradeStrategyEngine avancé (2026-07-16) ──────────────────
# Kelly sizing (fractionnel K=0.25), bornes hard [0.3, 2.0], fallback
# sur sizing actuel si WR observé < KELLY_MIN_TRADES par principe.
KELLY_FRACTION = 0.25
KELLY_MIN_TRADES = 20
SIZING_MIN = 0.3
SIZING_MAX = 2.0

# ── CVaR sizing institutionnel (Chantier B, 2026-07-18) ─────────────
# Le sizing Kelly existant (paper_risk_manager) est PLAFONNÉ par un budget
# CVaR 95% : taille max = CVAR_BUDGET_PIPS / cvar_95(returns récents). Quand
# la perte-queue attendue d'une paire dépasse le budget, la taille est réduite.
# Actif seulement sous kill switch V9_KELLY_CVAR_ENABLED (défaut OFF). Le
# sizing Kelly live a un verdict NO-GO walk-forward (DECISIONS_LOG 2026-07-18) —
# activation = override CEO explicite.
CVAR_CONFIDENCE = 0.95
CVAR_BUDGET_PIPS = 12.0       # perte-queue attendue max tolérée (pips) par trade
CVAR_LOOKBACK_TRADES = 50     # nb de paper_trades récents pour estimer la queue
CVAR_MIN_TRADES = 20          # en-dessous : pas assez d'historique, pas de plafond
# Vol regime multiplicateur de sizing (réduit taille position en vol haute,
# EXTREME=0 = pas de trade).
VOL_SIZING_MULTIPLIER: dict[str, float] = {
    "LOW": 1.0,
    "NORMAL": 1.0,
    "HIGH": 0.7,
    "EXTREME": 0.0,
}
# Trailing CASSURE-aware : active trailing quand MFE > ratio * TP,
# distance trailing = sl * ratio (au lieu du trailing_dist fixe 15 pips).
TRAILING_CASSURE_MIN_MFE_RATIO = 0.5
TRAILING_CASSURE_DIST_SL_RATIO = 0.5