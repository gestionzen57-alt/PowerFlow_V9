"""V10 MT5 Bridge — Phase 7 Edge Fund (additif R2 pur).

Bridges PowerFlow V10 avec MetaTrader 5 (MT5) via l'API Python officielle.

Doctrine :
  R2 additif pur (zero import core/v9/) — autorisé seulement core/v10/.
  R6 fail-open (MT5 absent / non loggué → fallback DB).
  R9 auditable (chacune de nos fonctions trace son état MT5 vs DB).
  R10 zéro capital (compute only — pas d'ordre transmis).

API exposée :
  - MT5BridgeState        : dataclass état du bridge (R9)
  - is_mt5_available()    : détecte MT5 + auto-detect profil AppData
  - initialize()          : mt5.initialize() depuis profil AppData détecté
  - shutdown()            : mt5.shutdown() safe (no-op si pas initialisé)
  - get_rates(symbol, tf, n)   : OHLCV → pd.DataFrame
  - get_ticks(symbol, from_dt, to_dt) : ticks ms → pd.DataFrame
  - get_spread_series(symbol, tf, n) : spread réel/barre
  - get_ohlcv_with_meta(symbol, tf, n) : OHLCV + spread + real_volume + tick_volume

Toutes les fonctions retournent un MT5BridgeState.dataframe (None si fail-open).
Le caller est responsable du fallback DB si dataframe est None.

Format timeframe accepte :
  - "M1","M5","M15","M30","H1","H4","D1","W1","MN" (V10 natif)
  - mt5.TIMEFRAME_M1 ... mt5.TIMEFRAME_MN1

Mapping : M1->M1, M5->M5, M15->M15, M30->M30, H1->H1, H4->H4, D1->D1,
          W1->W1, MN->MN1 (mensuel).
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Lazy MT5 import (R6 fail-open)
# ─────────────────────────────────────────────────────────────────────
_MT5 = None
_MT5_IMPORT_ERROR = None
try:
    import MetaTrader5 as _MT5  # type: ignore
except Exception as _exc:  # pragma: no cover
    _MT5 = None
    _MT5_IMPORT_ERROR = str(_exc)
    log.debug(f"v10_mt5_bridge: import MetaTrader5 impossible ({_exc}); R6 fallback DB")


# ─────────────────────────────────────────────────────────────────────
# Mapping Timeframe V10 → MT5
# ─────────────────────────────────────────────────────────────────────
TF_V10_TO_MT5 = {
    "M1": (_MT5.TIMEFRAME_M1 if _MT5 else None),
    "M5": (_MT5.TIMEFRAME_M5 if _MT5 else None),
    "M15": (_MT5.TIMEFRAME_M15 if _MT5 else None),
    "M30": (_MT5.TIMEFRAME_M30 if _MT5 else None),
    "H1": (_MT5.TIMEFRAME_H1 if _MT5 else None),
    "H4": (_MT5.TIMEFRAME_H4 if _MT5 else None),
    "D1": (_MT5.TIMEFRAME_D1 if _MT5 else None),
    "W1": (_MT5.TIMEFRAME_W1 if _MT5 else None),
    "MN": (_MT5.TIMEFRAME_MN1 if _MT5 else None),
}

MT5_TERMINAL_PATH_HINT = r"C:\Users\Administrateur\AppData\Roaming\MetaQuotes\Terminal"

# Chemins alternatifs où chercher terminal64.exe (installations standard)
MT5_TERMINAL_EXE_CANDIDATES = [
    r"C:\Program Files\Tickmill Europe MT5 Terminal\terminal64.exe",
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\Tickmill MT5 Terminal\terminal64.exe",
]


# ─────────────────────────────────────────────────────────────────────
# Dataclass état (R9)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class MT5BridgeState:
    """État du bridge MT5 — sérialisable pour audit R9."""
    mt5_initialized: bool = False
    mt5_available: bool = False           # MT5 importable + profil trouvé
    mt5_import_error: Optional[str] = None
    terminal_path: Optional[str] = None
    account_login: Optional[int] = None
    account_server: Optional[str] = None
    n_rate_calls: int = 0
    n_tick_calls: int = 0
    n_spread_calls: int = 0
    fallback_db_calls: int = 0
    seed: Optional[int] = None

    def as_dict(self) -> dict:
        return {
            "mt5_initialized": self.mt5_initialized,
            "mt5_available": self.mt5_available,
            "mt5_import_error": self.mt5_import_error,
            "terminal_path": self.terminal_path,
            "account_login": self.account_login,
            "account_server": self.account_server,
            "n_rate_calls": self.n_rate_calls,
            "n_tick_calls": self.n_tick_calls,
            "n_spread_calls": self.n_spread_calls,
            "fallback_db_calls": self.fallback_db_calls,
            "seed": self.seed,
        }


# Global state (singleton pattern, modifiable pour tests)
_BRIDGE_STATE = MT5BridgeState(
    mt5_available=_MT5 is not None,
    mt5_import_error=_MT5_IMPORT_ERROR,
)


def get_bridge_state() -> MT5BridgeState:
    """Récupère l'état courant du bridge."""
    return _BRIDGE_STATE


