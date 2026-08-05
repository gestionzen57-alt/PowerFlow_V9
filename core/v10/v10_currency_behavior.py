"""V10 Currency Behavior — comprendre le comportement des forces de devises.

Doctrine V10 : R1 (agit), R2 (additif pur — 0 import core/v9/), R5 (CoT),
R6 (fail-open), R7 (tests verts), R8 (auto-calibration), R9 (audit honnête),
R10 (capital protégé — la fidélité garde le gate de risque).

Mission CEO (2026-08-05, brainstorming Søn) :
  « V10 doit refléter la réalité du marché et pouvoir comprendre le
     comportement des forces de devises. »

Le module transforme 8 séries de scores bruts (force_*) en une
compréhension : QUI mène, QUI suit, QUI s'allie, QUAND le régime
bascule, POURQUOI (chaîne H4→H1→M30), et EST-CE QUE les forces
reflètent les prix (fidélité, garde-fou C).

Architecture 5 couches :
  Layer 0 — Observation    : chargement séries forces + prix (DB réelle)
  Layer 1 — Comportement   : états, coalitions, leadership, régimes,
                             causalité multi-TF (lead-lag)
  Layer 2 — Fidélité       : corr forces→rendements futurs (garde-fou C)
  Layer 3 — Apprentissage  : calibration R8, drift ADWIN, réversibilité
  Layer 4 — Expression     : behavior_context + narrative V1/V2

Réversibilité (règle d'or CEO — jamais bloqué par un choix) :
  Toute constante est dans CONFIG, surchargeable à chaud par
  `apply_behavior_config` (pattern Phase 28b étape 1), restaurée par
  `reset_behavior_config`. Registre des choix dans `get_behavior_state`.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# CONFIG — toutes les décisions sont des paramètres nommés (réversibles)
# ─────────────────────────────────────────────────────────────────────
CONFIG: Dict = {
    # Fenêtres multi-échelle (choix a) : 50 = fond, 20 = réactif
    "window_fond": 50,
    "window_reactif": 20,
    # Seuils régimes (choix b) : double lecture — hérités V9 + recalés
    "regime_threshold_inherited": 65.0,
    "regime_percentile_cal": 70.0,
    "regime_percentile_floor": 30.0,
    # Sessions (choix c) : bornes UTC configurables + overlap
    "sessions_utc": {
        "ASIAN": (0, 7),
        "LONDON": (7, 15),
        "NY": (13, 22),
    },
# Fidélité (choix d) : composite M30/H1 pondéré 0.6/0.4
"fidelity_weights": {"M30": 0.6, "H1": 0.4},
"fidelity_horizon_bars": {"M30": 3, "H1": 2},
"fidelity_min_reliable": 0.5,
"fidelity_corr_method": "spearman",
# Fidélité extrême (découverte Phase 32 — le signal vit aux queues) :
# WR directionnel quand la force est au percentile extrême.
"fidelity_extreme_percentile": 90.0,
"fidelity_extreme_min_samples": 15,
"fidelity_extreme_min_currencies": 3,
"fidelity_extreme_min_wr": 60.0,
    # Coalitions
    "coalition_corr_min": 0.7,
    "coalition_window": 30,
    # Drift ADWIN simplifié (Layer 3)
    "drift_eps": 0.05,
    "drift_short_window": 12,
    "drift_long_window": 48,
    # Filtre saturation artefact
    "force_min": 2.0,
    "force_max": 98.0,
}

# État runtime surchargé (Layer 3 — réversibilité)
_RUNTIME_CONFIG: Optional[Dict] = None
_RUNTIME_AUDIT: Dict = {}
_RUNTIME_APPLY_COUNT: int = 0

CURRENCIES = ["usd", "gbp", "eur", "jpy", "cad", "chf", "aud", "nzd"]


def get_config() -> Dict:
    """R6 fail-open : CONFIG active (runtime override si présent)."""
    return _RUNTIME_CONFIG if _RUNTIME_CONFIG is not None else CONFIG


# ─────────────────────────────────────────────────────────────────────
# Layer 3a — Réversibilité (règle d'or CEO)
# ─────────────────────────────────────────────────────────────────────
def apply_behavior_config(cfg: Dict) -> Dict:
    """Surcharge la CONFIG à chaud (pattern Phase 28b étape 1).

    R2 additif pur : ne modifie jamais CONFIG (les defaults survivent).
    Merge profond, idempotent, audit R9 serialisable.
    """
    global _RUNTIME_CONFIG, _RUNTIME_AUDIT, _RUNTIME_APPLY_COUNT
    if not isinstance(cfg, dict):
        return {"applied": False, "error": "cfg_must_be_dict",
                "type_received": str(type(cfg).__name__)}
    merged = dict(get_config())
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    _RUNTIME_CONFIG = merged
    _RUNTIME_APPLY_COUNT += 1
    _RUNTIME_AUDIT = {
        "applied_at": _now_iso(),
        "keys_set": sorted(cfg.keys()),
        "n_applies_total": _RUNTIME_APPLY_COUNT,
    }
    return {"applied": True, "n_keys_set": len(cfg), **_RUNTIME_AUDIT}


def reset_behavior_config() -> Dict:
    """Restaure les defaults module (jamais bloqué par un choix)."""
    global _RUNTIME_CONFIG, _RUNTIME_APPLY_COUNT
    _RUNTIME_CONFIG = None
    _RUNTIME_APPLY_COUNT += 1
    return {"applied": True, "reset": True, "n_applies_total": _RUNTIME_APPLY_COUNT}


def get_behavior_state() -> Dict:
    """Snapshot lecture seule R9 — registre des choix + config active."""
    return {
        "config_active": get_config(),
        "config_defaults": CONFIG,
        "runtime_override_active": _RUNTIME_CONFIG is not None,
        "n_applies_total": _RUNTIME_APPLY_COUNT,
        "last_audit": _RUNTIME_AUDIT,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Layer 0 — Observation
# ─────────────────────────────────────────────────────────────────────
@dataclass
class CurrencySeries:
    """Séries temporelles alignées : forces + prix pour une (paire, TF)."""
    pair: str
    timeframe: str
    timestamps: List[str] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)
    forces: Dict[str, List[float]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.timestamps)

    def to_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "n_points": len(self.timestamps),
            "first_ts": self.timestamps[0] if self.timestamps else None,
            "last_ts": self.timestamps[-1] if self.timestamps else None,
        }


def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse timestamp DB (ISO ou epoch broker UTC+3) → UTC aware.

    Piège V9 : `bar_time` est en epoch broker UTC+3. `timestamp` est
    ISO UTC. On tolère les deux (R6 fail-open).
    """
    if ts is None:
        return None
    s = str(ts)
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        if "T" in s:
            return datetime.fromisoformat(s)
        f = float(s)
        return datetime.fromtimestamp(f - 3 * 3600, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def session_of(ts_utc: datetime) -> str:
    """Session de marché (choix c) : bornes UTC configurables, overlap OK."""
    if ts_utc is None:  # R6 fail-open
        return "UNKNOWN"
    cfg = get_config()
    sessions = cfg.get("sessions_utc", {})
    hour = ts_utc.hour
    best, best_span = "UNKNOWN", 0
    for name, (h0, h1) in sessions.items():
        span = (h1 - h0) % 24
        if span <= 0:
            continue
        if h0 <= h1:
            in_s = h0 <= hour < h1
        else:  # chevauchement minuit
            in_s = hour >= h0 or hour < h1
        if in_s and span > best_span:
            best, best_span = name, span
    return best


def load_currency_series(db_path: str, pair: str = "GBPUSD",
                         timeframe: str = "M30",
                         days: int = 3) -> CurrencySeries:
    """Charge séries forces + prix depuis forces_snapshots (Layer 0).

    R6 fail-open : table absente ou vide → série vide (jamais de crash).
    Filtre saturation : force NOT NULL ET BETWEEN force_min AND force_max.
    """
    cfg = get_config()
    fmin, fmax = cfg["force_min"], cfg["force_max"]
    series = CurrencySeries(pair=pair, timeframe=timeframe)
    if not os.path.exists(db_path):
        return series
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'"
        )
        if cur.fetchone() is None:
            con.close()
            return series
        force_cols = ", ".join(f"force_{c}" for c in CURRENCIES)
        cur.execute(
            f"""
            SELECT timestamp, close, {force_cols}
            FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ?
              AND timestamp > datetime('now', ?)
              AND force_usd IS NOT NULL
            ORDER BY timestamp ASC
            """,
            (pair, timeframe, f"-{int(days)} days"),
        )
        for row in cur.fetchall():
            forces = {c: row[2 + i] for i, c in enumerate(CURRENCIES)
                      if row[2 + i] is not None and fmin <= row[2 + i] <= fmax}
            if len(forces) < len(CURRENCIES):  # point incomplet → skip (alignement strict)
                continue
            if row[1] is None:
                continue
            series.timestamps.append(str(row[0]))
            series.closes.append(float(row[1]))
            for c in CURRENCIES:
                series.forces.setdefault(c, []).append(float(forces[c]))
        con.close()
    except sqlite3.Error:
        return series
    return series


