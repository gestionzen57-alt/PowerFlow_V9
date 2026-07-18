"""DecisionLogger — couche Décision (Phase 9) PowerFlow V9.

Chaîne cognitive étendue :
    ... → Exploitabilité → Principes → Signal → [DÉCISION]

Persiste le contexte complet d'une décision (signal + scène +
comportement + fenêtre + exploitabilité + régime + principes) pour
permettre un replay intégral — aucune logique d'exécution d'ordre.
`action` est une recommandation qualitative, jamais un ordre : observer
/ surveiller / preparer_entree / aucune_action.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import time
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, SCHEMA_VERSION
from core.v9.db_schema import get_connection
from core.v9.decision_db import DECISIONS_COLUMNS, init_decision_db

ACTIONS = {"observer", "surveiller", "preparer_entree", "aucune_action"}

logger = logging.getLogger("v9.decision_logger")

# ── Brief O3 (2026-07-12) — Branching HITL confiance 40-65 ─────────
# ARBITRAGE ACTÉ : ce branchement est INFORMATIF. Il ne déroge PAS au seuil
# bloquant RiskManager.CONFIANCE_MIN=70 ni au plafond Arbiter <2 principes
# (74) — la notification sert la lecture humaine et la calibration, jamais
# l'exécution. Toute dérogation future = décision structurante séparée,
# tracée AVANT implémentation (cf DECISIONS_LOG §2026-07-12 Brief O3).
HITL_BRANCHING_ENABLED_ENV = "V9_HITL_BRANCHING_ENABLED"
HITL_CONF_HIGH = 80   # > 80 : comportement inchangé — CEO 2026-07-13 mode silencieux (moins notifs)
HITL_CONF_LOW = 40    # < 40 : marquage low_confidence_block, pas de Telegram
HITL_TELEGRAM_RATE_LIMIT_SECONDS = 300  # 1 notification / 5 min / (symbol x TF)
HITL_TELEGRAM_TIMEOUT_SECONDS = 5  # court — jamais bloquant pour le pipeline

# État du rate-limiter — PERSISTANT sur disque (fix 2026-07-18).
# Anciennement process-global (_telegram_rate_state en mémoire) : comme
# DecisionLogger est recréé à chaque run_chain() (cf. orchestrator.py:211),
# l'état mémoire mourait entre deux décisions → rate-limit jamais appliqué
# → spam de notifications « décision peu fiable » à chaque snapshot.
# Désormais l'état est sérialisé dans logs/.hitl_telegram_ratelimit.json
# (clé -> {last_sent_epoch, suppressed}) et partagé entre tous les process.
# On utilise time.time() (epoch) et non time.monotonic() : monotonic() ne
# fait sens que dans un process donné et ne peut pas être persisté.
_HITL_RATE_LIMIT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "logs" / ".hitl_telegram_ratelimit.json"
)
_telegram_rate_state: dict[str, dict[str, float | int]] = {}


def _hitl_rate_state_load() -> dict[str, dict[str, float | int]]:
    """Charge l'état du rate-limiter depuis le disque (best-effort)."""
    global _telegram_rate_state
    try:
        if _HITL_RATE_LIMIT_PATH.exists():
            data = json.loads(_HITL_RATE_LIMIT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _telegram_rate_state = data
    except Exception:
        pass
    return _telegram_rate_state


def _hitl_rate_state_save() -> None:
    """Persiste l'état du rate-limiter sur disque (best-effort)."""
    try:
        _HITL_RATE_LIMIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HITL_RATE_LIMIT_PATH.write_text(
            json.dumps(_telegram_rate_state, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _hitl_branching_enabled() -> bool:
    """Kill switch V9_HITL_BRANCHING_ENABLED (défaut '1' = ON)."""
    return os.environ.get(HITL_BRANCHING_ENABLED_ENV, "1") != "0"


def _hitl_rate_limit_check(key: str) -> tuple[bool, int]:
    """Rate-limit 1 notification / 5 min / clé (symbol|timeframe).

    État PERSISTANT sur disque (logs/.hitl_telegram_ratelimit.json) — partagé
    entre tous les process (fix 2026-07-18 : DecisionLogger recréé à chaque
    run_chain, l'ancien état mémoire mourait → spam de notifications).

    Horloge : on mesure l'écart avec time.monotonic() AU SEIN d'un process
    (précis, résistant aux sauts d'horloge), mais on persiste aussi un
    wall_epoch (time.time()) + le pid. Au reload, si le pid ne correspond
    pas (process différent), on se rabat sur le wall_epoch — monotonic()
    n'étant pas comparable entre process.

    Retourne (doit_envoyer, nb_supprimees_depuis_le_dernier_envoi).
    Compteur agrégé : les appels supprimés incrémentent un compteur qui
    est renvoyé (puis remis à 0) au prochain envoi effectif — permet
    d'afficher "... +N similaires supprimées" dans le message suivant.
    """
    _hitl_rate_state_load()
    now_mono = time.monotonic()
    now_wall = time.time()
    state = _telegram_rate_state.get(key)
    if state is None:
        _telegram_rate_state[key] = {
            "last_sent": now_mono,
            "wall_epoch": now_wall,
            "pid": os.getpid(),
            "suppressed": 0,
        }
        _hitl_rate_state_save()
        return True, 0
    # Même process -> monotonic; sinon -> wall_epoch (inter-process).
    if state.get("pid") == os.getpid():
        elapsed = now_mono - float(state["last_sent"])
    else:
        elapsed = now_wall - float(state.get("wall_epoch", now_wall))
    if elapsed >= HITL_TELEGRAM_RATE_LIMIT_SECONDS:
        suppressed = int(state["suppressed"])
        _telegram_rate_state[key] = {
            "last_sent": now_mono,
            "wall_epoch": now_wall,
            "pid": os.getpid(),
            "suppressed": 0,
        }
        _hitl_rate_state_save()
        return True, suppressed
    state["suppressed"] = int(state["suppressed"]) + 1
    _telegram_rate_state[key] = state
    _hitl_rate_state_save()
    return False, 0


def _load_telegram_config_safe() -> dict[str, str] | None:
    """Charge config/telegram.json sans jamais lever ni sys.exit (best-effort).

    Ne réutilise PAS v9_telegram_notifier.load_telegram_config() car cette
    dernière fait sys.exit(1) si absent/invalide — inacceptable dans un
    hook live non-bloquant (règle 6)."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "telegram.json"
    try:
        if not config_path.exists():
            return None
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        token = str(cfg.get("BOT_TOKEN", "")).strip()
        chat_id = str(cfg.get("CHAT_ID", "")).strip()
        if not token or not chat_id or token == "TON_TOKEN_ICI":
            return None
        return {"token": token, "chat_id": chat_id}
    except Exception:
        return None


def _notify_low_confidence_telegram(
    symbol: str, timeframe: str, direction: str, confiance: int, principes: list[str],
) -> None:
    """Notification Telegram best-effort pour confiance 40-65 (INFORMATIF).

    JAMAIS bloquant : timeout court, try/except large, aucune exception ne
    remonte (règle 6). Rate-limité 1/5min/(symbol x TF)."""
    key = f"{symbol}|{timeframe}"
    should_send, suppressed = _hitl_rate_limit_check(key)
    if not should_send:
        return
    try:
        cfg = _load_telegram_config_safe()
        if cfg is None:
            return
        from scripts.v9_telegram_notifier import send_telegram  # noqa: PLC0415

        principes_str = ", ".join(principes) if principes else "aucun"
        text = (
            f"⚠️ V9 décision peu fiable — {symbol} {timeframe} {direction} "
            f"conf={confiance} principes={principes_str} — informatif "
            f"(bloquée par RiskManager si <70)"
        )
        if suppressed:
            text += f"\n… +{suppressed} similaires supprimées"
        send_telegram(text, cfg, timeout=HITL_TELEGRAM_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("HITL branching : échec notification Telegram (non-bloquant)")

# ── Compression zlib pour contexte_complet_json ────────────────
# P0 DB optimisation 2026-07-08 : le JSON de contexte complet pèse
# ~34 Ko en moyenne (p50=27 Ko, p99=139 Ko) et représente 55% de la DB
# (~2 Go sur 3.7 Go). La compression zlib niveau 6 divise par ~20 la
# taille stockée (130 Ko → 6.7 Ko), au prix d'une décompression à la
# lecture (négligeable car DecisionLogger lit rarement les décisions
# passées).
# Format : bytes zlib (stocké dans colonne TEXT, SQLite accepte les
# bytes). Rétrocompatibilité : load_contexte_complet() détecte
# automatiquement bytes / str / json brut.
_COMPRESS_LEVEL = 6


def _compress_json(obj: Any) -> bytes:
    """Compresse un objet JSON avec zlib et retourne des bytes."""
    raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    return zlib.compress(raw, level=_COMPRESS_LEVEL)


def _decompress_json(data: bytes | str) -> Any:
    """Décompresse des bytes zlib vers l'objet JSON original."""
    if isinstance(data, str):
        compressed = data.encode("latin-1")
    else:
        compressed = data
    raw = zlib.decompress(compressed)
    return json.loads(raw.decode("utf-8"))


def load_contexte_complet(data: bytes | str | None) -> Any:
    """Charge un contexte_complet_json depuis la DB, gérant les formats.

    Format actuel (P0, 2026-07-08) : bytes zlib
    Format historique (avant P0)    : json brut (str commençant par '{')

    Rétrocompatibilité totale : les décisions existantes (non compressées)
    restent lisibles après la migration.
    """
    if not data:
        return None
    # Format bytes zlib
    if isinstance(data, bytes):
        try:
            return _decompress_json(data)
        except (ValueError, zlib.error):
            pass
    # Format str : JSON brut ou base64 (transitionnel)
    if isinstance(data, str):
        # JSON brut
        if data.startswith("{"):
            try:
                return json.loads(data)
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
        # Base64 (transitionnel, rollbacké)
        try:
            return _decompress_json(data)
        except (ValueError, zlib.error, base64.binascii.Error):
            pass
    return None


class DecisionLoggerError(ValueError):
    """Erreur de journalisation de décision (signal introuvable)."""


class DecisionLogger:
    """Assemble et persiste une décision (contexte complet, replayable)."""

    def __init__(self, db_path: Path | str | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_decision_db(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_signal(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row:
        """Charge le signal « porteur de décision » pour un snapshot.

        Tri par pertinence décisionnelle, pas par simple timestamp :
        un signal directionnel+exploitable est intrinsèquement plus
        informatif qu'un signal non-exploitable (raison_absence posé).
        On priorise donc les signaux directionnels, puis on prend le
        plus récent (ORDER BY id DESC) en cas d'ex-aequo.

        Bug fixé 2026-07-06 (pre-correction : ORDER BY id DESC LIMIT 1
        prenait le DERNIER signal inséré pour un snapshot, même si
        non-directionnel ; un signal directionnel généré APRÈS une
        première décision figée restait invisible pour DecisionLogger).
        """
        row = conn.execute(
            """
            SELECT * FROM signals
            WHERE snapshot_id = ?
            ORDER BY
                (direction IS NOT NULL AND direction != 'neutre'
                 AND exploitability_statut != 'non_exploitable') DESC,
                id DESC
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise DecisionLoggerError(f"aucun signal journalise pour snapshot {snapshot_id!r}")
        return row

    def _load_chain(self, conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
        scene = conn.execute(
            "SELECT * FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        behavior = window = exploitability = None
        if scene is not None:
            behavior = conn.execute(
                "SELECT * FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
                (scene["scene_id"],),
            ).fetchone()
        if behavior is not None:
            window = conn.execute(
                "SELECT * FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
                (behavior["behavior_id"],),
            ).fetchone()
        if window is not None:
            exploitability = conn.execute(
                "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1",
                (window["window_id"],),
            ).fetchone()
        return {
            "scene": dict(scene) if scene else None,
            "behavior": dict(behavior) if behavior else None,
            "window": dict(window) if window else None,
            "exploitability": dict(exploitability) if exploitability else None,
        }

    def _load_regime(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM regime_snapshots WHERE forces_snapshot_ref = ?", (snapshot_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_principles(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        # Doctrine realign Phase 9.8 (C4) — volontairement non filtré sur
        # v9_status ni triggered : contexte_complet_json doit permettre un
        # replay intégral (docstring module), donc la trace inclut déjà
        # tous les descripteurs évalués pour ce snapshot (triggered ou
        # non, ACTIVE ou SHADOW), pas seulement ceux qui ont déclenché.
        # Vérifié C4 : ce comportement pré-existe C1 et n'est pas affecté
        # par le passage de PRINCIPLE_ACTIVE_IDS de 10 à 27 (aucune ligne
        # ni aucun champ supplémentaire n'apparaît dans cette requête —
        # seule la colonne v9_status de certaines lignes déjà présentes
        # passe de SHADOW à ACTIVE).
        rows = conn.execute(
            "SELECT * FROM principle_evaluations WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _determine_action(self, signal: sqlite3.Row, exploitability: dict | None) -> str:
        # Brief O4 CEO 2026-07-13 — defense-in-depth UNIQUEMENT quand on a
        # une preuve positive de session blacklistée (signal_generator
        # doit avoir populé exit_strategy_recommended=None pour NY/after).
        # Si la colonne est NULL mais qu'on ne peut pas rattacher à NY/after
        # (DB legacy / test fixture sans _recommend_dynamic_), on laisse
        # passer le comportement baseline (cascade implicite R25').
        #
        # Compat sqlite3.Row : `signal.get()` n'existe pas, on teste la
        # présence de la clé via `signal.keys()`.
        try:
            signal_keys = signal.keys() if hasattr(signal, "keys") else None
        except Exception:
            signal_keys = None
        has_col = signal_keys is None or (
            "exit_strategy_recommended" in signal_keys if signal_keys else False
        )

        if has_col:
            exit_strat = signal["exit_strategy_recommended"]
            # Defense-in-depth : si explicitement None (= session blacklistée
            # O4 par signal_generator) ET direction directionnelle, bloque.
            # Si "DYNAMIC" (session tradable), laisse passer.
            if exit_strat is None and signal["direction"] not in (None, "neutre"):
                snapshot_id = (
                    signal["snapshot_id"]
                    if signal_keys and "snapshot_id" in signal_keys
                    else "unknown"
                )
                logger.info(
                    "decision_logger.o4_blacklist: snapshot %s marqué aucune_action "
                    "(session session_blacklisted_brief_o4)",
                    snapshot_id,
                )
                return "aucune_action"

        if signal["raison_absence"] is not None or signal["direction"] in (None, "neutre"):
            return "aucune_action"
        statut = exploitability["statut"] if exploitability else None
        if statut == "exploitable" and signal["horizon"] == "court_terme":
            return "preparer_entree"
        if statut in ("exploitable", "watchlist"):
            return "surveiller"
        return "observer"

    def log(self, snapshot_id: str) -> dict[str, Any]:
        """Assemble et persiste la décision pour un snapshot (le signal
        associé doit déjà avoir été journalisé par SignalGenerator)."""
        conn = self._connect()
        try:
            signal = self._load_signal(conn, snapshot_id)
            chain = self._load_chain(conn, snapshot_id)
            regime = self._load_regime(conn, snapshot_id)
            principles = self._load_principles(conn, snapshot_id)

            action = self._determine_action(signal, chain["exploitability"])
            principes_liste = sorted(set(json.loads(signal["principes_source_json"] or "[]")))

            low_confidence_block = self._apply_hitl_branching(
                direction=signal["direction"],
                confiance=signal["confiance"],
                symbol=signal["symbol"],
                timeframe=signal["timeframe"],
                principes=principes_liste,
            )

            decision = {
                "decision_id": _decision_id_for_snapshot(snapshot_id),
                "schema_version": SCHEMA_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "snapshot_id": snapshot_id,
                "signal_id": signal["signal_id"],
                "action": action,
                "symbol": signal["symbol"],
                "timeframe": signal["timeframe"],
                "currency": signal["currency"],
                "scene_id": chain["scene"]["scene_id"] if chain["scene"] else None,
                "behavior_id": chain["behavior"]["behavior_id"] if chain["behavior"] else None,
                "window_id": chain["window"]["window_id"] if chain["window"] else None,
                "exploitability_id": signal["exploitability_id"],
                "regime_type": signal["regime_type"],
                "direction": signal["direction"],
                "confiance": signal["confiance"],
                "principes": principes_liste,
                "source_type": self.source_type,
                "low_confidence_block": low_confidence_block,
                "contexte_complet": {
                    "signal": dict(signal),
                    "scene": chain["scene"],
                    "behavior": chain["behavior"],
                    "window": chain["window"],
                    "exploitability": chain["exploitability"],
                    "regime": regime,
                    "principle_evaluations": principles,
                },
            }

            self._write_to_db(conn, decision)
            return decision
        finally:
            conn.close()

    def _apply_hitl_branching(
        self,
        direction: str | None,
        confiance: int | None,
        symbol: str,
        timeframe: str,
        principes: list[str],
    ) -> int:
        """Branching HITL confiance (Brief O3). INFORMATIF uniquement — ne
        déroge PAS à RiskManager.CONFIANCE_MIN=70. Retourne
        low_confidence_block (0 ou 1) à persister sur la décision.

        - conf > 65        : inchangé (retourne 0, aucun effet de bord).
        - 40 <= conf <= 65  : notification Telegram best-effort rate-limitée.
        - conf < 40         : marquage low_confidence_block=1 + log dédié,
                               pas de Telegram.
        Ne s'applique qu'aux décisions directionnelles (direction pas
        None/neutre) — sinon retourne 0 sans effet."""
        if not _hitl_branching_enabled():
            return 0
        if direction in (None, "neutre") or confiance is None:
            return 0

        if confiance < HITL_CONF_LOW:
            logger.info(
                "HITL low_confidence_block : %s %s %s conf=%d (<%d) — bloqué, "
                "pas de notification",
                symbol, timeframe, direction, confiance, HITL_CONF_LOW,
            )
            return 1

        if HITL_CONF_LOW <= confiance <= HITL_CONF_HIGH:
            _notify_low_confidence_telegram(symbol, timeframe, direction, confiance, principes)
            return 0

        return 0

    def _write_to_db(self, conn: sqlite3.Connection, decision: dict) -> None:
        """INSERT idempotent par snapshot_id.

        Avant l'INSERT, cherche une décision existante pour le même
        snapshot_id. Si elle existe ET que la nouvelle décision est de
        meilleure qualité décisionnelle, on l'écrase par INSERT OR REPLACE
        sur decision_id (UNIQUE existant, déterministe depuis snapshot_id).
        Sinon (ancienne déjà directionnelle ou qualité équivalente), skip.

        Critère de qualité (du meilleur au moins bon) :
          1. directionnelle + court_terme  (action ∈ {preparer_entree,
             surveiller})
          2. directionnelle                (action=observer)
          3. non_directionnelle            (action=aucune_action)

        Bug fixé 2026-07-06 : avant le fix, decision_id était
        timestamp+uuid (changement à chaque appel), donc INSERT OR REPLACE
        créait une nouvelle rangée à chaque rejeu (3697 → 3960 sur 3
        snapshots rejoués). Maintenant, decision_id est stable par
        snapshot_id (cf. _generate_decision_id), et le pré-check qualité
        évite d'écraser une bonne décision par une mauvaise.
        """
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **decision,
            "principes_json": json.dumps(decision["principes"], ensure_ascii=False),
            "contexte_complet_json": _compress_json(decision["contexte_complet"]),
            "created_at": now,
        }
        # Pré-check qualité : si une décision existe déjà et est meilleure
        # ou égale, on skip l'écriture pour préserver l'idempotence.
        existing_row = conn.execute(
            "SELECT direction, action, confiance FROM decisions WHERE snapshot_id = ?",
            (decision["snapshot_id"],),
        ).fetchone()
        if existing_row is not None:
            existing_quality = _action_quality(
                existing_row["direction"], existing_row["action"], existing_row["confiance"]
            )
            new_quality = _action_quality(
                decision["direction"], decision["action"], decision["confiance"]
            )
            # Nouvelle qualité strictement supérieure → on écrase.
            # Sinon → on garde l'ancien (skip silencieux).
            if new_quality <= existing_quality:
                return

        columns = ", ".join(DECISIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in DECISIONS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
            [values[c] for c in DECISIONS_COLUMNS],
        )
        conn.commit()


def _action_quality(direction: str | None, action: str, confiance: int | None) -> int:
    """Score entier de qualité décisionnelle.

    Permet l'idempotence ordonnée : si une décision 'aucune_action'
    existe déjà pour un snapshot, un rejeu qui produit aussi 'aucune_action'
    sera ignoré. Un rejeu qui produit une décision directionnelle
    écrasera l'ancienne 'aucune_action' (cas emblématique bug session 2).

    Échelle (du moins bon au meilleur) :
      0 → aucune_action (non directionnelle)
      1 → observer       (directionnelle mais passive)
      2 → surveiller     (directionnelle + watchlist)
      3 → preparer_entree (directionnelle + exploitable + court terme)
    """
    if direction is None or direction == "neutre":
        return 0
    if action == "preparer_entree":
        return 3
    if action == "surveiller":
        return 2
    if action == "observer":
        return 1
    return 0


def _decision_id_for_snapshot(snapshot_id: str) -> str:
    """decision_id déterministe par snapshot_id.

    Avant 2026-07-06 : timestamp+uuid → unique par appel → INSERT OR
    REPLACE créait une nouvelle rangée à chaque rejeu (3697 → 3960 sur
    3 snapshots rejoués).

    Maintenant : hash court de snapshot_id (12 chars hex, suffisant pour
    l'unicité au sein d'une session). 2 appels .log() sur le même
    snapshot produisent le même decision_id → INSERT OR REPLACE écrase
    vraiment.

    Idempotence par snapshot_id garantie côté DB (UNIQUE constraint
    existante sur decision_id).
    """
    short = uuid.uuid5(uuid.NAMESPACE_URL, snapshot_id).hex[:12]
    return f"dec_{short}"


def _generate_decision_id(symbol: str, timeframe: str) -> str:
    """Compatibilité historique — ne plus utiliser en V9.

    Conservée pour ne pas casser d'imports legacy. Retourne désormais
    un decision_id basé sur (symbol, timeframe) mais ce n'est PAS
    idempotent au niveau snapshot_id. Préférez _decision_id_for_snapshot.
    """
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"dec_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{uuid.uuid4().hex[:6]}"
