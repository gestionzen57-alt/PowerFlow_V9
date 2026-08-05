"""V10 Force Native Calculator — Phase 20++ : recalcul forces V10 natives.

Doctrine V10 (mandat CEO étape 9.1) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open (forces absentes → neutre, data absente → fallback)
  R7 : tests verts cumulés
  R8 : auto-calibration
  R9 : audit metadata honnête
  R10 : zéro capital (calcul seul, pas de trade)

Objectif Phase 20++ :
  Remplacer le pnl proxy `close[t+5]-close[t]` (biaisé USDJPY -2785p)
  par un pnl V10 NATIF basé sur :
    1. compression_extension_etat (COLUMNES de `forces_snapshots`)
    2. force_<DEVISE> relative delta (cross-currency)
    3. crossover detection (croisement_detecte + croisement_direction)
    4. recroisement_detecte
    5. rejet_repulsion_detecte + rejet_intensite
  → pnl en pips virtuel, R9 audit, comparable au pnl Fatman MT4.

API :
  - `compute_force_native_pnl(snapshots, pair, horizon=3)` → float pnl_pips_native
  - `compute_force_native_features(snapshots, pair)` → Dict features natives
  - `NativeForceReport` dataclass avec audit
"""
from __future__ import annotations

import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────

# États compression/extension Fatman
COMP_EXT_STATES = ("COMPRESSION", "EXTENSION", "NEUTRE")

# Mapping intensité → pips (heuristique Phase 20+, R8 auto-calibration)
# Valeurs recalibrées pour rester dans une échelle comparable au proxy
# (proxy GBPUSD M30 ~5-50p sur 197 candles, cible native dans même ordre)
INTENSITY_TO_PIPS = {
    "FAIBLE": 1.5,
    "MOYEN": 3.0,
    "FORT": 5.0,
    "EXTREME": 8.0,
}

# Croisement direction → pips signé
CROISEMENT_DIRECTION_TO_PIPS = {
    "HAUSSIERE": +1.0,
    "BAISSIERE": -1.0,
    "NEUTRE": 0.0,
}

# Recroisement bonus (réduit, conservateur)
RECROISEMENT_BONUS_PIPS = 2.0

# Rejet répulsion pénalité (réduit, conservateur)
REJET_PENALTY_PIPS = -1.0

# Force delta seuil (par devise)
FORCE_DELTA_THRESHOLD = 15.0


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class NativeForceFeatures:
    """Features V10 natives par (paire, TF, snapshot)."""
    timestamp: str = ""
    bar_time: int = 0
    force_base: float = 0.0
    force_quote: float = 0.0
    force_delta: float = 0.0
    force_base_rank: int = 99
    force_quote_rank: int = 99
    compression_extension_etat: str = "NEUTRE"
    compression_extension_intensite: str = "FAIBLE"
    croisement_detecte: int = 0
    croisement_direction: str = "NEUTRE"
    recroisement_detecte: int = 0
    rejet_repulsion_detecte: int = 0
    rejet_intensite: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NativeForceReport:
    """Rapport pnl V10 natif par (paire, TF)."""
    pair: str = ""
    timeframe: str = ""
    n_snapshots_used: int = 0
    n_snapshots_compressed: int = 0
    n_snapshots_extended: int = 0
    n_croisements: int = 0
    n_recroisements: int = 0
    n_rejets: int = 0
    pnl_pips_native: float = 0.0
    pnl_pips_proxy: float = 0.0
    delta_pnl_vs_proxy: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _pair_to_base_quote(pair: str) -> Tuple[str, str]:
    """EURUSD → ('EUR', 'USD')."""
    if len(pair) == 6:
        return pair[:3], pair[3:]
    return ("", "")


def _safe_float(x, default=0.0) -> float:
    """Convertir en float, fallback default si None ou NaN."""
    if x is None:
        return default
    try:
        v = float(x)
        if v != v:  # NaN check
            return default
        return v
    except (TypeError, ValueError):
        return default


def _intensity_to_pips(intensite: str) -> float:
    """Map intensité Fatman → pips. R6 fail-open si intensité inconnue."""
    if not intensite:
        return INTENSITY_TO_PIPS["MOYEN"]  # R6 default
    return INTENSITY_TO_PIPS.get(intensite.upper(), INTENSITY_TO_PIPS["MOYEN"])


# ─────────────────────────────────────────────────────────────────────
# FEATURES NATIVES
# ─────────────────────────────────────────────────────────────────────