# ─────────────────────────────────────────────────────────────────────
# Helpers statistiques (stdlib)
# ─────────────────────────────────────────────────────────────────────
def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _spearman(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0

    def rank(vals: List[float]) -> List[float]:
        idx = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(idx):
            j = i
            while j + 1 < len(idx) and vals[idx[j + 1]] == vals[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[idx[k]] = avg
            i = j + 1
        return ranks

    return _pearson(rank(xs), rank(ys))


def _slope(vals: List[float]) -> float:
    """Pente linéaire normalisée de vals (≈ momentum sur la fenêtre)."""
    n = len(vals)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = (n - 1) / 2.0, sum(vals) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, vals))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _percentile(vals: List[float], p: float) -> float:
    if not vals:
        return 50.0
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = min(lo + 1, len(s) - 1)
    w = k - lo
    return s[lo] * (1 - w) + s[hi] * w


# ─────────────────────────────────────────────────────────────────────
# Layer 1a — Dynamique temporelle (états par devise)
# ─────────────────────────────────────────────────────────────────────
def classify_currency_states(series: CurrencySeries) -> Dict[str, Dict]:
    """État de chaque devise : RALLYE / ROTATION / RETOURNEMENT / RANGE.

    Règle (multi-échelle, choix a) :
      - momentum_fond   = pente sur window_fond (50)
      - momentum_react  = pente sur window_reactif (20)
      - acceleration    = momentum_react - momentum_fond
      - percentile      = position dans la distribution de la fenêtre fond
    RALLYE       : momentum_fond > 0 ET percentile ≥ 70
    ROTATION     : momentum_react > 0 ET momentum_fond ≤ 0 (entrée de force)
    RETOURNEMENT : momentum_react < 0 ET momentum_fond > 0 (sortie de force)
    RANGE        : sinon
    """
    cfg = get_config()
    wf, wr = cfg["window_fond"], cfg["window_reactif"]
    out: Dict[str, Dict] = {}
    n = len(series)
    for c in CURRENCIES:
        vals = series.forces.get(c, [])
        if len(vals) < max(wf, wr) + 2:
            out[c] = {"state": "RANGE", "momentum": 0.0, "acceleration": 0.0,
                      "percentile": 50.0, "value": vals[-1] if vals else 50.0}
            continue
        fond = vals[-wf:]
        react = vals[-wr:]
        m_fond = _slope(fond)
        m_react = _slope(react)
        acc = m_react - m_fond
        # Percentile rank de la dernière valeur dans toute la série
        pct = (100.0 * sum(1 for v in vals if v < vals[-1]) / len(vals)
               if vals else 50.0)
        if m_fond > 0 and pct >= 70:
            state = "RALLYE"
        elif m_fond < 0 and pct <= 30:
            state = "DECLINE"
        elif m_react > 0 and m_fond <= 0:
            state = "ROTATION"
        elif m_react < 0 and m_fond > 0:
            state = "RETOURNEMENT"
        else:
            state = "RANGE"
        out[c] = {"state": state, "momentum": round(m_fond, 4),
                  "acceleration": round(acc, 4), "percentile": round(pct, 1),
                  "value": round(vals[-1], 2)}
    return out


