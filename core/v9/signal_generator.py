"""SignalGenerator — couche Décision (Phase 9) PowerFlow V9.

Chaîne cognitive étendue :
    ... → Exploitabilité → Principes → [SIGNAL] → Décision

Agrège les évaluations de principes ACTIVE (jamais SHADOW — même
sémantique que le "shadow gate" V8 : un principe SHADOW est journalisé
et calibré, jamais routé vers un signal) en un signal directionnel pour
le symbole du snapshot. Toutes les évaluations ACTIVE triggered du
snapshot sont journalisées dans `principes_source` (doctrine 2026-07-07,
visibilité multi-devise), mais seules celles sur la devise de BASE (telle
quelle) et de contrepartie/quote (inversée — cf. `_pair_relative_
direction`) votent la direction de la paire ; une devise tierce n'a aucun
mapping directionnel valide vers la paire et est exclue du vote (fix
2026-07-15).

« Absence de signal » est une réponse de première classe (charte
cognitive V9, même principe que « non exploitable »/« refusé » en
couche Exploitabilité) : toujours journalisée avec sa raison, jamais
omise silencieusement.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import (
    DB_PATH,
    REGIMES_INADEQUATS,
    SCHEMA_VERSION,
    SIGNAL_CONFIANCE_HORIZON_COURT,
    SIGNAL_FORCES_FALLBACK_SPREAD_MIN,
)
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import (
    DYNAMIC_PROFILES,
    DYNAMIC_DEFAULT,
    infer_session_from_hour,
    is_session_tradable,
)
from core.v9.signal_db import SIGNALS_COLUMNS, init_signal_db
from core.v9.signal_fusion_engine import SignalFusionEngine

STATUS_ACTIVE = "ACTIVE"

# Fix 2026-07-15 (audit régime GBPUSD, suite) — traduction devise -> paire
# du vote directionnel. `principle_evaluations.direction` est relatif à LA
# DEVISE évaluée (ex. currency=USD, direction=haussiere veut dire "USD se
# renforce"), pas à la paire. Pour GBPUSD : base (GBP) compte tel quel
# (GBP haussier = GBPUSD haussier) ; quote (USD) doit être INVERSÉE (USD
# haussier = GBPUSD baissier) — jamais fait avant ce fix. Une devise tierce
# (NZD, EUR, ...) n'a aucun mapping directionnel valide vers la paire —
# exclue du vote (mais reste dans principes_source, doctrine 2026-07-07
# DECISIONS_LOG « filtre currency supprimé » — visibilité préservée).
_INVERSE_DIRECTION = {"haussiere": "baissiere", "baissiere": "haussiere", "neutre": "neutre"}


class SignalGeneratorError(ValueError):
    """Erreur de génération de signal (snapshot introuvable, symbole invalide)."""


@dataclass
class SymbolCurrencies:
    base: str
    quote: str

    @classmethod
    def from_symbol(cls, symbol: str) -> "SymbolCurrencies":
        if not symbol or len(symbol) < 6:
            raise SignalGeneratorError(f"symbole invalide pour derivation devise base/quote: {symbol!r}")
        return cls(base=symbol[:3].upper(), quote=symbol[3:6].upper())


class SignalGenerator:
    """Agrège les principes ACTIVE déclenchés en un signal, filtré par
    exploitabilité et régime de marché."""

    def __init__(self, db_path: Path | str | None = None, config: dict | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_signal_db(self.db_path)
        cfg = dict(config) if config else {}
        self.regimes_inadequats = set(cfg.get("regimes_inadequats", REGIMES_INADEQUATS))
        self.confiance_horizon_court = cfg.get("confiance_horizon_court", SIGNAL_CONFIANCE_HORIZON_COURT)
        # SignalFusionEngine (Chantier B DIVERSIFY 2026-07-16) — fusion des
        # principes faibles concordants. Hook additif dans _build_active_signal.
        self.fusion_engine = SignalFusionEngine()

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Chargement contexte ────────────────────────────────
    def _load_forces(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise SignalGeneratorError(f"snapshot de forces introuvable: {snapshot_id!r}")
        return row

    def _load_exploitability(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row | None:
        scene = conn.execute(
            "SELECT scene_id FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        if scene is None:
            return None
        behavior = conn.execute(
            "SELECT behavior_id FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
            (scene["scene_id"],),
        ).fetchone()
        if behavior is None:
            return None
        window = conn.execute(
            "SELECT window_id FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
            (behavior["behavior_id"],),
        ).fetchone()
        if window is None:
            return None
        return conn.execute(
            "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1",
            (window["window_id"],),
        ).fetchone()

    def _load_regime_type(self, conn: sqlite3.Connection, snapshot_id: str, currency: str) -> str | None:
        row = conn.execute(
            "SELECT regime_type FROM regime_snapshots WHERE forces_snapshot_ref = ? AND currency = ?",
            (snapshot_id, currency),
        ).fetchone()
        return row["regime_type"] if row else None

    def _load_all_triggered_active_principles(
        self, conn: sqlite3.Connection, snapshot_id: str
    ) -> list[sqlite3.Row]:
        """Toutes les évaluations ACTIVE triggered=1 du snapshot, toutes
        devises confondues (doctrine 2026-07-07 : visibilité multi-devise
        préservée — `_pair_relative_direction` filtre le VOTE, pas la
        journalisation dans `principes_source`)."""
        return conn.execute(
            "SELECT * FROM principle_evaluations WHERE snapshot_id = ? "
            "AND v9_status = ? AND triggered = 1",
            (snapshot_id, STATUS_ACTIVE),
        ).fetchall()

    @staticmethod
    def _pair_relative_direction(
        raw_direction: str | None, row_currency: str | None, currencies: "SymbolCurrencies"
    ) -> str | None:
        """Traduit `direction` (relative à `row_currency`) vers la direction
        de la PAIRE. Base : identique. Quote : inversée. Devise tierce :
        None (exclue du vote — aucun mapping directionnel valide)."""
        if not raw_direction:
            return None
        if row_currency == currencies.base:
            return raw_direction
        if row_currency == currencies.quote:
            return _INVERSE_DIRECTION.get(raw_direction, raw_direction)
        return None

    def _load_mtf_confirmation(
        self, conn: sqlite3.Connection, snapshot_id: str
    ) -> sqlite3.Row | None:
        """Lecture best-effort de `mtf_confirmations` (MTFConfirmationEngine,
        greffé dans orchestrator.py après regime_detector). Table optionnelle
        (R2 additif) : absente sur une DB pré-MTF -> None, comportement
        inchangé (pas de boost)."""
        try:
            return conn.execute(
                "SELECT direction, aligned, conflict, confidence_boost "
                "FROM mtf_confirmations WHERE forces_snapshot_ref = ?",
                (snapshot_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None

    # ── Génération ─────────────────────────────────────────
    def generate(self, snapshot_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            forces = self._load_forces(conn, snapshot_id)
            symbol, timeframe = forces["symbol"], forces["timeframe"]
            currencies = SymbolCurrencies.from_symbol(symbol)

            exploitability = self._load_exploitability(conn, snapshot_id)
            exploitability_statut = exploitability["statut"] if exploitability else None
            exploitability_id = exploitability["exploitability_id"] if exploitability else None

            # 2026-07-06 — Re-evaluation d'urgence ISM PMI : si l'exploitability
            # DB est non_exploitable (statut calculé avant le fix de
            # ExploitabilityEvaluator._determine_status), on recalcule
            # le statut via _determine_status (sans toucher la DB). Si le
            # nouveau statut est exploitable/watchlist, on l'utilise pour
            # permettre au pipeline de produire des signaux même sur
            # window=absente + confiance élevée (cas marché de range).
            from core.v9.exploitability_evaluator import ExploitabilityEvaluator
            if (
                exploitability_statut in (None, "non_exploitable", "refuse")
                and exploitability is not None
            ):
                try:
                    ee = ExploitabilityEvaluator(db_path=self.db_path)
                    new_status = ee._determine_status(
                        ee._load_window(exploitability["window_id"]),
                        int(exploitability.get("niveau_confiance_global") or 0),
                    )
                    if new_status in ("exploitable", "watchlist"):
                        exploitability_statut = new_status
                except Exception:
                    pass  # Re-evaluation échouée : on garde le statut DB

            regime_type = self._load_regime_type(conn, snapshot_id, currencies.base)

            raison_absence = self._determine_absence_reason(exploitability_statut, regime_type)

            # Charger TOUJOURS les principes ACTIVE déclenchés (toutes
            # devises) pour les journaliser dans principes_source, même
            # quand le signal est marqué "absent". Cela permet d'observer
            # en live quels principes se déclenchent sur des snapshots non
            # exploitables — feedback utile pour calibration. Le champ
            # direction/confiance restent à None si raison_absence est set.
            # Fix 2026-07-15 : un seul chargement (l'ancien filtre currency
            # était un no-op — cf. `_load_all_triggered_active_principles` —
            # appeler deux fois base+quote doublait chaque ligne dans le
            # vote). `_pair_relative_direction` fait le tri devise->vote
            # dans `_build_active_signal`, pas ici.
            triggered = list(self._load_all_triggered_active_principles(conn, snapshot_id))
            if raison_absence is None and not triggered:
                raison_absence = "aucun_principe_actif_declenche"

            if raison_absence is not None:
                signal = self._build_absent_signal(
                    snapshot_id, symbol, timeframe, currencies, regime_type,
                    exploitability_id, exploitability_statut, raison_absence,
                    bool(forces["stale"]), triggered=triggered,
                )
            else:
                mtf = self._load_mtf_confirmation(conn, snapshot_id)
                signal = self._build_active_signal(
                    snapshot_id, symbol, timeframe, currencies, regime_type,
                    exploitability_id, exploitability_statut, triggered, bool(forces["stale"]),
                    forces=forces, mtf=mtf,
                )

            self._write_to_db(conn, signal)
            return signal
        finally:
            conn.close()

    def _determine_absence_reason(
        self, exploitability_statut: str | None, regime_type: str | None
    ) -> str | None:
        if exploitability_statut != "exploitable":
            return f"exploitabilite_non_exploitable:{exploitability_statut or 'absente'}"
        if regime_type is None or regime_type in self.regimes_inadequats:
            return f"regime_inadequat:{regime_type or 'inconnu'}"
        return None

    def _build_absent_signal(
        self, snapshot_id, symbol, timeframe, currencies, regime_type,
        exploitability_id, exploitability_statut, raison_absence, stale,
        triggered=None,
    ) -> dict[str, Any]:
        # P1 DYNAMIC (autopilot 2026-07-13) — un signal "absent" n'a pas
        # de direction, donc on note quand même une stratégie recommandée
        # de secours basée sur la session_marche (utile pour les audits
        # hors-ligne qui veulent savoir "qu'aurait-on fait si le pipeline
        # avait émis ?").
        dynamic_rec = _recommend_dynamic_for_absent(self, symbol, timeframe)
        return {
            "signal_id": _generate_signal_id(symbol, timeframe),
            "schema_version": SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "currency": currencies.base,
            "direction": None,
            "confiance": 0,
            "horizon": None,
            "principes_source": sorted({row["principle_id"] for row in (triggered or [])}),
            "regime_type": regime_type,
            "exploitability_id": exploitability_id,
            "exploitability_statut": exploitability_statut,
            "raison_absence": raison_absence,
            "stale": stale,
            "source_type": self.source_type,
            "exit_strategy_recommended": dynamic_rec["strategy"],
            "tp_pips_recommended": dynamic_rec["tp_pips"],
            "sl_pips_recommended": dynamic_rec["sl_pips"],
        }

    def _build_active_signal(
        self, snapshot_id, symbol, timeframe, currencies, regime_type,
        exploitability_id, exploitability_statut, triggered, stale,
        forces=None, mtf=None,
    ) -> dict[str, Any]:
        # Doctrine realign Phase 9.8 (C3) — vote déjà dynamique par
        # construction : `triggered` ne contient que les évaluations
        # v9_status=ACTIVE + triggered=1 (cf.
        # _load_all_triggered_active_principles), et le vote est une
        # pluralité sur ce sous-ensemble réel, jamais une fraction d'un N
        # fixe. Que config.PRINCIPLE_ACTIVE_IDS contienne 10 ou 27 IDs ne
        # change donc rien ici : aucun dénominateur hardcodé à mettre à
        # jour (vérifié C3, DECISIONS_LOG 2026-07-08 §R8-levée-doctrine-
        # realign).
        #
        # Fix 2026-07-15 (suite audit régime GBPUSD) — `row["direction"]`
        # est relatif à `row["currency"]`, pas à la paire (ex. currency=USD
        # direction=haussiere = "USD se renforce" = baissier pour GBPUSD).
        # `_pair_relative_direction` traduit : base tel quel, quote
        # inversée, devise tierce exclue du vote (None). Vérifié sur le
        # snapshot GBPUSD M15 17:15 du 15/07 : 4 votes "baissiere" portaient
        # tous sur currency=NZD (sans rapport avec GBPUSD) et dominaient le
        # vote à tort — désormais exclus, `principes_source` les conserve
        # (doctrine 2026-07-07, visibilité préservée).
        directions = [
            d for row in triggered
            if (d := self._pair_relative_direction(row["direction"], row["currency"], currencies))
        ]
        vote = Counter(directions)
        if not vote:
            direction = "neutre"
        else:
            top_count = max(vote.values())
            leaders = [d for d, c in vote.items() if c == top_count]
            direction = leaders[0] if len(leaders) == 1 else "neutre"

        confidences = [row["confidence"] for row in triggered if row["confidence"] is not None]
        confiance = round(sum(confidences) / len(confidences)) if confidences else 0
        confiance = max(0, min(100, confiance))

        # Fix 2026-07-15 (audit régime GBPUSD) — fallback forces quand le
        # vote des principes triggered est vide de direction (seuls des
        # principes grammar descriptifs, direction=None, se sont
        # déclenchés). Observé sur GBPUSD M15 15/07 : spread GBP-USD
        # jusqu'à +74, vote toujours vide → direction=neutre malgré un
        # déséquilibre de force sans ambiguïté. Ne s'applique QUE si
        # aucun principe n'a voté (vote vide) — un vote réellement
        # partagé entre haussiere/baissiere (leaders multiples) reste
        # neutre, le fallback ne tranche jamais un désaccord entre
        # principes actifs.
        if not vote and forces is not None:
            try:
                spread = float(forces[f"force_{currencies.base.lower()}"]) - float(
                    forces[f"force_{currencies.quote.lower()}"]
                )
            except (TypeError, KeyError, IndexError):
                spread = 0.0
            if abs(spread) >= SIGNAL_FORCES_FALLBACK_SPREAD_MIN:
                direction = "haussiere" if spread > 0 else "baissiere"
                confiance = max(0, min(100, round(abs(spread))))

        # MTF Confirmation Engine (stratégie Søn, 2026-07-15) — applique le
        # confidence_boost UNIQUEMENT quand la direction MTF (thèse H4/H1
        # confirmée par le TF courant) coïncide avec la direction déjà
        # déterminée par le vote des principes / fallback forces ci-dessus.
        # Ne modifie JAMAIS la direction elle-même — un désaccord MTF ne
        # peut qu'appliquer le malus de conflit, jamais retourner le signal.
        if mtf is not None and direction not in (None, "neutre") and mtf["direction"] == direction:
            if mtf["aligned"] or mtf["conflict"]:
                confiance = max(0, min(100, confiance + int(mtf["confidence_boost"] or 0)))

        # SignalFusionEngine (Chantier B DIVERSIFY 2026-07-16) — fusionne les
        # principes faibles concordants en un signal plus fort. ADDITIF (R2) :
        # ne peut QUE relever la confiance quand ≥2 principes votent la MÊME
        # direction que le signal déjà déterminé ; ne retourne jamais la
        # direction, n'abaisse jamais la confiance. Best-effort (R6) : toute
        # erreur → signal inchangé. La fusion consomme la direction RELATIVE À
        # LA PAIRE (comme le vote), pas la direction brute par-devise.
        fusion_rule = None
        fusion_n = None
        try:
            fusion_input = [
                {
                    "principle_id": row["principle_id"],
                    "direction": self._pair_relative_direction(
                        row["direction"], row["currency"], currencies
                    ),
                    "confidence": row["confidence"],
                }
                for row in triggered
            ]
            fusion = self.fusion_engine.fuse(fusion_input)
        except Exception:
            fusion = None
        if (
            fusion is not None
            and direction not in (None, "neutre")
            and fusion["direction"] == direction
            and fusion["confidence"] > confiance
        ):
            confiance = max(0, min(100, int(fusion["confidence"])))
            fusion_rule = fusion["fusion_rule"]
            fusion_n = fusion["n_fused"]

        horizon = "court_terme" if confiance >= self.confiance_horizon_court else "surveillance"

        # P1 DYNAMIC (autopilot 2026-07-13) — recommande la stratégie
        # de sortie DYNAMIC par session_marche. INEFFET JUSQU'À ACTIVATION
        # OPÉRATEUR (cf DECISIONS_LOG Brief O4 « biais New York/After »).
        # Le signal porte la recommandation ; le résolveur WIN/LOSS peut
        # l'utiliser pour proposer une stratégie de sortie adaptée.
        dynamic_rec = _recommend_dynamic_for_active(self, symbol, timeframe)

        return {
            "signal_id": _generate_signal_id(symbol, timeframe),
            "schema_version": SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "currency": currencies.base,
            "direction": direction,
            "confiance": confiance,
            "horizon": horizon,
            "principes_source": sorted({row["principle_id"] for row in triggered}),
            "regime_type": regime_type,
            "exploitability_id": exploitability_id,
            "exploitability_statut": exploitability_statut,
            "raison_absence": None,
            "stale": stale,
            "source_type": self.source_type,
            "exit_strategy_recommended": dynamic_rec["strategy"],
            "tp_pips_recommended": dynamic_rec["tp_pips"],
            "sl_pips_recommended": dynamic_rec["sl_pips"],
            # Chantier B DIVERSIFY — traçabilité fusion (None si non appliquée).
            # Clés hors SIGNALS_COLUMNS : ignorées à l'écriture DB, exposées au
            # retour pour audit/tests.
            "fusion_rule": fusion_rule,
            "fusion_n": fusion_n,
        }

    def _write_to_db(self, conn: sqlite3.Connection, signal: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **signal,
            "principes_source_json": json.dumps(signal["principes_source"], ensure_ascii=False),
            "created_at": now,
        }
        columns = ", ".join(SIGNALS_COLUMNS)
        placeholders = ", ".join("?" for _ in SIGNALS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO signals ({columns}) VALUES ({placeholders})",
            [values[c] for c in SIGNALS_COLUMNS],
        )
        conn.commit()


def _generate_signal_id(symbol: str, timeframe: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"sig_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{uuid.uuid4().hex[:6]}"


# ── P1 DYNAMIC (autopilot 2026-07-13) — helpers recommandation ────────


def _recommend_dynamic_for_active(self, symbol: str, timeframe: str) -> dict[str, Any]:
    """Recommande la stratégie de sortie DYNAMIC basée sur l'heure UTC
    du moment où le signal est généré.

    Lit `DYNAMIC_PROFILES` (exit_simulator) — calibration empirique Phase 13.2.

    **Brief O4 CEO 2026-07-13** : si la session est blacklistée (NY, after),
    retourne `strategy=None`/`tp_pips=None`/`sl_pips=None`/tradeable=False —
    sessions interdites de trade (WR structurellement négatif Phase 13.2).
    Le `decision_logger` doit alors bloquer `preparer_entree` (defense-in-depth).
    Le profil DYNAMIC reste descriptif (R25') mais aucun trade n'est initié.

    Returns:
        dict {strategy, tp_pips, sl_pips, session_marche, tradeable}. Si
        session blacklistée, strategy/tp_pips/sl_pips=None et tradeable=False.
    """
    hour_utc = datetime.now(timezone.utc).hour
    session_marche = infer_session_from_hour(hour_utc)
    if not is_session_tradable(session_marche):
        return {
            "strategy": None,
            "tp_pips": None,
            "sl_pips": None,
            "session_marche": session_marche,
            "scale": None,
            "tradeable": False,
            "reason": "session_blacklisted_brief_o4",
        }
    profile = DYNAMIC_PROFILES.get(session_marche, DYNAMIC_DEFAULT)
    return {
        "strategy": "DYNAMIC",
        "tp_pips": float(profile["tp_pips"]),
        "sl_pips": float(profile["sl_pips"]),
        "session_marche": session_marche,
        "scale": float(profile.get("scale", 1.0)),
        "tradeable": True,
    }


def _recommend_dynamic_for_absent(self, symbol: str, timeframe: str) -> dict[str, Any]:
    """Identique à _recommend_dynamic_for_active, propage la blacklist Brief O4."""
    rec = _recommend_dynamic_for_active(self, symbol, timeframe)
    return rec


# Lie les méthodes à la classe (Python ne supporte pas les méthodes
# définies après la classe ; on attache via monkey-patch pour conserver
# le style "def locale" sans exploser le diff).
SignalGenerator._recommend_dynamic_for_active = _recommend_dynamic_for_active  # type: ignore[attr-defined]
SignalGenerator._recommend_dynamic_for_absent = _recommend_dynamic_for_absent  # type: ignore[attr-defined]