def _reset_bridge_state_for_tests() -> None:
    """Helper test — ne pas utiliser en prod."""
    global _BRIDGE_STATE
    _BRIDGE_STATE = MT5BridgeState(
        mt5_available=_MT5 is not None,
        mt5_import_error=_MT5_IMPORT_ERROR,
    )


# ─────────────────────────────────────────────────────────────────────
# Détection profil MT5
# ─────────────────────────────────────────────────────────────────────
def _detect_mt5_terminal() -> Optional[str]:
    """Auto-détecte le chemin du terminal MT5 (chemin du terminal64.exe).

    Fix Phase 33 : mt5.initialize(path=...) exige le chemin COMPLET de
    l'exécutable (erreur -10003 sinon : "Process create failed").
    Recherche :
      1. chemins candidats connus (MT5_TERMINAL_EXE_CANDIDATES)
      2. terminal64.exe dans les profils AppData MetaQuotes
      3. Program Files (glob **/terminal64.exe limité en profondeur)

    Returns le chemin complet du terminal64.exe, ou None.
    """
    # 1. Chemins candidats explicites (installations standard)
    for cand in MT5_TERMINAL_EXE_CANDIDATES:
        if Path(cand).exists():
            return cand
    # 2. Profils AppData MetaQuotes (profil avec terminal64.exe)
    base = Path(MT5_TERMINAL_PATH_HINT)
    if base.exists():
        candidates = list(base.glob("**/terminal64.exe"))
        if candidates:
            candidates.sort(key=lambda p: -len(str(p.parent.name)))
            return str(candidates[0])
    # 3. Program Files : recherche globale du terminal64.exe
    for pf in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        if pf.exists():
            try:
                hits = list(pf.glob("**/terminal64.exe"))
            except OSError:
                hits = []
            if hits:
                return str(hits[0])
    return None


def _v10_tf_to_mt5(tf: str) -> Optional[int]:
    """Convertit un timeframe V10 (M1..D1..MN) en mt5.TIMEFRAME_*."""
    return TF_V10_TO_MT5.get(tf.upper())


def is_mt5_available() -> bool:
    """True si MT5 importable ET profil détectable."""
    if _MT5 is None:
        return False
    return _detect_mt5_terminal() is not None