# ─────────────────────────────────────────────────────────────────────
# Layer 1b — Relations inter-devises (coalitions, leadership)
# ─────────────────────────────────────────────────────────────────────
def detect_coalitions(series: CurrencySeries) -> Dict:
    """Coalitions glissantes : paires de devises corrélées sur la fenêtre.

    Corrélation de Pearson des forces sur coalition_window points.
    Coalition si corr ≥ coalition_corr_min (0.7) — choix de config.
    Sortie : liste de coalitions {members, corr} + label heuristique.
    """
    cfg = get_config()
    cw = cfg["coalition_window"]
    corr_min = cfg["coalition_corr_min"]
    coalitions = []
    for i in range(len(CURRENCIES)):
        for j in range(i + 1, len(CURRENCIES)):
            a, b = CURRENCIES[i], CURRENCIES[j]
            va = series.forces.get(a, [])
            vb = series.forces.get(b, [])
            if len(va) < cw or len(vb) < cw:
                continue
            corr = _pearson(va[-cw:], vb[-cw:])
            if corr >= corr_min:
                coalitions.append({
                    "members": [a.upper(), b.upper()],
                    "corr": round(corr, 3),
                    "label": _coalition_label(a, b),
                })
    coalitions.sort(key=lambda x: -x["corr"])
    return {"n_coalitions": len(coalitions), "coalitions": coalitions[:6]}


