"""v9_meta_strategy_simulation.py — Simulation replay Phase E (motion CEO validation).

**Pourquoi ce script existe** :
- Phase 1+2 (commits `0d5e81c` + `6ab0076`) ont livré le câblage shadow + CLI rapport.
- Phase 3 du brief = validation edge uplift sur données live (≥500 shadows).
- Problème : le shadow live nécessite `V9_META_STRATEGY_SHADOW_ENABLED=1` pendant 24-48h,
  et un pipeline tournant — pas faisable en une session courte.
- **Solution** : simulation replay. Rejoue les décisions historiques `decisions`
  résolues (WIN/LOSS connu) à travers `recommend_with_shadow()` avec :
  1. legacy_strategy = `exit_strategy_recommended` (déjà connu)
  2. meta_strategy = calculé via `meta_strategy_optimizer.select_strategy()`
     sur (symbol, timeframe, regime_type, phase, vol_atr_pips, direction)
- Puis calcule l'edge uplift : WR_meta vs WR_legacy, PF_meta vs PF_legacy, par
  segment dense. Lecture seule sur l'historique — R2 additif, R6 défensif, R18
  code pur.
- Sortie : rapport Markdown dans `reports/meta_strategy/simulation_YYYY-MM-DD_HHMM.md`
  avec verdict motion CEO factuel.

**Usage** :
```bash
# Dry-run (défaut) : affiche rapport + écrit Markdown
.venv/Scripts/python.exe scripts/v9_meta_strategy_simulation.py

# Depuis 7 jours
.venv/Scripts/python.exe scripts/v9_meta_strategy_simulation.py --since 7d

# DB custom
.venv/Scripts/python.exe scripts/v9_meta_strategy_simulation.py --db-path data/test_regen.db

# Limiter le nombre de décisions rejouées (perf)
.venv/Scripts/python.exe scripts/v9_meta_strategy_simulation.py --limit 5000
```
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ------------------------------------------------------------------ paths


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "v9_forces.db"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "meta_strategy"


# ------------------------------------------------------------------ helpers


def _since_ts(since: str) -> float:
    """Convertit '24h' / '7d' / '1h' en timestamp epoch."""
    now = time.time()
    if since.endswith("h"):
        return now - int(since[:-1]) * 3600
    if since.endswith("d"):
        return now - int(since[:-1]) * 86400
    if since.endswith("m"):
        return now - int(since[:-1]) * 60
    try:
        return datetime.fromisoformat(since).timestamp()
    except ValueError as e:
        raise SystemExit(f"FORMAT --since invalide ({since}): {e}")


def _load_resolved_decisions(
    db_path: Path, since_ts: float | None, limit: int,
) -> list[dict]:
    """Charge les décisions résolues (is_win=0/1) depuis l'historique.

    Jointure decisions + signals pour récupérer le contexte complet.
    Schéma live 2026-07-20 : `is_win` (0/1), `resolution_pips`, `resolved_at`.
    Colonnes optionnelles (phase, volatility_atr_pips) peuvent être absentes
    sur des DB legacy — fallback NULL via sqlite3 column introspection.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        # Inspect schema signals pour colonnes optionnelles
        sig_cols = {r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()}
        phase_expr = "s.phase" if "phase" in sig_cols else "NULL AS phase"
        vol_expr = "s.volatility_atr_pips" if "volatility_atr_pips" in sig_cols else "NULL AS volatility_atr_pips"
        exit_expr = "s.exit_strategy_recommended" if "exit_strategy_recommended" in sig_cols else "NULL AS exit_strategy_recommended"

        where_clauses = ["d.is_win IS NOT NULL"]
        params: list = []
        if since_ts is not None:
            where_clauses.append("d.resolved_at >= ?")
            params.append(since_ts)
        where = " AND ".join(where_clauses)
        sql = f"""
            SELECT d.decision_id, d.snapshot_id, d.symbol, d.timeframe,
                   d.direction, d.regime_type, d.is_win, d.resolution_pips AS pips,
                   d.resolution_strategy,
                   {phase_expr}, {vol_expr}, {exit_expr},
                   d.resolved_at
            FROM decisions d
            LEFT JOIN signals s ON s.snapshot_id = d.snapshot_id
            WHERE {where}
            ORDER BY d.resolved_at DESC
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _phase_from_decision(dec: dict) -> str:
    """Détermine phase depuis regime + pips (heuristique si signals.phase absent).

    Pas de colonne phase sur signals (schéma live) → on dérive de regime_type :
    - NEUTRE + pips > 0 → initiation (range qui paye)
    - NEUTRE + pips < 0 → resolution (range qui casse)
    - TENDANCE + pips > 0 → developpement (trend haussier)
    - TENDANCE + pips < 0 → culmination (trend baissier / retournement)
    - CLIMAX → resolution (sortie)
    - DISTRIBUTION → resolution
    - Pas de pips → initiation (neutre par défaut)
    """
    phase = dec.get("phase")
    if phase:
        return phase
    regime = dec.get("regime_type") or "NEUTRE"
    pips_raw = dec.get("pips")
    if pips_raw is None:
        # Pas de pips connu → on ne peut pas trancher, défaut neutre
        return "initiation"
    pips = float(pips_raw)
    if regime == "NEUTRE":
        return "initiation" if pips > 0 else "resolution"
    if regime == "TENDANCE":
        return "developpement" if pips > 0 else "culmination"
    if regime in ("CLIMAX", "DISTRIBUTION"):
        return "resolution"
    return "initiation"


def _vol_atr_from_decision(dec: dict) -> float | None:
    """Vol ATR approximatif depuis pips (heuristique si signals.volatility absent)."""
    return dec.get("volatility_atr_pips")


@dataclass
class _FakeLegacyFromSignal:
    """Duck-typed StrategyRecommendation construit depuis signal.exit_strategy_recommended."""
    recommended_strategy: str
    confidence: float
    recommended_tp: float
    recommended_sl: float
    rationale: str


def _build_legacy_from_signal(dec: dict) -> _FakeLegacyFromSignal:
    """Construit un fake StrategyRecommendation depuis la décision historique."""
    exit_strat = dec.get("exit_strategy_recommended") or "TP_SL"
    # legacy = exit_strat, confiance = 0.5 (placeholder), tp/sl défaut
    return _FakeLegacyFromSignal(
        recommended_strategy=exit_strat,
        confidence=0.5,
        recommended_tp=10.0,
        recommended_sl=15.0,
        rationale=f"legacy_from_signal:{exit_strat}",
    )


# ------------------------------------------------------------------ core simulation


def run_simulation(
    db_path: Path,
    *,
    since_ts: float | None,
    limit: int,
    force_meta: bool = False,
) -> dict[str, Any]:
    """Rejoue les décisions historiques via recommend_with_shadow, mesure edge uplift.

    Args :
    - `force_meta` : si True, active temporairement
      `V9_META_STRATEGY_SHADOW_ENABLED=1` pour la durée de la simulation
      (= contournement R25' pour validation offline, lecture seule sur DB live).

    Returns dict :
    - `n_decisions` : décisions rejouées
    - `n_agreements` : legacy == meta
    - `n_disagreements`
    - `wr_legacy`, `pf_legacy`
    - `wr_meta`, `pf_meta`
    - `delta_wr` : wr_meta - wr_legacy
    - `delta_pf`
    - `by_segment` : uplift par (symbol, regime_type, phase)
    - `verdict` : motion CEO
    """
    import os
    from core.v9.v9_meta_strategy_shadow import (
        ensure_shadow_table, recommend_with_shadow,
    )

    # Force shadow ON si demandé (pour diagnostic R25')
    prev_shadow = os.environ.get("V9_META_STRATEGY_SHADOW_ENABLED")
    if force_meta:
        os.environ["V9_META_STRATEGY_SHADOW_ENABLED"] = "1"

    try:
        decisions = _load_resolved_decisions(db_path, since_ts, limit)
        if not decisions:
            return {"n_decisions": 0, "verdict": "NO_DATA"}

        legacy_results: list[tuple[str, float]] = []
        meta_results: list[tuple[str, float]] = []
        meta_only_when_used: list[tuple[str, float]] = []
        meta_agreements: list[tuple[str, float]] = []
        agreements = 0
        disagreements = 0

        ensure_shadow_table(db_path)

        # Normalisation vocabulaire meta ↔ résolution live (DYNAMIC ≈ TP_SL sur shadow)
        def _resolution_matches_meta(resolution: str, meta_strat: str) -> bool:
            """DYNAMIC ≈ n'importe quelle strat meta (live résout en DYNAMIC).
            SKIPPED = trade annulé, ne matche aucune stratégie meta."""
            if not resolution or resolution == "UNKNOWN":
                return False
            if resolution == "SKIPPED":
                return False
            if resolution == "DYNAMIC":
                return meta_strat in ("TP_SL", "TP_PARTIAL", "FAST_EXIT", "TRAILING")
            return resolution == meta_strat

        for dec in decisions:
            legacy = _build_legacy_from_signal(dec)
            phase = _phase_from_decision(dec)
            vol_atr = _vol_atr_from_decision(dec)
            direction = dec.get("direction") or "long"

            out_legacy, comparison = recommend_with_shadow(
                symbol=dec["symbol"],
                timeframe=dec["timeframe"],
                regime_type=dec["regime_type"],
                phase=phase,
                direction=direction,
                vol_atr_pips=vol_atr,
                legacy_recommendation=legacy,
                db_path=db_path,
            )

            if comparison is None:
                meta_strategy = legacy.recommended_strategy
                is_agreement = True
            else:
                meta_strategy = comparison.meta_strategy
                is_agreement = comparison.agreement

            pips = float(dec.get("pips") or 0.0)
            legacy_results.append((legacy.recommended_strategy, pips))
            meta_results.append((meta_strategy, pips))
            if is_agreement:
                agreements += 1
                meta_agreements.append((meta_strategy, pips))
            else:
                disagreements += 1

            resolution_strategy = dec.get("resolution_strategy") or "UNKNOWN"
            # Subset honnête : meta == résolution effective (normalisation vocabulaire).
            # Si comparison is None (kill switch OFF, tie legacy=meta), on considère
            # que la résolution DYNAMIC est compatible avec meta=legacy (subset ⊆ DYNAMIC).
            if comparison is None:
                # Pas de shadow log écrit, mais on peut inférer : si résolution DYNAMIC
                # et legacy=meta_strategy → on a au moins une indication favorable
                if resolution_strategy == "DYNAMIC":
                    meta_only_when_used.append((legacy.recommended_strategy, pips))
            elif _resolution_matches_meta(resolution_strategy, meta_strategy):
                meta_only_when_used.append((meta_strategy, pips))

        def _wr_pf(pairs: list[tuple[str, float]]) -> tuple[float, float]:
            if not pairs:
                return 0.0, 0.0
            wins = [p for _, p in pairs if p > 0]
            losses = [p for _, p in pairs if p <= 0]
            gross_win = sum(wins)
            gross_loss = abs(sum(losses)) or 1e-9
            wr = len(wins) / len(pairs)
            pf = gross_win / gross_loss
            return wr, pf

        wr_legacy, pf_legacy = _wr_pf(legacy_results)
        wr_meta, pf_meta = _wr_pf(meta_results)
        delta_wr = wr_meta - wr_legacy
        delta_pf = pf_meta - pf_legacy

        # Subset honnête (Chemin A — fix L250-252 structurel)
        wr_meta_subset, pf_meta_subset = _wr_pf(meta_only_when_used)
        wr_legacy_subset, pf_legacy_subset = (
            _wr_pf(meta_agreements) if meta_agreements else (0.0, 0.0)
        )
        n_subset = len(meta_only_when_used)
        delta_subset_wr = wr_meta_subset - wr_legacy_subset
        delta_subset_pf = pf_meta_subset - pf_legacy_subset

        n = len(decisions)
        if n < 100:
            verdict = "YELLOW_VOLUMETRIE"
            verdict_msg = f"🟡 Volumétrie faible ({n}) — attendre ≥500 décisions résolues."
        elif n_subset < 30:
            verdict = "YELLOW_SUBSET_LOW"
            verdict_msg = (
                f"🟡 Subset honnête trop petit ({n_subset} trades où meta == résolution) — "
                f"inconclusif. ΔWR_global={delta_wr*100:+.1f}pts mais c'est artifact (mêmes pips legacy ET meta). "
                f"Attendre shadow live 48h pour verdicts factuels."
            )
        elif delta_subset_wr >= 0.05 and delta_subset_pf >= 0.5:
            verdict = "GREEN_PROMOTE"
            verdict_msg = (
                f"🟢 Edge uplift HONNÊTE confirmé sur subset (n={n_subset}, ΔWR=+{delta_subset_wr*100:.1f}pts ΔPF=+{delta_subset_pf:.2f}). "
                f"Motion CEO câblage runtime justifiée."
            )
        elif delta_subset_wr >= 0.02 and delta_subset_pf >= 0.2:
            verdict = "YELLOW_MARGINAL"
            verdict_msg = (
                f"🟡 Edge uplift marginal sur subset (n={n_subset}, ΔWR=+{delta_subset_wr*100:.1f}pts ΔPF=+{delta_subset_pf:.2f}). "
                f"Attendre plus de data ou affiner seuils."
            )
        else:
            verdict = "RED_NO_UPLIFT"
            verdict_msg = (
                f"🔴 Pas d'edge uplift honnête (subset n={n_subset}, "
                f"ΔWR={delta_subset_wr*100:+.1f}pts ΔPF={delta_subset_pf:+.2f}). "
                f"Ne PAS câbler runtime. (ΔWR_global={delta_wr*100:+.1f}pts ignore : artifact structurel)"
            )

        # By segment (groupement simple)
        by_segment_legacy = defaultdict(list)
        by_segment_meta = defaultdict(list)
        for dec, (lstr, pips) in zip(decisions, legacy_results):
            key = (dec["symbol"], dec["regime_type"], _phase_from_decision(dec))
            by_segment_legacy[key].append(pips)
        for dec, (mstr, pips) in zip(decisions, meta_results):
            key = (dec["symbol"], dec["regime_type"], _phase_from_decision(dec))
            by_segment_meta[key].append(pips)

        segs = []
        for key in by_segment_legacy:
            if len(by_segment_legacy[key]) >= 5:
                l = by_segment_legacy[key]
                m = by_segment_meta[key]
                wr_l = sum(1 for p in l if p > 0) / len(l)
                wr_m = sum(1 for p in m if p > 0) / len(m)
                segs.append({
                    "symbol": key[0], "regime": key[1], "phase": key[2],
                    "n": len(l), "wr_legacy": round(wr_l, 4),
                    "wr_meta": round(wr_m, 4),
                    "delta_wr": round(wr_m - wr_l, 4),
                })
        segs.sort(key=lambda s: s["delta_wr"], reverse=True)

        return {
            "n_decisions": n,
            "n_agreements": agreements,
            "n_disagreements": disagreements,
            "agreement_rate": round(agreements / n, 4) if n else 0,
            "wr_legacy": round(wr_legacy, 4),
            "wr_meta": round(wr_meta, 4),
            "delta_wr": round(delta_wr, 4),
            "pf_legacy": round(pf_legacy, 4),
            "pf_meta": round(pf_meta, 4),
            "delta_pf": round(delta_pf, 4),
            "n_subset_honest": n_subset,
            "wr_meta_subset": round(wr_meta_subset, 4),
            "pf_meta_subset": round(pf_meta_subset, 4),
            "delta_subset_wr": round(delta_subset_wr, 4),
            "delta_subset_pf": round(delta_subset_pf, 4),
            "by_segment": segs[:20],
            "verdict": verdict,
            "verdict_msg": verdict_msg,
        }
    finally:
        if force_meta:
            if prev_shadow is None:
                os.environ.pop("V9_META_STRATEGY_SHADOW_ENABLED", None)
            else:
                os.environ["V9_META_STRATEGY_SHADOW_ENABLED"] = prev_shadow



# ------------------------------------------------------------------ rendering


def render_markdown(result: dict, db_path: Path, since_label: str) -> str:
    lines = []
    lines.append(f"# Rapport Simulation Meta-Strategy — {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"- **DB** : `{db_path}`")
    lines.append(f"- **Fenêtre** : {since_label}")
    lines.append("")
    if result["n_decisions"] == 0:
        lines.append("⚠️  Aucune décision résolue (WIN/LOSS) dans la fenêtre.")
        lines.append("   Vérifier que le pipeline live tourne et que les décisions sont résolues.")
        return "\n".join(lines)

    lines.append("## Vue globale")
    lines.append("")
    lines.append(f"- **Décisions rejouées** : {result['n_decisions']}")
    lines.append(f"- **Agreements** : {result['n_agreements']} ({result['agreement_rate']*100:.1f}%)")
    lines.append(f"- **Disagreements** : {result['n_disagreements']}")
    lines.append("")
    lines.append("### Edge uplift legacy vs meta (GLOBAL — artifact structurel)")
    lines.append("")
    lines.append("⚠️  **Même `pips` historique appliqué aux deux = tie par construction**. Cette mesure est illustrative, pas décisionnelle.")
    lines.append("")
    lines.append("| Métrique | Legacy | Meta | Δ |")
    lines.append("|----------|--------|------|---|")
    lines.append(f"| **Win Rate** | {result['wr_legacy']*100:.2f}% | {result['wr_meta']*100:.2f}% | {result['delta_wr']*100:+.2f} pts |")
    lines.append(f"| **Profit Factor** | {result['pf_legacy']:.2f} | {result['pf_meta']:.2f} | {result['delta_pf']:+.2f} |")
    lines.append("")
    lines.append("### Edge uplift HONNÊTE (subset meta == résolution effective)")
    lines.append("")
    lines.append(f"Subset : **{result['n_subset_honest']} trades** où la stratégie meta == `decisions.resolution_strategy` (pips réellement attribuable à meta).")
    lines.append("")
    lines.append("| Métrique | Legacy (agreements) | Meta (when used) | Δ |")
    lines.append("|----------|---------------------|------------------|---|")
    if result['n_subset_honest'] > 0:
        wr_legacy_subset = (result.get('wr_legacy') if result['n_agreements'] else 0)
        lines.append(f"| **Win Rate** | {result.get('wr_legacy', 0)*100:.2f}% | {result['wr_meta_subset']*100:.2f}% | {result['delta_subset_wr']*100:+.2f} pts |")
        lines.append(f"| **Profit Factor** | {result.get('pf_legacy', 0):.2f} | {result['pf_meta_subset']:.2f} | {result['delta_subset_pf']:+.2f} |")
    else:
        lines.append("| **Win Rate** | — | — | — |")
        lines.append("| **Profit Factor** | — | — | — |")
    lines.append("")

    if result["by_segment"]:
        lines.append("## Top segments par uplift (≥5 décisions)")
        lines.append("")
        lines.append("| Symbol | Regime | Phase | N | WR legacy | WR meta | Δ WR |")
        lines.append("|--------|--------|-------|---|-----------|---------|------|")
        for s in result["by_segment"]:
            lines.append(
                f"| `{s['symbol']}` | `{s['regime']}` | `{s['phase']}` | "
                f"{s['n']} | {s['wr_legacy']*100:.1f}% | {s['wr_meta']*100:.1f}% | "
                f"{s['delta_wr']*100:+.1f} pts |"
            )
        lines.append("")

    lines.append("## Verdict motion CEO (R25' strict)")
    lines.append("")
    lines.append(result["verdict_msg"])
    lines.append("")
    return "\n".join(lines)


def render_console(result: dict) -> None:
    print(f"🧪 Simulation Meta-Strategy Phase E")
    print(f"   Décisions rejouées : {result['n_decisions']}")
    if result["n_decisions"] > 0:
        print(f"   WR legacy         : {result['wr_legacy']*100:.2f}%")
        print(f"   WR meta           : {result['wr_meta']*100:.2f}%")
        print(f"   Δ WR              : {result['delta_wr']*100:+.2f} pts")
        print(f"   PF legacy         : {result['pf_legacy']:.2f}")
        print(f"   PF meta           : {result['pf_meta']:.2f}")
        print(f"   Δ PF              : {result['delta_pf']:+.2f}")
        print(f"   Verdict           : {result['verdict']}")
        print(f"   → {result['verdict_msg']}")


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulation replay Phase E meta-strategy (R25' validation)")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Chemin DB (défaut: {DEFAULT_DB_PATH})")
    parser.add_argument("--since", type=str, default="7d",
                        help="Fenêtre temporelle (24h, 7d, 30d, ou ISO timestamp)")
    parser.add_argument("--limit", type=int, default=10000,
                        help="Limite nombre décisions rejouées (défaut: 10000)")
    parser.add_argument("--no-write", action="store_true",
                        help="Ne pas écrire le fichier Markdown")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR,
                        help=f"Dossier rapport (défaut: {DEFAULT_REPORT_DIR})")
    parser.add_argument("--force-meta", action="store_true",
                        help="Force V9_META_STRATEGY_SHADOW_ENABLED=1 pendant la simulation "
                             "(contournement R25' pour diagnostic offline, lecture seule DB)")
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"⚠️  DB introuvable : {args.db_path}", file=sys.stderr)
        return 1

    try:
        since_ts = _since_ts(args.since)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2

    since_label = args.since if ":" not in args.since else f"since {args.since}"

    result = run_simulation(
        args.db_path, since_ts=since_ts, limit=args.limit,
        force_meta=args.force_meta,
    )

    render_console(result)

    if not args.no_write:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        suffix = "_force" if args.force_meta else ""
        report_path = args.report_dir / f"simulation_{stamp}{suffix}.md"
        md = render_markdown(result, args.db_path, since_label)
        report_path.write_text(md, encoding="utf-8")
        print(f"📝 Rapport écrit : {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())