# ─────────────────────────────────────────────────────────────────────
# Initialize / shutdown
# ─────────────────────────────────────────────────────────────────────
def initialize(*, terminal_path: Optional[str] = None) -> bool:
    """Initialise MT5 avec auto-détection du terminal (R9 audit).

    Returns True si initialisé, False sinon (R6 fail-open).
    """
    state = get_bridge_state()
    if _MT5 is None:
        log.debug("v10_mt5_bridge.initialize: MetaTrader5 non importable.")
        return False

    path = terminal_path or _detect_mt5_terminal()
    if path:
        state.terminal_path = path
        try:
            ok = _MT5.initialize(path=path)
        except Exception as e:  # pragma: no cover
            ok = False
            log.debug(f"v10_mt5_bridge.initialize exception: {e}")
        if not ok:
            # Fallback R6 : init sans path (terminal par défaut du package).
            # Certains builds MetaTrader5 ignorent un path qui ne pointe
            # pas sur l'exe exact — l'init sans path retombe sur le bon.
            try:
                ok = _MT5.initialize()
            except Exception as e:  # pragma: no cover
                ok = False
                log.debug(f"v10_mt5_bridge.initialize fallback exception: {e}")
            if ok:
                try:
                    info = _MT5.terminal_info()
                    if info is not None and hasattr(info, "path"):
                        state.terminal_path = str(info.path)
                except Exception:
                    pass
    else:
        try:
            ok = _MT5.initialize()
        except Exception as e:  # pragma: no cover
            ok = False
            log.debug(f"v10_mt5_bridge.initialize exception: {e}")
        if ok:
            try:
                info = _MT5.terminal_info()
                if info is not None and hasattr(info, "path"):
                    state.terminal_path = str(info.path)
            except Exception:
                pass

    state.mt5_initialized = bool(ok)
    state.mt5_available = bool(ok)
    if ok:
        try:
            acc = _MT5.account_info()
            if acc is not None:
                state.account_login = int(getattr(acc, "login", 0)) or None
                state.account_server = str(getattr(acc, "server", "") or "") or None
        except Exception:
            pass
    return state.mt5_initialized