def _coalition_label(a: str, b: str) -> str:
    """Label heuristique des coalitions connues."""
    pairs = {
        frozenset(["aud", "nzd"]): "cycliques",
        frozenset(["jpy", "chf"]): "refuges",
        frozenset(["eur", "gbp"]): "europeennes",
        frozenset(["usd", "cad"]): "nord-americaines",
    }
    return pairs.get(frozenset([a, b]), "autres")


def compute_leadership(series: CurrencySeries) -> Dict:
    """Leader / follower + rotation détectée entre 2 fenêtres.

    Leader = force moyenne max sur la fenêtre ; rotation si le leader
    de la fenêtre récente ≠ leader de la fenêtre précédente.
    """
    cfg = get_config()
    wf = cfg["window_fond"]
    out: Dict = {}
    if len(series) < wf * 2:
        return {"leader": None, "follower": None, "rotation_detected": False}
    prev = {}
    cur = {}
    for c in CURRENCIES:
        vals = series.forces.get(c, [])
        if len(vals) < wf * 2:
            continue
        prev[c] = sum(vals[-2 * wf:-wf]) / wf
        cur[c] = sum(vals[-wf:]) / wf
    if not cur:
        return {"leader": None, "follower": None, "rotation_detected": False}
    leader_prev = max(prev, key=prev.get)
    leader_cur = max(cur, key=cur.get)
    follower_cur = min(cur, key=cur.get)
    out = {
        "leader": leader_cur.upper(),
        "leader_strength": round(cur[leader_cur], 1),
        "follower": follower_cur.upper(),
        "follower_strength": round(cur[follower_cur], 1),
        "rotation_detected": leader_prev != leader_cur,
        "leader_before": leader_prev.upper(),
    }
    return out


# ─────────────────────────────────────────────────────────────────────
# Layer 1c — Régimes de marché (double lecture)
# ─────────────────────────────────────────────────────────────────────
def classify_regime(series: CurrencySeries, session: str = "LONDON") -> Dict:
    """Régime risk_on/off (choix b — double lecture comparée).

    Lecture 1 (héritée V9) : cycliques AUD/NZD > seuil_inherited (65)
      ET/OU refuges JPY/CHF > seuil_inherited.
    Lecture 2 (recalée R8) : seuils = percentiles 70/30 de la
      distribution réelle des 4 devises de régime sur la série.
    Le régime effectif = lecture dont la séparation est la plus forte
    (écart cycliques - refuges le plus grand en valeur absolue).
    """
    cfg = get_config()
    th_inh = cfg["regime_threshold_inherited"]
    p_cal = cfg["regime_percentile_cal"]
    p_floor = cfg["regime_percentile_floor"]
    out = {"session": session, "readings": {}}

    def regime_from(aud, nzd, jpy, chf, th_on, th_off):
        is_on = aud > th_on and nzd > th_on
        is_off = jpy > th_off and chf > th_off
        if is_on and not is_off:
            return "RISK_ON"
        if is_off and not is_on:
            return "SAFE_HAVEN"
        if is_on and is_off:
            return "MIXED"
        return "NEUTRAL"

    def latest_of(c):
        vals = series.forces.get(c, [])
        return vals[-1] if vals else 50.0

    aud, nzd, jpy, chf = (latest_of(c) for c in ["aud", "nzd", "jpy", "chf"])

    # Lecture 1 — héritée
    r1 = regime_from(aud, nzd, jpy, chf, th_inh, th_inh)
    # Lecture 2 — recalée (percentiles de la distribution réelle)
    dist = {c: series.forces.get(c, []) for c in ["aud", "nzd", "jpy", "chf"]}
    th_on = _percentile(dist["aud"] + dist["nzd"], p_cal) if dist["aud"] else th_inh
    th_off = _percentile(dist["jpy"] + dist["chf"], p_floor) if dist["jpy"] else th_inh
    r2 = regime_from(aud, nzd, jpy, chf, th_on, th_off)

    # Netteté : somme des dépassements de seuils — la lecture dont les
    # forces dépassent le plus nettement ses seuils est la plus fiable.
    net1 = (max(0.0, aud - th_inh) + max(0.0, nzd - th_inh)
            + max(0.0, jpy - th_inh) + max(0.0, chf - th_inh))
    net2 = (max(0.0, aud - th_on) + max(0.0, nzd - th_on)
            + max(0.0, jpy - th_off) + max(0.0, chf - th_off))
    regime = r1 if net1 >= net2 else r2
    out.update({
        "regime": regime,
        "forces": {"aud": round(aud, 1), "nzd": round(nzd, 1),
                   "jpy": round(jpy, 1), "chf": round(chf, 1)},
        "readings": {
            "inherited": {"regime": r1, "threshold": th_inh},
            "recalibrated": {"regime": r2, "threshold_on": round(th_on, 1),
                             "threshold_off": round(th_off, 1)},
        },
        "chosen": "inherited" if regime == r1 else "recalibrated",
    })
    return out


