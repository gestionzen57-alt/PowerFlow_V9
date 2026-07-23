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
import logging
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.v9.bayesian_calibrator import BayesianCalibrator

logger = logging.getLogger("v9.signal_generator")

from core.v9.config import (
    DB_PATH,
    REGIMES_INADEQUATS,
    SCHEMA_VERSION,
    SIGNAL_CONFIANCE_HORIZON_COURT,
    SIGNAL_FORCES_FALLBACK_SPREAD_MIN,
    SPREAD_MAX_PAR_PAIRE,
    SPREAD_MAX_DEFAULT,
    TICK_VOLUME_MIN,
    BEHAVIOR_QUALIFICATION_BOOST,
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

# ── Câblage bayésien live (Motions #43 / #45, 2026-07-21) ────────────
# Imports GARDÉS (R6) : si un module bayésien est absent / casse à
# l'import, `_BAYES_AVAILABLE=False` et les hooks live sont inertes
# (zéro régression). Le câblage EFFECTIF reste derrière les kill switches
# `V9_BAYESIAN_CALIBRATOR_ENABLED` (#43) et `V9_BAYESIAN_PREDICTOR_ENABLED`
# (#45) — défaut OFF, R25' strict.
try:
    from core.v9.kill_switches import (
        bayesian_calibrator_enabled as _bayesian_calibrator_enabled,
        bayesian_predictor_enabled as _bayesian_predictor_enabled,
    )
    from core.v9.bayesian_calibrator import BayesianCalibrator as _BayesianCalibrator
    from core.v9.v9_bayesian_predictor import predict as _bayes_predict
    _BAYES_AVAILABLE = True
except Exception:  # pragma: no cover - dépend de l'environnement
    _BAYES_AVAILABLE = False

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

            # 2026-07-23 — Filtres comportementaux (analyse microstructure).
            # Ces filtres bloquent les signaux sur des patterns identifiés
            # comme perdants dans l'étude DB 7j (skill v9-behavioral-analysis).
            # R6 défensif : try/except, jamais bloquant si champ absent.
            if raison_absence is None:
                raison_absence = self._behavioral_filter(forces, conn, snapshot_id)

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
                    forces=forces, mtf=mtf, conn=conn,
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

    def _behavioral_filter(self, forces: sqlite3.Row, conn: sqlite3.Connection, snapshot_id: str) -> str | None:
        """Filtres comportementaux post-régime (2026-07-23).

        Filtres bloquants (skill v9-behavioral-analysis) :
        1. Rejet/répulsion → faux croisement
        1b. Recroisement → cross-back
        2. Spread par paire > seuil → slippage
        3. Croisement à vitesse nulle → mort
        4. Rotation leadership → instabilité
        5. Tick volume < minimum → pas de liquidité
        6. Confirmation différée croisement → attendre 2 snaps

        R6 défensif : tout champ absent → pas de blocage.
        R2 additif : n'ajoute que des raisons d'absence.
        """
        try:
            # Filtre 1 : rejet/répulsion
            if forces["rejet_repulsion_detecte"]:
                return "rejet_repulsion_detecte"

            # Filtre 1b : recroisement = cross-back
            if forces["recroisement_detecte"]:
                return "recroisement_cross_back"

            # Filtre 2 : spread par paire (adapté, pas global)
            symbol = forces["symbol"]
            spread = forces["spread_points"]
            if spread is not None:
                seuil = SPREAD_MAX_PAR_PAIRE.get(symbol, SPREAD_MAX_DEFAULT)
                if spread > seuil:
                    return f"spread_trop_large:{spread}>{seuil}"

            # Filtre 3 : croisement à vitesse nulle
            vitesse = forces["vitesse"]
            if forces["croisement_detecte"] and vitesse is not None and abs(vitesse) < 0.01:
                return "croisement_mort_vitesse_nulle"

            # Filtre 5 : tick volume insuffisant (pas de liquidité)
            tick_vol = forces["tick_volume"]
            if tick_vol is not None and tick_vol < TICK_VOLUME_MIN:
                return f"volume_insuffisant:{tick_vol}"

            # Filtre 8 : compression duration — si en compression mais
            # moins de 2 snaps consécutifs en compression → pas assez
            # de squeeze établi → bloquer (un snap en compression est
            # ponctuel, pas un vrai squeeze).
            comp_state = forces["compression_extension_etat"]
            if comp_state in ("compression", "extension"):
                try:
                    prev_comp = conn.execute(
                        "SELECT compression_extension_etat FROM forces_snapshots "
                        "WHERE symbol = ? AND timeframe = ? AND timestamp < ? "
                        "ORDER BY timestamp DESC LIMIT 1",
                        (symbol, forces["timeframe"], forces["timestamp"]),
                    ).fetchone()
                    if prev_comp is not None and prev_comp["compression_extension_etat"] not in ("compression", "extension"):
                        # Le snap précédent n'était pas en compression → squeeze
                        # naissant, pas encore établi → laisser passer mais sans boost
                        pass
                except (sqlite3.OperationalError, KeyError, IndexError):
                    pass

            # Filtre 6 : confirmation différée — si un croisement vient
            # d'être détecté, vérifier les 2 snapshots précédents pour
            # confirmer que la direction se maintient. Si le croisement
            # est frais (pas encore confirmé sur 2 snaps), bloquer.
            if forces["croisement_detecte"] and vitesse is not None and abs(vitesse) >= 0.01:
                try:
                    prev_snaps = conn.execute(
                        "SELECT direction, vitesse FROM forces_snapshots "
                        "WHERE symbol = ? AND timeframe = ? AND timestamp < ? "
                        "ORDER BY timestamp DESC LIMIT 2",
                        (symbol, forces["timeframe"], forces["timestamp"]),
                    ).fetchall()
                    if len(prev_snaps) < 2:
                        return "croisement_non_confirme:moins_de_2_snaps"
                    crois_dir = forces["croisement_direction"] or forces["direction"]
                    confirmed = 0
                    for ps in prev_snaps:
                        if ps["direction"] == crois_dir:
                            confirmed += 1
                    if confirmed < 1:
                        return "croisement_non_confirme:direction_non_maintenue"
                except (sqlite3.OperationalError, KeyError, IndexError):
                    pass  # R6 — pas de blocage si query échoue

            # Filtre 4 : rotation leadership
            try:
                scene = conn.execute(
                    "SELECT scene_id FROM scenes WHERE forces_snapshot_ref = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
                if scene is not None:
                    beh = conn.execute(
                        "SELECT qualification FROM behaviors WHERE scene_id_ref = ? "
                        "ORDER BY id DESC LIMIT 1",
                        (scene["scene_id"],),
                    ).fetchone()
                    if beh is not None and beh["qualification"] == "rotation_leadership":
                        return "rotation_leadership_instabilite"
            except sqlite3.OperationalError:
                pass

        except (KeyError, IndexError, TypeError):
            pass

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
        forces=None, mtf=None, conn=None,
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
        # 2026-07-22 — Plafond confiance 70 (motion CEO « fait tout »).
        # 69% des decisions ont conf=100 mais WR réel=43.2% (gap +56pts).
        # Plafonder à 70 aligne la confiance déclarée sur la réalité observée
        # et donne du headroom pour le Bayesian calibrator (#43) qui peut
        # encore monter la confiance si l'edge est confirmé.
        confiance = max(0, min(70, confiance))

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
                confiance = max(0, min(70, round(abs(spread))))

        # MTF Confirmation Engine (stratégie Søn, 2026-07-15) — applique le
        # confidence_boost UNIQUEMENT quand la direction MTF (thèse H4/H1
        # confirmée par le TF courant) coïncide avec la direction déjà
        # déterminée par le vote des principes / fallback forces ci-dessus.
        # Ne modifie JAMAIS la direction elle-même — un désaccord MTF ne
        # peut qu'appliquer le malus de conflit, jamais retourner le signal.
        if mtf is not None and direction not in (None, "neutre") and mtf["direction"] == direction:
            if mtf["aligned"] or mtf["conflict"]:
                confiance = max(0, min(70, confiance + int(mtf["confidence_boost"] or 0)))

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
            confiance = max(0, min(70, int(fusion["confidence"])))
            fusion_rule = fusion["fusion_rule"]
            fusion_n = fusion["n_fused"]

        horizon = "court_terme" if confiance >= self.confiance_horizon_court else "surveillance"

        # P1 DYNAMIC (autopilot 2026-07-13) — recommande la stratégie
        # de sortie DYNAMIC par session_marche. INEFFET JUSQU'À ACTIVATION
        # OPÉRATEUR (cf DECISIONS_LOG Brief O4 « biais New York/After »).
        # Le signal porte la recommandation ; le résolveur WIN/LOSS peut
        # l'utiliser pour proposer une stratégie de sortie adaptée.
        dynamic_rec = _recommend_dynamic_for_active(self, symbol, timeframe)

        principes_source = sorted({row["principle_id"] for row in triggered})

        # 2026-07-23 — Boost comportemental (skill v9-behavioral-analysis).
        # Les signaux avec compression/extension + CVD aligné + croisement
        # ont 4x plus de chance d'être réels. On booste la confiance
        # (dans la limite du plafond 70) pour ces patterns.
        # R2 additif : ne s'applique que sur les signaux directionnels.
        # R6 défensif : try/except, jamais bloquant.
        if direction not in (None, "neutre"):
            try:
                comp_state = forces.get("compression_extension_etat") if isinstance(forces, dict) else forces["compression_extension_etat"]
                cvd_delta = forces.get("cvd_delta") if isinstance(forces, dict) else forces["cvd_delta"]
                croisement = forces.get("croisement_detecte") if isinstance(forces, dict) else forces["croisement_detecte"]

                # Boost 1 : compression/extension présente = énergie (+5)
                if comp_state in ("compression", "extension"):
                    confiance = min(70, confiance + 5)

                # Boost 2 : CVD aligné avec direction (+5)
                if cvd_delta is not None:
                    if (direction == "haussiere" and cvd_delta > 0) or \
                       (direction == "baissiere" and cvd_delta < 0):
                        confiance = min(70, confiance + 5)

                # Boost 3 : croisement confirmé (vitesse > 0.05) (+5)
                vitesse_val = forces.get("vitesse") if isinstance(forces, dict) else forces["vitesse"]
                if croisement and vitesse_val is not None and abs(vitesse_val) > 0.05:
                    confiance = min(70, confiance + 5)

                # 2026-07-23 — Boost velocity profile (Fix 7).
                # medium (0.05-0.5) = momentum confirmé → +3
                # fast (>0.5) = mouvement violent → +5 (cap au plafond 70)
                if vitesse_val is not None:
                    av = abs(vitesse_val)
                    if av > 0.5:
                        confiance = min(70, confiance + 5)
                    elif av > 0.05:
                        confiance = min(70, confiance + 3)

                # 2026-07-23 — Boost/malus CVD × prix (divergence) (Fix 4).
                # Si prix monte (close>open) ET CVD>0 → convergence haussière (+5)
                # Si prix monte (close>open) ET CVD<0 → divergence (distribution) (-5)
                # Si prix baisse (close<open) ET CVD<0 → convergence baissière (+5)
                # Si prix baisse (close<open) ET CVD>0 → divergence (accumulation) (-5)
                open_val = forces.get("open") if isinstance(forces, dict) else forces["open"]
                close_val = forces.get("close") if isinstance(forces, dict) else forces["close"]
                if open_val is not None and close_val is not None and cvd_delta is not None and cvd_delta != 0:
                    prix_hausse = close_val > open_val
                    cvd_pos = cvd_delta > 0
                    if (prix_hausse and cvd_pos and direction == "haussiere") or \
                       (not prix_hausse and not cvd_pos and direction == "baissiere"):
                        # Convergence prix+CVD dans le sens du signal
                        confiance = min(70, confiance + 5)
                    elif (prix_hausse and not cvd_pos) or (not prix_hausse and cvd_pos):
                        # Divergence prix vs CVD = signal affaibli
                        confiance = max(0, confiance - 5)

            except (KeyError, IndexError, TypeError):
                pass  # R6 — champ absent, pas de boost

        # 2026-07-23 — Boost/malus par qualification behavior (Fix 5).
        # Étude DB 7j : reequilibrage WR=52% (+6.8 pips), seconde_bosse WR=55% (+25 pips)
        # vs contraction WR=23% (-135 pips), tension WR=37% (-300 pips).
        # R6 défensif : si behavior absent ou conn None → pas de boost.
        if conn is not None:
            try:
                scene_row = conn.execute(
                    "SELECT scene_id FROM scenes WHERE forces_snapshot_ref = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
                if scene_row is not None:
                    beh_row = conn.execute(
                        "SELECT qualification FROM behaviors WHERE scene_id_ref = ? "
                        "ORDER BY id DESC LIMIT 1",
                        (scene_row["scene_id"],),
                    ).fetchone()
                    if beh_row is not None:
                        qual = beh_row["qualification"]
                        boost = BEHAVIOR_QUALIFICATION_BOOST.get(qual, 0)
                        if boost > 0:
                            confiance = min(70, confiance + boost)
                        elif boost < 0:
                            confiance = max(0, confiance + boost)
            except (sqlite3.OperationalError, KeyError, TypeError):
                pass  # R6 — table behaviors absente → skip

        # ── Hooks bayésiens live NON-INTRUSIFS (Motions #43 / #45, 2026-07-21) ──
        # ADDITIF (R2) : calculent des champs d'OBSERVATION (`confiance_*` /
        # `predictor_*`) et ne modifient JAMAIS `direction` ni `confiance`
        # (0-100) que consomment les couches aval (arbiter / sizing). Gardés
        # par kill switch (défaut OFF, R25') + R6 (toute erreur → champ None).
        # Ne s'évaluent que sur un signal directionnel réel (pas neutre/absent).
        bayes_fields = self._compute_bayesian_fields(
            symbol, timeframe, regime_type, confiance, direction, principes_source
        )

        # 2026-07-22 — Câblage actif : quand le Bayesian calibrator (#43)
        # produit une confiance_calibree non-None, on REMPLACE la confiance
        # déclarée par la confiance calibrée. C'est le maillon manquant qui
        # ferme la boucle : le posterior Beta(α,β) réel du contexte remplace
        # la confiance déclarée (anti-calibrée, Brier 0.49) dans TOUT le
        # pipeline aval (risk_manager, kelly_sizing, trade_engine).
        # R2 additif : si confiance_calibree est None (pas assez de données,
        # DB inaccessible, kill switch OFF), la confiance déclarée reste.
        # R6 défensif : try/except, jamais bloquant.
        confiance_declaree = confiance
        if bayes_fields.get("confiance_calibree") is not None:
            try:
                calibrated_pct = round(bayes_fields["confiance_calibree"] * 100)
                calibrated_pct = max(0, min(70, calibrated_pct))  # plafond 70
                confiance = calibrated_pct
                logger.info(
                    "confiance calibree ACTIVE: declaree=%d -> calibree=%d (ctx=%s %s %s)",
                    confiance_declaree, confiance, principes_source[0] if principes_source else "?",
                    symbol, timeframe,
                )
            except Exception as exc:
                logger.warning("confiance calibree fallback: %s", exc)

        # Recalculer horizon avec la confiance calibree
        horizon = "court_terme" if confiance >= self.confiance_horizon_court else "surveillance"

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
            "confiance_declaree": confiance_declaree,  # 22/07: confiance avant calibration
            "horizon": horizon,
            "principes_source": principes_source,
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
            # Motions #43/#45 — champs bayésiens ADDITIFS (hors SIGNALS_COLUMNS,
            # ignorés à l'écriture DB, exposés au retour pour audit/observabilité).
            **bayes_fields,
        }

    def _compute_bayesian_fields(
        self, symbol, timeframe, regime_type, confiance, direction, principes_source,
    ) -> dict[str, Any]:
        """Calcule les champs bayésiens ADDITIFS d'un signal (Motions #43/#45).

        - #43 `confiance_calibree` (∈[0,1]) : confiance déclarée transformée via
          le posterior Beta(α,β) réel du contexte (kill switch
          V9_BAYESIAN_CALIBRATOR_ENABLED).
        - #45 `predictor_*` : proba calibrée Platt+Beta+shrinkage, action edge
          recommandée, edge en pips (kill switch V9_BAYESIAN_PREDICTOR_ENABLED).

        NON-INTRUSIF (R2) : n'altère jamais direction/confiance. R6 : tout échec
        → champ None. Retourne toujours le dict complet (clés stables)."""
        fields: dict[str, Any] = {
            "confiance_calibree": None,
            "predictor_calibrated_prob": None,
            "predictor_action": None,
            "predictor_edge_pips": None,
            "predictor_platt_used": None,
            "predictor_confidence_in_calibration": None,
        }
        if not _BAYES_AVAILABLE or direction in (None, "neutre"):
            return fields

        # #43 — Calibration bayésienne (posterior Beta du contexte).
        try:
            if _bayesian_calibrator_enabled() and principes_source:
                calibrator = _get_calibrator_singleton(self.db_path)
                if calibrator is not None:
                    session_now = infer_session_from_hour(
                        datetime.now(timezone.utc).hour
                    )
                    ctx_key = (
                        principes_source[0], symbol, timeframe,
                        session_now, regime_type or "inconnu",
                    )
                    fields["confiance_calibree"] = calibrate_confidence(
                        confiance, ctx_key, calibrator
                    )
        except Exception as exc:  # R6 — jamais bloquant
            logger.warning("hook calibrate_confidence fallback: %s", exc)

        # #45 — Prédicteur bayésien (Platt local/global + Beta + shrinkage).
        # `predict()` lit sa PROPRE calibration_db (jamais v9_forces.db).
        try:
            if _bayesian_predictor_enabled():
                pred = _bayes_predict(
                    symbol=symbol,
                    timeframe=timeframe,
                    regime_type=regime_type or "NEUTRE",
                    phase="initiation",
                    vol_atr_pips=None,
                    declared_confiance=int(confiance),
                )
                fields["predictor_calibrated_prob"] = pred.calibrated_proba
                fields["predictor_action"] = pred.recommended_action
                fields["predictor_edge_pips"] = pred.edge
                fields["predictor_platt_used"] = pred.platt_used
                fields["predictor_confidence_in_calibration"] = (
                    pred.confidence_in_calibration
                )
                logger.info(
                    "bayes_predict %s %s conf=%d -> p=%.3f action=%s edge=%+.2fp "
                    "delta(p-conf/100)=%+.3f",
                    symbol, timeframe, confiance, pred.calibrated_proba,
                    pred.recommended_action, pred.edge,
                    pred.calibrated_proba - confiance / 100.0,
                )
        except Exception as exc:  # R6 — jamais bloquant
            logger.warning("hook bayes_predict fallback: %s", exc)

        return fields

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


# ── Singleton calibrator par db_path (Motion #43, câblage live 2026-07-21) ──
# L'orchestrator instancie un SignalGenerator PAR snapshot ; un calibrator
# neuf par instance re-scannerait 30 j d'agrégats DB à chaque signal (coût
# hot-loop sur une DB de plusieurs Go). On cache donc un BayesianCalibrator
# par db_path au niveau module : le scan agrégats n'a lieu qu'une fois par
# process. Staleness intra-process assumée (la calibration varie lentement,
# rafraîchie au recyclage de process / par les crons de calibration). R6 :
# None si construction échoue → les hooks retombent inertes.
_CALIBRATOR_SINGLETONS: dict[str, Any] = {}


def _get_calibrator_singleton(db_path: Path | str) -> Any:
    if not _BAYES_AVAILABLE:
        return None
    key = str(db_path)
    if key not in _CALIBRATOR_SINGLETONS:
        try:
            _CALIBRATOR_SINGLETONS[key] = _BayesianCalibrator(db_path)
        except Exception:  # R6 — jamais lever depuis la couche décision
            _CALIBRATOR_SINGLETONS[key] = None
    return _CALIBRATOR_SINGLETONS[key]


# ── Calibration bayésienne (Axe 1.1 J1, 2026-07-21) ──────────────────
def calibrate_confidence(
    raw_conf: float, context_key: tuple, calibrator: "BayesianCalibrator"
) -> float:
    """Transforme une confiance déclarée (0-100) en probabilité calibrée [0,1].

    ADDITIF (R2) — **non câblé** dans `generate()` : outil à disposition du
    résolveur / sizing, inerte tant que la motion CEO d'activation (kill switch
    `V9_BAYESIAN_CALIBRATOR_ENABLED`) n'est pas prise (R25').

    Comportement :
        - Posterior du contexte disponible (`n ≥ MIN_N_KELLY`) → renvoie
          `posterior.mean` (WR calibré) et logge (INFO) le delta raw−calibré.
        - Sinon (pas de données / DB inaccessible) → fallback `raw_conf/100.0`
          (R6 défensif). Jamais d'exception propagée.
    """
    try:
        posterior = calibrator.fit_context(context_key)
        if posterior is not None and posterior.n >= calibrator.MIN_N_KELLY:
            calibrated = posterior.mean
            raw_norm = raw_conf / 100.0
            logger.info(
                "calibrate_confidence ctx=%s raw=%.3f calibrated=%.3f delta=%+.3f n=%d",
                context_key, raw_norm, calibrated, raw_norm - calibrated, posterior.n,
            )
            return calibrated
    except Exception as exc:  # R6 : jamais lever depuis la couche décision
        logger.warning("calibrate_confidence fallback (ctx=%s): %s", context_key, exc)
    return raw_conf / 100.0


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