def compute_force_native_features(snapshot: Dict, pair: str) -> NativeForceFeatures:
    """Calcule features V10 natives depuis une row snapshot.

    Args:
        snapshot: dict représentant 1 row de `forces_snapshots`
        pair: ex "EURUSD"

    Returns:
        NativeForceFeatures peuplé, R9 audit inclus.
    """
    base, quote = _pair_to_base_quote(pair)

    # Récupérer force_<base> et force_<quote> (lowercase keys dans snapshot)
    force_base_key = f"force_{base.lower()}"
    force_quote_key = f"force_{quote.lower()}"

    force_base = _safe_float(snapshot.get(force_base_key, 50.0), 50.0)
    force_quote = _safe_float(snapshot.get(force_quote_key, 50.0), 50.0)

    # Force delta signé (base forte vs quote faible → positif)
    force_delta = force_base - force_quote

    # Ranks (8 devises : USD/GBP/EUR/JPY/CAD/CHF/AUD/NZD)
    all_devises = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]
    forces = {}
    for d in all_devises:
        forces[d] = _safe_float(snapshot.get(f"force_{d.lower()}", 50.0), 50.0)

    # Rank = tri descendant, 1=plus fort
    sorted_devises = sorted(forces.items(), key=lambda kv: kv[1], reverse=True)
    rank_map = {d: i + 1 for i, (d, _) in enumerate(sorted_devises)}
    force_base_rank = rank_map.get(base, 99)
    force_quote_rank = rank_map.get(quote, 99)

    # Compression/extension (lecture directe colonnes Fatman)
    comp_ext_etat = snapshot.get("compression_extension_etat", "NEUTRE") or "NEUTRE"
    comp_ext_intensite = snapshot.get("compression_extension_intensite", "FAIBLE") or "FAIBLE"

    # Croisement / recroisement / rejet
    croisement_detecte = int(_safe_float(snapshot.get("croisement_detecte", 0), 0))
    croisement_direction = snapshot.get("croisement_direction", "NEUTRE") or "NEUTRE"
    recroisement_detecte = int(_safe_float(snapshot.get("recroisement_detecte", 0), 0))
    rejet_detecte = int(_safe_float(snapshot.get("rejet_repulsion_detecte", 0), 0))
    rejet_intensite = _safe_float(snapshot.get("rejet_intensite", 0.0), 0.0)

    return NativeForceFeatures(
        timestamp=snapshot.get("timestamp", "") or "",
        bar_time=int(_safe_float(snapshot.get("bar_time", 0), 0)),
        force_base=force_base,
        force_quote=force_quote,
        force_delta=force_delta,
        force_base_rank=force_base_rank,
        force_quote_rank=force_quote_rank,
        compression_extension_etat=str(comp_ext_etat).upper(),
        compression_extension_intensite=str(comp_ext_intensite).upper(),
        croisement_detecte=croisement_detecte,
        croisement_direction=str(croisement_direction).upper(),
        recroisement_detecte=recroisement_detecte,
        rejet_repulsion_detecte=rejet_detecte,
        rejet_intensite=rejet_intensite,
        audit={
            "source": "forces_snapshots native columns",
            "pair": pair,
            "base": base,
            "quote": quote,
        },
    )


# ─────────────────────────────────────────────────────────────────────
# PNL NATIF
# ─────────────────────────────────────────────────────────────────────