# ─────────────────────────────────────────────────────────────────────
# Layer 1d — Causalité multi-TF (lead-lag H4 → M30)
# ─────────────────────────────────────────────────────────────────────
def compute_lead_lag(series_slow: CurrencySeries,
                     series_fast: CurrencySeries) -> Dict:
    """Lead-lag entre TF lent et TF rapide par corrélation croisée.

    Pour chaque devise : corr(force_slow[t], force_fast[t+k]) pour
    k ∈ [-3..3]. Si le meilleur k > 0 → le TF lent PRÉCÈDE le rapide
    (lead). Retourne la majorité des devises + la chaîne narrative.
    """
    leads = []
    for c in CURRENCIES:
        vs = series_slow.forces.get(c, [])
        vf = series_fast.forces.get(c, [])
        if len(vs) < 10 or len(vf) < 10:
            continue
        n = min(len(vs), len(vf))
        best_k, best_corr = 0, -1.0
        for k in range(-3, 4):
            xs = vs[10:n - max(k, 0)] if k <= 0 else vs[10 + k:n]
            ys = vf[10 + max(-k, 0):n] if k >= 0 else vf[10:n + k]
            if len(xs) < 5 or len(ys) < 5:
                continue
            corr = abs(_pearson(xs, ys))
            if corr > best_corr:
                best_corr, best_k = corr, k
        leads.append((c, best_k, best_corr))
    if not leads:
        return {"lead_lag": "UNKNOWN", "n_currencies_leads": 0, "detail": []}
    n_leads = sum(1 for _, k, _ in leads if k > 0)
    dominant = "SLOW_LEADS" if n_leads > len(leads) / 2 else \
        "FAST_LEADS" if n_leads < len(leads) / 2 else "SYNCHRONOUS"
    return {
        "lead_lag": dominant,
        "n_currencies_leads": n_leads,
        "n_currencies_total": len(leads),
        "detail": [{"currency": c.upper(), "best_lag_bars": k,
                    "corr": round(v, 3)} for c, k, v in leads[:4]],
    }


