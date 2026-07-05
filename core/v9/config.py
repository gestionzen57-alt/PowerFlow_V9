"""Configuration centrale — PowerFlow V9, couche Forces (capture)."""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "1.0"

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

DB_PATH = ROOT_DIR / "data" / "v9_forces.db"

LISTEN_HOST = "127.0.0.1"
# NOTE: V8 utilise encore 31685 en prod.
# Pour tester V9, changer en 31690 temporairement.
LISTEN_PORT = 31685

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
COALITION_THRESHOLD = 5.0
# Écart minimal (en unités de force) entre deux devises de direction
# opposée pour qualifier un antagonisme.
ANTAGONISM_THRESHOLD = 10.0
# Écart minimal entre deux pentes consécutives pour qualifier une pliure
# (rupture brutale de dynamique) dans la cinématique locale.
PLIURE_THRESHOLD = 3.0
# Nombre de snapshots consécutifs (par timeframe) chargés depuis la DB
# comme historique pour la cinématique, les coalitions/antagonismes
# (comparaison au snapshot précédent) et les confluences MTF.
MTF_LOOKBACK = 10

# ── Calibration BehaviorAnalyzer (couche Comportements) ──
# Nombre de scènes / comportements précédents (même paire + même
# timeframe) chargés comme historique pour qualifier une dynamique,
# détecter une transition ou déterminer une phase.
BEHAVIOR_HISTORY_LOOKBACK = 10
# Seuil de similarité (0.0-1.0) au-delà duquel un comportement est
# considéré comme une variante d'un comportement déjà catalogué.
SIMILARITY_THRESHOLD = 0.65
# Confiance de qualification (0-100) attribuée quand une pliure sévère
# de la cinématique locale de la scène est détectée.
CONFIANCE_PLIURE_SEVERE = 70
# Confiance de qualification (0-100) attribuée quand une bascule
# d'équilibre nette est détectée dans un antagonisme de la scène.
CONFIANCE_BASCULE_NETTE = 75
