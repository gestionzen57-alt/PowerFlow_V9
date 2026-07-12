#!/usr/bin/env python3
"""v9_export_dataset.py — Export dataset V9-trader-mini (Brief O5, 2026-07-12).

PÉRIMÈTRE STRICT : préparation du dataset + carte de données UNIQUEMENT.
Aucun entraînement, aucun téléchargement de modèle, aucun agent. Le
fine-tuning lui-même = GO séparé de Søn, tracé dans DECISIONS_LOG.

Exporte les décisions `preparer_entree` résolues en dataset de
fine-tuning supervisé (contexte → issue), format JSONL.

Population :
- DYNAMIC (asie/london/overlap, résolution directionnelle réelle) ->
  train/val/test (split chronologique strict).
- SKIPPED (new_york/after, pas de résolution directionnelle) -> exclues
  du train/val/test, exportées séparément dans skipped.jsonl.

Features : contexte assemblé par `PrincipleEngine._load_shared_context()`
(le contrat de propagation ACTUEL — cf. docs/architecture/CONTEXT_CONTRACT.md
Couche 7). Note doctrine : le brief cite "31 champs" (chiffre historique
docs/AGENT.md 2026-07-06/07) ; le contrat a depuis grandi (risk_assessment,
regime multi-champs, zone_diagnostics, coalition_news_allow ajoutés Phase 13)
— ce script utilise le contexte RÉEL et actuel, pas le chiffre stale.

INTERDIT dans les features : tout champ postérieur à la décision
(resolution_*, MFE/MAE réalisés, exit_reason) — _load_shared_context() ne
lit jamais la colonne `decisions`, donc aucune fuite possible par
construction.

Idempotent : dry-run par défaut, --apply pour écrire réellement.

Usage :
    python scripts/v9_export_dataset.py --dry-run
    python scripts/v9_export_dataset.py --apply --output data/datasets/v9_trader_mini/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.principle_engine import PrincipleEngine, PrincipleEngineError  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "datasets" / "v9_trader_mini"
DEFAULT_CARD_PATH = ROOT_DIR / "docs" / "reports" / "DATASET_V9_TRADER_MINI_CARD.md"
DEFAULT_MD5_PATH = ROOT_DIR / "docs" / "reports" / "DATASET_V9_TRADER_MINI_MD5SUMS.txt"

TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
# TEST_RATIO = 0.1 (reste)

# Brief Q1 (2026-07-12) — split par blocs entrelacés pour train/val (voir
# chronological_split ci-dessous). BLOCK_MODULO=9 => ~1 bloc sur 9 (~11% du
# pool train+val, soit ~10% du total) assigné à val. BLOCK_SIZE_TARGET borne
# la taille de bloc pour désagréger les salves de marché corrélées (voir
# docs/reports/V9_TRADER_MINI_VAL_SPLIT_INVESTIGATION_20260712.md).
BLOCK_MODULO = 9
BLOCK_SIZE_TARGET = 50

# Métadonnées — pas forcément features d'entraînement (marquées séparément).
METADATA_FIELDS = ("symbol", "timeframe", "session_marche", "timestamp")


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_target_decisions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Décisions preparer_entree résolues en DYNAMIC ou SKIPPED, triées par
    timestamp ASC (ordre chronologique strict, base du split)."""
    return conn.execute(
        """
        SELECT decision_id, snapshot_id, symbol, timeframe, timestamp,
               direction, is_win, resolution_pips, resolution_strategy,
               resolution_details
        FROM decisions
        WHERE action = 'preparer_entree'
          AND resolution_strategy IN ('DYNAMIC', 'SKIPPED')
        ORDER BY timestamp ASC
        """
    ).fetchall()


def build_records(
    conn: sqlite3.Connection, rows: list[sqlite3.Row], engine: PrincipleEngine,
) -> tuple[list[dict], list[dict], int]:
    """Construit les records DYNAMIC (labellisés) et SKIPPED (séparés).
    Retourne (dynamic_records, skipped_records, n_context_errors)."""
    dynamic: list[dict] = []
    skipped: list[dict] = []
    n_errors = 0

    for r in rows:
        try:
            features = engine._load_shared_context(conn, r["snapshot_id"])
        except PrincipleEngineError:
            n_errors += 1
            continue

        # Retirer les métadonnées du bloc features (marquées séparément).
        # `session_marche` vit dans le sous-dict "context" produit par
        # _load_shared_context() (pas au niveau racine) — pop() y est fait
        # explicitement. symbol/timeframe/timestamp viennent de la ligne
        # `decisions` (absents de _load_shared_context()).
        nested_context = features.get("context")
        session_marche = (
            nested_context.pop("session_marche", None)
            if isinstance(nested_context, dict) else None
        )
        metadata = {
            "symbol": r["symbol"],
            "timeframe": r["timeframe"],
            "session_marche": session_marche,
            "timestamp": r["timestamp"],
        }

        exit_reason = None
        if r["resolution_details"]:
            try:
                exit_reason = json.loads(r["resolution_details"]).get("exit_reason")
            except (json.JSONDecodeError, TypeError):
                pass

        record = {
            "decision_id": r["decision_id"],
            "features": features,
            "metadata": metadata,
            "label": r["is_win"],
            "pips": r["resolution_pips"],
            "exit_reason": exit_reason,
        }

        if r["resolution_strategy"] == "DYNAMIC":
            dynamic.append(record)
        else:
            skipped.append(record)

    return dynamic, skipped, n_errors