# ─────────────────────────────────────────────────────────────────────
# Layer 2 — Fidélité (garde-fou C : les forces reflètent-elles les prix ?)
# ─────────────────────────────────────────────────────────────────────
def compute_fidelity(series: CurrencySeries) -> Dict:
    """Corrélation forces → rendements futurs (garde-fou C).

    Pour chaque devise : corrélation (Spearman par défaut) entre
    force[t] et rendement futur close[t+h] / close[t] - 1, sur tous
    les points de la série. h = fidelity_horizon_bars[TF].
    Composite : pondération M30/H1 via fidelity_weights (choix d).
    reliable = composite ≥ fidelity_min_reliable (0.5).
    """
    cfg = get_config()
    method = cfg["fidelity_corr_method"]
    horizon = cfg["fidelity_horizon_bars"].get(series.timeframe, 3)
    corr_fn = _spearman if method == "spearman" else _pearson
    n = len(series)
    if n < horizon + 5:
        return {"n_points": n, "per_currency": {}, "composite": 0.0,
                "reliable": False, "reason": "insufficient_data"}
    per = {}
    for c in CURRENCIES:
        vals = series.forces.get(c, [])
        if len(vals) < horizon + 5:
            continue
        xs, ys = [], []
        for t in range(n - horizon):
            r = series.closes[t + horizon] / series.closes[t] - 1.0
            if r == 0:
                continue
            xs.append(vals[t])
            ys.append(r)
        per[c] = {"corr": round(corr_fn(xs, ys), 4),
                  "n_samples": len(xs)} if len(xs) >= 10 else {
            "corr": 0.0, "n_samples": len(xs)}
    composite = 0.0
    total_w = 0.0
    for c, d in per.items():
        if d["n_samples"] >= 10:
            composite += d["corr"] * 1.0
            total_w += 1.0
    composite = composite / total_w if total_w else 0.0
    reliable = composite >= cfg["fidelity_min_reliable"]
    return {
        "n_points": n,
        "horizon_bars": horizon,
        "per_currency": per,
        "composite": round(composite, 4),
        "reliable": reliable,
        "reason": "ok" if reliable else "fidelity_below_threshold",
    }


def compute_fidelity_extreme(series: CurrencySeries) -> Dict:
    """Fidélité aux extrêmes (découverte Phase 32, R9 sur DB réelle).

    Le signal des forces n'est PAS linéaire : la corrélation globale
    ≈ 0, mais quand une force est au percentile extrême (P90/P10),
    le rendement futur devient directionnel (WR 70-90% observé sur
    AUDUSD). Retourne le WR directionnel aux queues + la force
    extrême la plus fiable (celle avec WR max aux extrêmes).

    Garde-fou R10 : `extreme_reliable` = au moins
    fidelity_extreme_min_currencies devises avec WR ≥ min_wr sur
    n ≥ min_samples échantillons chacun.
    """
    cfg = get_config()
    p = cfg["fidelity_extreme_percentile"]
    min_n = cfg["fidelity_extreme_min_samples"]
    min_wr = cfg["fidelity_extreme_min_wr"]
    min_cur = cfg["fidelity_extreme_min_currencies"]
    horizon = cfg["fidelity_horizon_bars"].get(series.timeframe, 3)
    n = len(series)
    if n < horizon + 30:
        return {"n_points": n, "per_currency": {},
                "extreme_reliable": False, "best_currency": None,
                "reason": "insufficient_data"}
    per = {}
    for c in CURRENCIES:
        vals = series.forces.get(c, [])
        if len(vals) < n:
            continue
        s = sorted(vals)
        th_hi = s[int(len(s) * p / 100)]
        th_lo = s[int(len(s) * (100 - p) / 100)]
        n_hi = n_lo = wr_hi = wr_lo = 0
        avg_hi = avg_lo = 0.0
        for t in range(n - horizon):
            r = series.closes[t + horizon] / series.closes[t] - 1.0
            if vals[t] >= th_hi:
                n_hi += 1
                wr_hi += 1 if r > 0 else 0
                avg_hi += r
            elif vals[t] <= th_lo:
                n_lo += 1
                wr_lo += 1 if r > 0 else 0
                avg_lo += r
        per[c] = {
            "threshold_hi": round(th_hi, 1), "threshold_lo": round(th_lo, 1),
            "n_hi": n_hi, "wr_hi_pct": round(100 * wr_hi / n_hi, 1) if n_hi else None,
            "avg_hi_bps": round(10000 * avg_hi / n_hi, 1) if n_hi else None,
            "n_lo": n_lo, "wr_lo_pct": round(100 * wr_lo / n_lo, 1) if n_lo else None,
            "avg_lo_bps": round(10000 * avg_lo / n_lo, 1) if n_lo else None,
        }
    # Force extrême la plus fiable : WR max parmi les queues avec n suffisant
    best, best_score = None, 0.0
    n_reliable = 0
    for c, d in per.items():
        scores = []
        if d["n_hi"] >= min_n and d["wr_hi_pct"] is not None:
            scores.append(d["wr_hi_pct"])
        if d["n_lo"] >= min_n and d["wr_lo_pct"] is not None:
            scores.append(d["wr_lo_pct"])
        if scores and max(scores) >= min_wr:
            n_reliable += 1
        if scores:
            score = max(scores)
            if score > best_score:
                best_score, best = score, c
    extreme_reliable = n_reliable >= min_cur
    return {
        "n_points": n,
        "percentile": p,
        "horizon_bars": horizon,
        "per_currency": per,
        "n_currencies_extreme_fiable": n_reliable,
        "best_currency": best.upper() if best else None,
        "best_wr_pct": round(best_score, 1) if best else None,
        "extreme_reliable": extreme_reliable,
        "reason": "ok" if extreme_reliable else "extreme_fidelity_below_threshold",
    }