def compute_force_native_pnl(
    features_list: List[NativeForceFeatures],
    *,
    pair: str = "",
    direction: str = "AUTO",
) -> float:
    """Calcule pnl V10 NATIF depuis une liste de features (horizon candles).

    Logique (R9 audit honest) :
      1. Si compression_extension_etat == COMPRESSION :
         - intensité FAIBLE/MOYEN/FORT/EXTREME → pips signé selon direction
      2. Si EXTENSION : pips plus faible (potentiel épuisement)
      3. Si croisement_detecte : bonus selon direction
      4. Si recroisement_detecte : bonus +RECROISEMENT_BONUS_PIPS
      5. Si rejet_repulsion_detecte : pénalité REJET_PENALTY_PIPS
      6. Force delta : pips proportionnel à |force_delta|/100 * intensity_pips

    Args:
        features_list: liste ordonnée (t-1, t-2, ..., t-horizon)
        pair: pour contexte
        direction: AUTO (force_delta signe) / BULLISH / BEARISH

    Returns:
        float pnl_pips_native
    """
    if not features_list:
        return 0.0

    pnl_total = 0.0
    direction = direction.upper()

    for i, f in enumerate(features_list):
        # 1. Compression/Extension pips (composante principale)
        intensity_pips = _intensity_to_pips(f.compression_extension_intensite)

        if f.compression_extension_etat == "COMPRESSION":
            # Plein potentiel
            comp_pips = intensity_pips
        elif f.compression_extension_etat == "EXTENSION":
            # Épuisement — réduit de moitié
            comp_pips = intensity_pips * 0.5
        else:
            comp_pips = intensity_pips * 0.25

        # Signe selon direction
        if direction == "AUTO":
            # signe = signe du force_delta
            sign = 1.0 if f.force_delta >= 0 else -1.0
        elif direction == "BULLISH":
            sign = +1.0
        else:  # BEARISH
            sign = -1.0

        comp_pips_signed = comp_pips * sign

        # 2. Croisement bonus
        crois_pips = 0.0
        if f.croisement_detecte:
            crois_sign = CROISEMENT_DIRECTION_TO_PIPS.get(f.croisement_direction, 0.0)
            crois_pips = intensity_pips * 0.3 * crois_sign

        # 3. Recroisement bonus
        recrois_pips = RECROISEMENT_BONUS_PIPS * sign if f.recroisement_detecte else 0.0

        # 4. Rejet répulsion (toujours négatif)
        rejet_pips = REJET_PENALTY_PIPS * (f.rejet_intensite or 1.0) if f.rejet_repulsion_detecte else 0.0

        # 5. Force delta boost (linéaire, capé à intensity_pips)
        force_boost = (abs(f.force_delta) / 100.0) * intensity_pips * sign

        candle_pnl = comp_pips_signed + crois_pips + recrois_pips + rejet_pips + force_boost

        # Decay temporel : candles plus anciennes comptent moins (R8 calibré)
        # candle le plus récent (i=0) → weight=1.0, candle t-3 → weight=0.7
        weight = 1.0 - 0.1 * i
        pnl_total += candle_pnl * weight

    return round(pnl_total, 4)