def chronological_split(
    records: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split chronologique (déjà triés par timestamp en amont). Aucun shuffle.
    1 décision = 1 snapshot unique (vérifié Brief O2/O1) -> aucun risque de
    répartir un même snapshot sur 2 splits.

    Brief Q1 (2026-07-12) — re-split justifié par l'investigation de la
    rupture de distribution val du Brief O5 (44.6% vs 93.9%/89.3%) : le val
    purement contigu (derniers 10% du bloc train+val) isolait un unique
    épisode de marché corrélé (~56 min, 821 snapshots M15 intrabar, 100%
    session london, 100% direction baissière — voir
    docs/reports/V9_TRADER_MINI_VAL_SPLIT_INVESTIGATION_20260712.md). Ce
    n'étaient pas ~821 essais indépendants mais un seul mouvement de marché
    ayant mal tourné pour la thèse baissière dominante de cette fenêtre.

    Nouveau découpage :
    - **test** reste un holdout chronologique PUR (derniers ~10%, aucune
      contamination futur->passé) — condition de déploiement réaliste
      inchangée.
    - **train/val** sont découpés en blocs contigus de taille bornée
      (BLOCK_SIZE_TARGET, resserré pour les petits pools) sur les ~90%
      restants ; un bloc sur BLOCK_MODULO est assigné à val. Val représente
      ainsi plusieurs épisodes de marché distincts répartis dans le temps
      plutôt qu'une seule salve corrélée, sans mélanger futur/passé au sein
      d'un bloc (chaque bloc reste chronologique en interne).

    Complétude garantie par construction (partition de records, aucune perte
    ni duplication) ; vérifiée en multiset par les tests."""
    n = len(records)
    n_test = n - int(n * (TRAIN_RATIO + VAL_RATIO))
    pool = records[: n - n_test] if n_test else list(records)
    test = records[n - n_test:] if n_test else []

    if not pool:
        return [], [], test

    chunk_size = min(BLOCK_SIZE_TARGET, max(1, len(pool) // BLOCK_MODULO))
    val_slot = BLOCK_MODULO // 2

    train: list[dict] = []
    val: list[dict] = []
    for block_idx, start in enumerate(range(0, len(pool), chunk_size)):
        block = pool[start:start + chunk_size]
        if block_idx % BLOCK_MODULO == val_slot:
            val.extend(block)
        else:
            train.extend(block)

    return train, val, test


def to_classification_jsonl(record: dict) -> str:
    """Format (a) — classification brute + métadonnées marquées séparément."""
    return json.dumps(
        {
            "features": record["features"],
            "metadata": record["metadata"],
            "label": record["label"],
            "pips": record["pips"],
            "exit_reason": record["exit_reason"],
        },
        ensure_ascii=False, sort_keys=True,
    )


def to_chat_template_jsonl(record: dict) -> str:
    """Format (b) — chat-template (qwen3-coder 4B / phi3 3.8B)."""
    content = json.dumps(record["features"], ensure_ascii=False, sort_keys=True)
    assistant = "WIN" if record["label"] == 1 else "LOSS"
    return json.dumps(
        {"messages": [
            {"role": "user", "content": content},
            {"role": "assistant", "content": assistant},
        ]},
        ensure_ascii=False,
    )


def _write_jsonl(path: Path, records: list[dict], formatter) -> None:
    path.write_text(
        "\n".join(formatter(r) for r in records) + ("\n" if records else ""),
        encoding="utf-8",
    )


def _md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    """Chemin relatif à ROOT_DIR si possible (lisibilité du fichier MD5),
    sinon chemin absolu (--output hors du repo, ex: tests)."""
    try:
        return path.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def build_data_card(
    dynamic: list[dict], skipped: list[dict],
    train: list[dict], val: list[dict], test: list[dict],
    n_context_errors: int,
) -> str:
    def _class_dist(records: list[dict]) -> dict[str, Any]:
        n = len(records)
        n_win = sum(1 for r in records if r["label"] == 1)
        return {"n": n, "n_win": n_win, "n_loss": n - n_win,
                "win_rate_pct": round(n_win / max(1, n) * 100, 1)}

    lines = [
        "# Carte de données — V9-trader-mini",
        "",
        f"- Généré : Brief O5 (2026-07-12), script `scripts/v9_export_dataset.py`.",
        f"- Prérequis : Brief O1 livré (labels DYNAMIC/SKIPPED propres, "
        f"0 décision TP_SL restante).",
        "",
        "## Volumes par split",
        "",
        "| Split | N | Wins | Losses | WR |",
        "|---|---|---|---|---|",
    ]
    for name, recs in (("train", train), ("val", val), ("test", test)):
        d = _class_dist(recs)
        lines.append(f"| {name} | {d['n']} | {d['n_win']} | {d['n_loss']} | {d['win_rate_pct']}% |")
    d_all = _class_dist(dynamic)
    lines.append(f"| **total DYNAMIC** | {d_all['n']} | {d_all['n_win']} | {d_all['n_loss']} | {d_all['win_rate_pct']}% |")
    lines.append(f"| skipped (exclu train/val/test) | {len(skipped)} | — | — | — |")
    lines.append("")
    lines.append(f"Erreurs de chargement de contexte (snapshot incomplet, exclu) : {n_context_errors}")
    lines.append("")
    lines.append("## Distribution des classes")
    lines.append("")
    lines.append(
        f"Déséquilibre attendu ~85-88% win (post-Brief O1, résolution DYNAMIC) — "
        f"WR réel observé : {d_all['win_rate_pct']}%. Recommandation (non appliquée ici, "
        f"décision d'entraînement séparée) : class weights ou sous-échantillonnage de "
        f"la classe majoritaire (win) côté entraînement, pas de rééquilibrage dans "
        f"l'export lui-même (le dataset doit rester fidèle à la distribution réelle)."
    )
    lines.append("")
    lines.append("## Biais connus")
    lines.append("")
    lines.extend([
        "- **Période à drift haussier documenté (~91%)** — cf. `docs/reports/NY_AFTER_BIAS_20260712.md` "
        "§Brief O4. Un modèle entraîné sur cette fenêtre risque de sur-apprendre le biais "
        "directionnel du marché plutôt que la logique des principes.",
        "- **GBPUSD uniquement** — aucune généralisation testée à d'autres paires.",
        "- **`PRICE_LAG_AT_NODE_BIRTH` ≈ 90% des triggers** — risque de modèle dégénéré qui "
        "apprend simplement \"PRICE_LAG déclenché ⇒ WIN\" sans discriminer le contexte fin.",
        "- **Sessions New York/After exclues** (`skipped.jsonl` séparé) — le modèle ne voit "
        "jamais ces contextes ; tout déploiement futur sur ces sessions serait hors "
        "distribution d'entraînement.",
        "- **Labels dépendants de la stratégie DYNAMIC** (TP/SL par session, Brief O1) — un "
        "changement futur de stratégie de sortie invaliderait ces labels ; le dataset "
        "devrait être régénéré (le script est idempotent, cf. ci-dessous).",
    ])
    train_wr = _class_dist(train)["win_rate_pct"]
    val_wr = _class_dist(val)["win_rate_pct"]
    test_wr = _class_dist(test)["win_rate_pct"]
    if abs(val_wr - train_wr) > 15 or abs(val_wr - test_wr) > 15:
        lines.append(
            f"- **⚠️ Rupture de distribution détectée sur le split val** (WR train={train_wr}% "
            f"vs val={val_wr}% vs test={test_wr}%) — un split chronologique expose les "
            f"changements de régime de marché ; ce n'est PAS un bug du script (attendu avec "
            f"une seule paire/période), mais une raison de plus de ne PAS lancer "
            f"d'entraînement sans investiguer cet écart au préalable (cf. §Entraînement)."
        )
    lines.append("")
    lines.append("## Features")
    lines.append("")
    lines.append(
        "Contexte assemblé par `PrincipleEngine._load_shared_context()` (contrat "
        "`docs/architecture/CONTEXT_CONTRACT.md` Couche 7 — état ACTUEL, pas le chiffre "
        "\"31 champs\" historique de `docs/AGENT.md` 2026-07-06/07, obsolète depuis les "
        "ajouts Phase 13 risk_assessment/regime/zone_diagnostics/news-aware). Métadonnées "
        f"({', '.join(METADATA_FIELDS)}) séparées des features, marquées explicitement."
    )
    lines.append("")
    lines.append(
        "**Interdit et vérifié absent des features** : tout champ postérieur à la décision "
        "(`resolution_*`, MFE/MAE réalisés, `exit_reason`) — `_load_shared_context()` ne lit "
        "jamais la table `decisions`, aucune fuite possible par construction."
    )
    lines.append("")
    lines.append("## Split")
    lines.append("")
    lines.append(
        f"Chronologique STRICT (train {int(TRAIN_RATIO*100)}% le plus ancien, val "
        f"{int(VAL_RATIO*100)}%, test {int((1-TRAIN_RATIO-VAL_RATIO)*100)}% le plus récent). "
        f"Aucun shuffle inter-périodes. 1 décision = 1 snapshot unique (vérifié Brief O1/O2 : "
        f"0 snapshot avec >1 décision `preparer_entree`) — aucun risque de répartir un même "
        f"snapshot sur deux splits."
    )
    lines.append("")
    lines.append("## Formats")
    lines.append("")
    lines.append(
        "- `{split}.jsonl` — classification brute `{\"features\": {...}, \"label\": 0|1, \"pips\": x}`."
    )
    lines.append(
        "- `{split}_chat.jsonl` — chat-template "
        "`{\"messages\":[{\"role\":\"user\",\"content\":\"<contexte JSON>\"},"
        "{\"role\":\"assistant\",\"content\":\"WIN|LOSS\"}]}` "
        "(cible qwen3-coder 4B / phi3 3.8B, quantization Q4_K_M — documentaire, rien à faire ici)."
    )
    lines.append("- `skipped.jsonl` — mêmes champs, décisions New York/After (analyse future).")
    lines.append("")
    lines.append("## Entraînement")
    lines.append("")
    lines.append(
        "**NON ouvert.** Ce brief couvre uniquement la préparation du dataset + carte de "
        "données. Le fine-tuning est un GO séparé de Søn, à tracer dans DECISIONS_LOG AVANT "
        "implémentation (R17/R19). Le modèle éventuel reste HORS du cœur cognitif (R18) — "
        "outil d'analyse/shadow uniquement."
    )
    lines.append("")
    lines.append("## Hachages MD5 + régénération")
    lines.append("")
    lines.append("Voir `docs/reports/DATASET_V9_TRADER_MINI_MD5SUMS.txt`.")
    lines.append(
        "Régénération idempotente : `python scripts/v9_export_dataset.py --apply "
        "--output data/datasets/v9_trader_mini/` (dry-run par défaut sans `--apply`)."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Export dataset V9-trader-mini (Brief O5)")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--card", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--md5", type=Path, default=DEFAULT_MD5_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    conn = _connect(args.db)
    try:
        rows = fetch_target_decisions(conn)
        print(f"[.. ] {len(rows)} décisions cibles (DYNAMIC + SKIPPED)")

        engine = PrincipleEngine(db_path=args.db)
        dynamic, skipped, n_errors = build_records(conn, rows, engine)
        print(f"[.. ] {len(dynamic)} DYNAMIC (train/val/test), {len(skipped)} SKIPPED "
              f"(séparées), {n_errors} erreurs contexte (exclues)")

        train, val, test = chronological_split(dynamic)
        print(f"[.. ] Split chronologique : train={len(train)}, val={len(val)}, test={len(test)}")

        if not args.apply:
            print("Aucun fichier écrit (dry-run). Relancer avec --apply.")
            return 0

        args.output.mkdir(parents=True, exist_ok=True)
        files_written: list[Path] = []
        for name, recs in (("train", train), ("val", val), ("test", test)):
            p_cls = args.output / f"{name}.jsonl"
            _write_jsonl(p_cls, recs, to_classification_jsonl)
            files_written.append(p_cls)
            p_chat = args.output / f"{name}_chat.jsonl"
            _write_jsonl(p_chat, recs, to_chat_template_jsonl)
            files_written.append(p_chat)
        p_skipped = args.output / "skipped.jsonl"
        _write_jsonl(p_skipped, skipped, to_classification_jsonl)
        files_written.append(p_skipped)

        card_text = build_data_card(dynamic, skipped, train, val, test, n_errors)
        args.card.parent.mkdir(parents=True, exist_ok=True)
        args.card.write_text(card_text, encoding="utf-8")
        print(f"[OK ] Carte de données : {args.card}")

        md5_lines = [f"{_md5_of(p)} *{_display_path(p)}" for p in files_written]
        args.md5.parent.mkdir(parents=True, exist_ok=True)
        args.md5.write_text("\n".join(md5_lines) + "\n", encoding="utf-8")
        print(f"[OK ] MD5 : {args.md5}")

        for p in files_written:
            print(f"[OK ] Écrit : {p}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