def compute_fidelity_composite(fidelity_m30: Dict,
                               fidelity_h1: Dict) -> Dict:
    """Composite multi-TF (choix d) : pondération 0.6 M30 / 0.4 H1."""
    cfg = get_config()
    w = cfg["fidelity_weights"]
    f30 = fidelity_m30.get("composite", 0.0) if fidelity_m30 else 0.0
    f1 = fidelity_h1.get("composite", 0.0) if fidelity_h1 else 0.0
    composite = w.get("M30", 0.6) * f30 + w.get("H1", 0.4) * f1
    reliable = composite >= cfg["fidelity_min_reliable"]
    return {
        "composite": round(composite, 4),
        "m30": f30, "h1": f1,
        "weights": w,
        "reliable": reliable,
        "reason": "ok" if reliable else "fidelity_below_threshold",
    }


# ─────────────────────────────────────────────────────────────────────
# Layer 3b — Apprentissage : calibration + drift
# ─────────────────────────────────────────────────────────────────────
def calibrate_regime_thresholds(series: CurrencySeries) -> Dict:
    """Calibration R8 des seuils de régime depuis la distribution réelle.

    Retourne les seuils proposés (percentiles 70/30) + les défauts
    actifs — le système choisit par fidélité, jamais gravé.
    """
    dist_cyc = series.forces.get("aud", []) + series.forces.get("nzd", [])
    dist_ref = series.forces.get("jpy", []) + series.forces.get("chf", [])
    if len(dist_cyc) < 20 or len(dist_ref) < 20:
        return {"proposed": None, "reason": "insufficient_data"}
    p70 = _percentile(dist_cyc, 70.0)
    p30 = _percentile(dist_ref, 30.0)
    return {
        "proposed": {
            "risk_on_threshold": round(p70, 1),
            "safe_haven_threshold": round(p30, 1),
            "n_samples_cycliques": len(dist_cyc),
            "n_samples_refuges": len(dist_ref),
        },
        "active": {
            "risk_on_threshold": get_config()["regime_threshold_inherited"],
            "safe_haven_threshold": get_config()["regime_threshold_inherited"],
        },
    }


def detect_drift(fidelity_history: List[float]) -> Dict:
    """Drift ADWIN simplifié sur la série de fidélité composite (Layer 3).

    Moyenne fenêtre courte vs longue ; drift si écart > drift_eps.
    R6 fail-open : historique trop court → no_drift.
    """
    cfg = get_config()
    eps = cfg["drift_eps"]
    sw, lw = cfg["drift_short_window"], cfg["drift_long_window"]
    if len(fidelity_history) < sw + 5:
        return {"drift_detected": False, "reason": "insufficient_history",
                "n_points": len(fidelity_history)}
    short = fidelity_history[-sw:]
    long_ = fidelity_history[-lw:]
    m_s = sum(short) / len(short)
    m_l = sum(long_) / len(long_)
    delta = abs(m_s - m_l)
    return {
        "drift_detected": delta > eps,
        "delta": round(delta, 4),
        "mean_short": round(m_s, 4),
        "mean_long": round(m_l, 4),
        "eps": eps,
        "n_points": len(fidelity_history),
    }