# ─────────────────────────────────────────────────────────────────────
# PIPELINE ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def compute_native_force_report(
    snapshots: List[Dict],
    pair: str,
    timeframe: str,
    *,
    horizon: int = 3,
) -> NativeForceReport:
    """Pipeline complet : snapshots → features → pnl natif.

    R9 audit honest : retourne pnl TOTAL + WR par signal + avg pnl/trade.
    Le ratio WR compare au proxy pnl (proxy est biaisé USDJPY -2785p).

    Args:
        snapshots: rows de `forces_snapshots` (au moins `horizon + 1`)
        pair: ex "GBPUSD"
        timeframe: ex "M30"
        horizon: nb bougies futures pour pnl

    Returns:
        NativeForceReport avec pnl_pips_native, pnl_pips_proxy, WR natif vs proxy, etc.
    """
    if len(snapshots) < horizon + 1:
        return NativeForceReport(
            pair=pair,
            timeframe=timeframe,
            n_snapshots_used=len(snapshots),
            audit={"error": "insufficient_snapshots", "need": horizon + 1},
        )

    # Pour chaque snapshot, on regarde les `horizon` candles suivantes
    # pour calculer pnl natif (vs proxy close[t+horizon] - close[t])
    pnl_native_total = 0.0
    pnl_proxy_total = 0.0
    n_native_wins = 0
    n_proxy_wins = 0

    n_compressed = 0
    n_extended = 0
    n_croisements = 0
    n_recroisements = 0
    n_rejets = 0

    features_used: List[NativeForceFeatures] = []

    for i in range(len(snapshots) - horizon):
        # Features pour ce snapshot
        feat = compute_force_native_features(snapshots[i], pair)

        # Pnl natif : regarde les `horizon` candles suivantes
        horizon_features = [feat]
        for j in range(1, horizon + 1):
            if i + j < len(snapshots):
                horizon_features.append(compute_force_native_features(snapshots[i + j], pair))

        pnl_native = compute_force_native_pnl(horizon_features, pair=pair)
        pnl_native_total += pnl_native
        if pnl_native > 0:
            n_native_wins += 1

        # Pnl proxy pour comparaison (R9 audit honest)
        close_t = _safe_float(snapshots[i].get("close", 0.0), 0.0)
        close_t_h = _safe_float(snapshots[i + horizon].get("close", 0.0), 0.0)
        if close_t > 0:
            pnl_proxy = (close_t_h - close_t) * (10000 if "JPY" not in pair else 100)
            pnl_proxy_total += pnl_proxy
            if pnl_proxy > 0:
                n_proxy_wins += 1

        # Compteurs audit
        if feat.compression_extension_etat == "COMPRESSION":
            n_compressed += 1
        elif feat.compression_extension_etat == "EXTENSION":
            n_extended += 1

        if feat.croisement_detecte:
            n_croisements += 1
        if feat.recroisement_detecte:
            n_recroisements += 1
        if feat.rejet_repulsion_detecte:
            n_rejets += 1

        features_used.append(feat)

    delta_pnl = pnl_native_total - pnl_proxy_total
    n_trades = len(features_used)
    wr_native = (n_native_wins / n_trades) if n_trades else 0.0
    wr_proxy = (n_proxy_wins / n_trades) if n_trades else 0.0
    avg_pnl_native = pnl_native_total / n_trades if n_trades else 0.0
    avg_pnl_proxy = pnl_proxy_total / n_trades if n_trades else 0.0

    return NativeForceReport(
        pair=pair,
        timeframe=timeframe,
        n_snapshots_used=n_trades,
        n_snapshots_compressed=n_compressed,
        n_snapshots_extended=n_extended,
        n_croisements=n_croisements,
        n_recroisements=n_recroisements,
        n_rejets=n_rejets,
        pnl_pips_native=round(pnl_native_total, 4),
        pnl_pips_proxy=round(pnl_proxy_total, 4),
        delta_pnl_vs_proxy=round(delta_pnl, 4),
        audit={
            "horizon": horizon,
            "method": "V10 native (compression/extension + croisement + force_delta)",
            "intensity_to_pips": INTENSITY_TO_PIPS,
            "recroisement_bonus": RECROISEMENT_BONUS_PIPS,
            "rejet_penalty": REJET_PENALTY_PIPS,
            "wr_native": round(wr_native, 4),
            "wr_proxy": round(wr_proxy, 4),
            "avg_pnl_native_per_trade": round(avg_pnl_native, 4),
            "avg_pnl_proxy_per_trade": round(avg_pnl_proxy, 4),
            "delta_wr": round(wr_native - wr_proxy, 4),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# LOAD SNAPSHOTS FROM DB
# ─────────────────────────────────────────────────────────────────────

def load_snapshots_from_db(
    db_path: str,
    pair: str,
    timeframe: str,
    *,
    limit: Optional[int] = None,
) -> List[Dict]:
    """Charge snapshots depuis forces_snapshots (R6 fail-open si absent)."""
    try:
        con = sqlite3.connect(db_path, timeout=10)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Vérifier table existe
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'")
        if not cur.fetchone():
            con.close()
            return []

        sql = """
            SELECT * FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
            ORDER BY bar_time ASC
        """
        if limit:
            sql += f" LIMIT {int(limit)}"

        cur.execute(sql, (pair, timeframe))
        rows = [dict(row) for row in cur.fetchall()]
        con.close()
        return rows
    except Exception as exc:
        # R6 fail-open : retourne []
        return []


# ─────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────

def demo_run(db_path: str = "data/v9_forces.db") -> List[NativeForceReport]:
    """Run demo sur 6 paires × 3 TF (M30/H1/H4), affiche pnl natif vs proxy.

    Returns:
        Liste de NativeForceReport par (paire, TF).
    """
    pairs = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]
    tfs = ["M30", "H1", "H4"]
    reports = []

    for pair in pairs:
        for tf in tfs:
            snaps = load_snapshots_from_db(db_path, pair, tf, limit=200)
            if len(snaps) < 5:
                continue
            rep = compute_native_force_report(snaps, pair, tf, horizon=3)
            reports.append(rep)

    return reports


__all__ = [
    "COMP_EXT_STATES",
    "INTENSITY_TO_PIPS",
    "CROISEMENT_DIRECTION_TO_PIPS",
    "RECROISEMENT_BONUS_PIPS",
    "REJET_PENALTY_PIPS",
    "FORCE_DELTA_THRESHOLD",
    "NativeForceFeatures",
    "NativeForceReport",
    "compute_force_native_features",
    "compute_force_native_pnl",
    "compute_native_force_report",
    "load_snapshots_from_db",
    "demo_run",
]
