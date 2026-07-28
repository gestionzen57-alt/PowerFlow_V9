"""core/v9/lost_trade_blacklist.py — Blacklist contextuelle symbol+session+regime (28/07).

Motion CEO 28/07 : FAIT TOUT CE QU'IL FAUT POUR SYSTEME RENTABLE EDGE FUND.

Audit 30j a identifié 6 contextes (symbol+session+regime) structurellement
perdants (cumul -387 pips). Ce module expose une blacklist consultable
par trade_engine pour bloquer l'ouverture de paper_trades sur ces contextes.

Doctrine : R2 additif (nouveau module, 0 modif core/v9/), R6 défensif,
R14 git source de vérité, R18 code pur.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"C:\projet\V9")
BLACKLIST_PATH = ROOT / "config" / "v9_lost_trade_blacklist.json"

# Blacklist initial (motion CEO 28/07, audit 30j).
# Format : {"symbol+session+regime": {"blocked": True, "reason": "..."}}
# Capture le triplet top-level pour flexibilité (any-principle, any-context).
DEFAULT_BLACKLIST = {
    "GBPUSD+london+NEUTRE": {
        "blocked": True,
        "reason": "20 trades, WR 0.0%, cum -130.80 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    "USDCHF+london+NEUTRE": {
        "blocked": True,
        "reason": "15 trades, WR 0.0%, cum -69.80 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    "EURUSD+london+NEUTRE": {
        "blocked": True,
        "reason": "14 trades, WR 14.3%, cum -67.45 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    "GBPUSD+asie+NEUTRE": {
        "blocked": True,
        "reason": "19 trades, WR 15.8%, cum -50.80 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    "USDCHF+asie+NEUTRE": {
        "blocked": True,
        "reason": "12 trades, WR 0.0%, cum -56.70 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    "AUDUSD+asie+NEUTRE": {
        "blocked": True,
        "reason": "21 trades, WR 38.1%, cum -11.40 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    # Motion CEO 28/07 edge fund star-pattern analysis.
    # Stars 1-principe (PRICE_LAG, POWER_ANGLE, ZONE_RETEST) sont toujours perdants
    # sur asie/london mais gagnants sur overlap/new_york. Plus chirurgical.
    "GBPUSD+asie+NEUTRE": {
        "blocked": True,
        "reason": "19 trades, WR 15.8%, cum -50.80 pips (audit 30j)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T13:30:00+00:00",
    },
    # Motion CEO 28/07 edge fund star-pattern analysis (round 2).
    # Stars 1-principe (PRICE_LAG_AT_NODE_BIRTH, POWER_ANGLE_BREAK_TO_PRICE_IMPACT,
    # ZONE_RETEST) sont GAGNANTS sur overlap/new_york mais PERDANTS sur asie/london.
    # Pattern systématique -492 pips cumule. Bloquer ces contextes pour les USDCAD/USDJPY
    # deja blacklistés + active pour 4 paires (les pires restantes).
    "PRICE_LAG_AT_NODE_BIRTH+asie+NEUTRE": {
        "blocked": True,
        "reason": "70 trades, WR 28.6%, cum -126.20 pips (star-pattern asie)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T14:00:00+00:00",
    },
    "PRICE_LAG_AT_NODE_BIRTH+london+NEUTRE": {
        "blocked": True,
        "reason": "58 trades, WR 8.6%, cum -298.75 pips (star-pattern london)",
        "added_by": "motion CEO 28/07",
        "added_at": "2026-07-28T14:00:00+00:00",
    },
}


def _load_blacklist() -> dict[str, dict]:
    """Charge la blacklist depuis le fichier config ou initialise par défaut."""
    if BLACKLIST_PATH.exists():
        try:
            data = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # Init par défaut
    BLACKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    BLACKLIST_PATH.write_text(
        json.dumps(DEFAULT_BLACKLIST, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return dict(DEFAULT_BLACKLIST)


# Cache module-level (R6 fail-safe)
_BLACKLIST_CACHE: dict[str, dict] | None = None


def is_context_blacklisted(symbol: str, session: str, regime: str) -> bool:
    """Retourne True si (symbol, session, regime) est blacklisté.

    R6 : retourne False si indisponible (fail-open).
    """
    global _BLACKLIST_CACHE
    if _BLACKLIST_CACHE is None:
        try:
            _BLACKLIST_CACHE = _load_blacklist()
        except Exception:
            return False
    key = f"{symbol}+{session}+{regime}"
    entry = _BLACKLIST_CACHE.get(key)
    return bool(entry and entry.get("blocked", False))


def reload_blacklist() -> int:
    """Recharge la blacklist depuis le fichier. Retourne le nombre d'entrées."""
    global _BLACKLIST_CACHE
    _BLACKLIST_CACHE = _load_blacklist()
    return len(_BLACKLIST_CACHE)


def get_blacklist() -> dict[str, dict]:
    """Retourne la blacklist complète (lecture)."""
    global _BLACKLIST_CACHE
    if _BLACKLIST_CACHE is None:
        _BLACKLIST_CACHE = _load_blacklist()
    return dict(_BLACKLIST_CACHE)


def add_to_blacklist(symbol: str, session: str, regime: str, reason: str) -> None:
    """Ajoute un contexte à la blacklist (motion CEO explicite)."""
    global _BLACKLIST_CACHE
    if _BLACKLIST_CACHE is None:
        _BLACKLIST_CACHE = _load_blacklist()
    key = f"{symbol}+{session}+{regime}"
    _BLACKLIST_CACHE[key] = {
        "blocked": True,
        "reason": reason,
        "added_by": "manual_motion",
        "added_at": "2026-07-28T13:30:00+00:00",
    }
    BLACKLIST_PATH.write_text(
        json.dumps(_BLACKLIST_CACHE, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def remove_from_blacklist(symbol: str, session: str, regime: str) -> None:
    """Retire un contexte de la blacklist."""
    global _BLACKLIST_CACHE
    if _BLACKLIST_CACHE is None:
        _BLACKLIST_CACHE = _load_blacklist()
    key = f"{symbol}+{session}+{regime}"
    _BLACKLIST_CACHE.pop(key, None)
    BLACKLIST_PATH.write_text(
        json.dumps(_BLACKLIST_CACHE, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