# ─────────────────────────────────────────────────────────────────────
# Layer 4 — Expression (behavior_context + narratives)
# ─────────────────────────────────────────────────────────────────────
def build_narrative(ctx: Dict) -> str:
    """Narrative V1 : 1 phrase lisible CEO (pattern multidevise enrichi)."""
    leadership = ctx.get("leadership", {})
    regime = ctx.get("regime", {})
    fid = ctx.get("fidelity_composite", {})
    leader = leadership.get("leader")
    if not leader:
        return "Données insuffisantes pour lire le comportement des devises."
    parts = [f"{leader} mène ({leadership.get('leader_strength', '?')})"]
    if leadership.get("rotation_detected"):
        parts.append(f"rotation depuis {leadership.get('leader_before', '?')}")
    regime_name = regime.get("regime", "NEUTRAL")
    parts.append(f"régime {regime_name}")
    parts.append(f"session {regime.get('session', '?')}")
    fid_r = fid.get("reliable", False)
    # Fidélité extrême (signal aux queues) si disponible
    fx = ctx.get("fidelity_extreme", {})
    if fx.get("best_currency") and fx.get("extreme_reliable"):
        parts.append(f"extrême {fx['best_currency']} WR {fx.get('best_wr_pct', '?')}%")
    parts.append(f"fidélité {'OK' if fid_r else '⚠️ DÉGRADÉE'} "
                 f"({fid.get('composite', 0.0):.2f})")
    return " · ".join(parts) + "."


def build_causal_narrative(ctx: Dict) -> str:
    """Narrative V2 : récit causal H4→H1→M30 (moteur récit appliqué)."""
    ll = ctx.get("lead_lag", {})
    chain = {
        "SLOW_LEADS": "H4 précède H1/M30 — le mouvement naît sur le grand TF",
        "FAST_LEADS": "M30 précède H4 — le mouvement naît sur le court TF",
        "SYNCHRONOUS": "les TF bougent ensemble — pas de chaîne causale nette",
        "UNKNOWN": "causalité non lisible — données insuffisantes",
    }
    return chain.get(ll.get("lead_lag", "UNKNOWN"), "causalité inconnue")


def build_behavior_context(series_m30: CurrencySeries,
                           series_h1: CurrencySeries,
                           series_h4: Optional[CurrencySeries] = None,
                           session: Optional[str] = None) -> Dict:
    """API complète : behavior_context global (Layer 0→4).

    Calcule la compréhension complète du comportement des devises pour
    une (paire, TF) sur la DB réelle. Le champ `fidelity_composite`
    est LE garde-fou : si reliable=False, le contexte est flaggé
    `degraded` et ne doit pas alimenter le gate de risque (R10).
    """
    cfg = get_config()
    session = session or (session_of(_parse_ts(series_m30.timestamps[-1]))
                          if series_m30.timestamps else "UNKNOWN")
    states = classify_currency_states(series_m30)
    coalitions = detect_coalitions(series_m30)
    leadership = compute_leadership(series_m30)
    regime = classify_regime(series_m30, session=session)
    lead_lag = (compute_lead_lag(series_h4, series_m30)
                if series_h4 is not None else
                {"lead_lag": "UNKNOWN", "n_currencies_leads": 0, "detail": []})
    fidelity_m30 = compute_fidelity(series_m30)
    fidelity_h1 = compute_fidelity(series_h1) if len(series_h1) else {}
    fid_comp = compute_fidelity_composite(fidelity_m30, fidelity_h1)
    # Fidélité extrême (découverte Phase 32) : le signal vit aux queues
    fidelity_extreme = compute_fidelity_extreme(series_m30)
    ctx = {
        "generated_at": _now_iso(),
        "pair": series_m30.pair,
        "timeframes": [series_m30.timeframe, series_h1.timeframe],
        "session": session,
        "per_currency": states,
        "coalitions": coalitions,
        "leadership": leadership,
        "regime": regime,
        "lead_lag": lead_lag,
        "fidelity": {
            "M30": fidelity_m30, "H1": fidelity_h1,
        },
        "fidelity_composite": fid_comp,
        "fidelity_extreme": fidelity_extreme,
        "narrative": "",
        "causal_narrative": "",
    }
    ctx["narrative"] = build_narrative(ctx)
    ctx["causal_narrative"] = build_causal_narrative(ctx)
    # Degradé si les DEUX lectures sont infiables (garde-fou R10)
    ctx["degraded"] = not fid_comp["reliable"] and not fidelity_extreme["extreme_reliable"]
    if ctx["degraded"]:
        ctx["warning"] = ("fidelity_below_threshold — contexte exclu du gate "
                          "de risque (R10) jusqu'à recalibrage")
    return ctx