def shutdown() -> None:
    """Shutdown MT5 safe (no-op si pas initialisé)."""
    state = get_bridge_state()
    if _MT5 is None:
        return
    try:
        if state.mt5_initialized:
            _MT5.shutdown()
            state.mt5_initialized = False
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# get_rates / get_ticks / get_spread_series
# ─────────────────────────────────────────────────────────────────────
def get_rates(symbol: str, tf: str, n: int = 200) -> Optional["pd.DataFrame"]:
    """Lit N dernières barres OHLCV depuis MT5.

    Returns pd.DataFrame avec colonnes : time, open, high, low, close,
    tick_volume, spread, real_volume. Indexé sur time (datetime64).

    R6 fail-open : retourne None si MT5 indisponible.
    """
    state = get_bridge_state()
    if _MT5 is None:
        return None
    if not state.mt5_initialized and not initialize():
        return None

    # Lazy import pandas
    try:
        import pandas as pd
    except Exception:  # pragma: no cover
        return None

    mt5_tf = _v10_tf_to_mt5(tf)
    if mt5_tf is None:
        log.debug(f"v10_mt5_bridge.get_rates: timeframe V10 inconnu {tf}")
        return None

    try:
        rates = _MT5.copy_rates_from_pos(symbol, mt5_tf, 0, int(n))
    except Exception as e:  # pragma: no cover
        log.debug(f"v10_mt5_bridge.get_rates exception: {e}")
        return None
    if rates is None or len(rates) == 0:
        return None

    state.n_rate_calls += 1
    df = pd.DataFrame(rates)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def get_ticks(
    symbol: str,
    from_dt: datetime,
    to_dt: Optional[datetime] = None,
) -> Optional["pd.DataFrame"]:
    """Lit les vrais ticks ms depuis MT5 entre [from_dt, to_dt].

    Si to_dt est None → from_dt + 1 jour.
    """
    state = get_bridge_state()
    if _MT5 is None:
        return None
    if not state.mt5_initialized and not initialize():
        return None

    try:
        import pandas as pd
    except Exception:  # pragma: no cover
        return None

    if to_dt is None:
        to_dt = from_dt + timedelta(days=1)

    try:
        ticks = _MT5.copy_ticks_range(
            symbol,
            int(from_dt.timestamp()),
            int(to_dt.timestamp()),
            _MT5.COPY_TICKS_ALL,  # type: ignore
        ) if _MT5 else None
    except Exception as e:  # pragma: no cover
        log.debug(f"v10_mt5_bridge.get_ticks exception: {e}")
        return None
    if ticks is None or len(ticks) == 0:
        return None

    state.n_tick_calls += 1
    df = pd.DataFrame(ticks)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    if "time_msc" in df.columns:
        df["time_msc"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    return df


def get_spread_series(symbol: str, tf: str, n: int = 100) -> Optional["pd.Series"]:
    """Lit la série des spreads réels (points) par barre.

    R6 fail-open : retourne None si MT5 indisponible.
    """
    state = get_bridge_state()
    df = get_rates(symbol, tf, n)
    if df is None or "spread" not in df.columns:
        return None
    state.n_spread_calls += 1
    try:
        return df["spread"]
    except Exception:
        return None


def get_ohlcv_with_meta(
    symbol: str, tf: str, n: int = 200,
) -> Optional["pd.DataFrame"]:
    """get_rates enrichi — alias sémantique identique.

    V10 utilise directement get_rates ; cette fonction est conservée pour
    symétrie API + auditabilité R9.
    """
    return get_rates(symbol, tf, n)


# ─────────────────────────────────────────────────────────────────────
# Fallback DB (R6 — pas de régression)
# ─────────────────────────────────────────────────────────────────────
def read_ohlcv_from_db(
    db_path: str,
    symbol: str,
    tf: str,
    limit: int = 200,
) -> List[dict]:
    """Fallback DB (R6 fail-open) : lit barres depuis forces_snapshots."""
    state = get_bridge_state()
    out: List[dict] = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except (sqlite3.OperationalError, OSError):
        return []
    try:
        cur = con.cursor()
        try:
            rows = cur.execute(
                """
                SELECT bar_time, open, high, low, close, tick_volume, spread_points
                FROM forces_snapshots
                WHERE symbol=? AND timeframe=? AND is_closed_bar=1
                ORDER BY bar_time DESC LIMIT ?
                """,
                (symbol, tf, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        con.close()

    state.fallback_db_calls += 1
    for bar_time, o, h, l, c, vol, spread in reversed(rows):
        ts = (
            datetime.fromtimestamp(bar_time, tz=timezone.utc).isoformat()
            if bar_time else ""
        )
        out.append({
            "timestamp": ts,
            "open": o, "high": h, "low": l, "close": c,
            "tick_volume": float(vol or 0.0),
            "spread": float(spread or 0.0),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# API haut-niveau : barres avec préférence MT5 et fallback DB
# ─────────────────────────────────────────────────────────────────────
def get_bars_with_fallback(
    symbol: str,
    tf: str,
    n: int = 200,
    *,
    db_path: Optional[str] = None,
) -> List[dict]:
    """Barres OHLCV avec préférence MT5 → fallback DB.

    R6 fail-open : si MT5 absent / erreur / pas assez de barres → DB.

    Returns une liste de dicts {open, high, low, close, tick_volume, timestamp}
    compatible avec compute_vsa / compute_structure / etc.
    """
    # Tentative MT5
    df = get_rates(symbol, tf, n=n)
    if df is not None and not df.empty:
        # MT5 a renvoyé quelque chose — on convertit au format V10
        out: List[dict] = []
        for _, row in df.iterrows():
            ts = row["time"].isoformat() if hasattr(row["time"], "isoformat") else str(row["time"])
            out.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": float(row.get("tick_volume", 0.0) or 0.0),
                "real_volume": float(row.get("real_volume", 0.0) or 0.0),
                "spread": float(row.get("spread", 0.0) or 0.0),
                "timestamp": ts,
            })
        # R10 : aucun ordre transmis — compute only.
        return out

    # Fallback DB
    if not db_path:
        return []
    return read_ohlcv_from_db(db_path, symbol, tf, limit=n)


__all__ = [
    "MT5BridgeState",
    "is_mt5_available",
    "initialize",
    "shutdown",
    "get_rates",
    "get_ticks",
    "get_spread_series",
    "get_ohlcv_with_meta",
    "read_ohlcv_from_db",
    "get_bars_with_fallback",
    "get_bridge_state",
    "MT5_TERMINAL_PATH_HINT",
    "TF_V10_TO_MT5",
]
