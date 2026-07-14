"""generate_adaptive_principles.py — Génère les variantes _ADAPTIVE.yaml
des principes V9 (P3-CONSUME-EXTEND, 2026-07-14, Hermes).

Pour chaque principe source listé dans PRINCIPLES_SOURCES, génère un
nouveau fichier `<ORIG>_ADAPTIVE.yaml` dans core/v9/principles/, qui :
- copie id, version, scope (timeframes/currencies), emits, bounds, notes
  du source ;
- statut forcé à SHADOW + v9_status=SHADOW (R25' : pas de promotion
  sans motion CEO distincte) ;
- origin = "V9-P3-CONSUME-EXTEND" pour tracer la filiation ;
- ajoute 3 conditions de garde (adaptive_coalition_threshold,
  adaptive_antagonism_threshold, adaptive_pliure_threshold is_not_null)
  en tête des conditions, avant les conditions originales, pour
  assurer la dégradation gracieuse R6 si P3-WIRE est OFF.

Doctrine respectée :
- R8  : nouveau fichier, pas de modif d'un existant, pas de backup
        MD5 requis (convention ADAPTIVE_VOL_GATE).
- R18 : zéro LLM, zéro réseau.
- R22 : 1 commit par groupe (node_rule / birth / grammar).
- R25' : SHADOW par défaut, promotion = motion CEO distincte.
- R26 : tests pytest à valider (test_p3_consume_extend.py).

Idempotent : relance-safe, écrase la version _ADAPTIVE.yaml précédente.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRINCIPLES_DIR = ROOT / "core" / "v9" / "principles"

# Groupes P3-CONSUME-EXTEND (mêmes timeframes que les sources).
# Format : (source_filename, adaptive_strategy) — la stratégie dit
# quels champs adaptatifs sont consommés et comment.
# Stratégies :
#   "coalition" : adaptive_coalition_threshold (gate fort)
#   "antagonism" : adaptive_antagonism_threshold (gate fort)
#   "pliure" : adaptive_pliure_threshold (gate fort)
#   "all" : les 3 gates combinés (volatilité globale)

GROUP_NODE_RULE = [
    ("COALITION_NODE.yaml", "coalition"),
    ("ANTAGONIST_NODE.yaml", "antagonism"),
    ("ZONE_RETEST.yaml", "antagonism"),
    ("ELASTIC_BREATH.yaml", "antagonism"),
    ("GRAVITY_RESPRING_NODE.yaml", "coalition"),
]

GROUP_BIRTH_BREAK = [
    ("POWER_ANGLE_BREAK_TO_PRICE_IMPACT.yaml", "pliure"),
    ("NODE_BIRTH_FAST.yaml", "pliure"),
    ("RAW_NODE_BIRTH.yaml", "pliure"),
    ("PRICE_LAG_AT_NODE_BIRTH.yaml", "pliure"),
]

GROUP_GRAMMAR = [
    ("GRAMMAR_ABSORPTION.yaml", "all"),
    ("GRAMMAR_ANTAGONISME.yaml", "antagonism"),
    ("GRAMMAR_BREAK.yaml", "pliure"),
    ("GRAMMAR_COALITION.yaml", "coalition"),
    ("GRAMMAR_CONTEXTE.yaml", "all"),
    ("GRAMMAR_CROISEMENT.yaml", "all"),
    ("GRAMMAR_EXHAUSTION.yaml", "antagonism"),
    ("GRAMMAR_EXTENSION.yaml", "pliure"),
    ("GRAMMAR_LEADER_FOLLOWER.yaml", "coalition"),
    ("GRAMMAR_LOCK.yaml", "antagonism"),
    ("GRAMMAR_OPPOSITION.yaml", "antagonism"),
    ("GRAMMAR_PULLBACK.yaml", "pliure"),
    ("GRAMMAR_REGIME.yaml", "all"),
    ("GRAMMAR_RESPIRATION.yaml", "all"),
    ("GRAMMAR_SQUEEZE.yaml", "pliure"),
    ("GRAMMAR_TENSION.yaml", "antagonism"),
    ("SIGNAL_OPEN.yaml", "all"),
]

# Champs adaptatifs consommés par stratégie (sous-ensemble des 3 dispos).
STRATEGY_FIELDS = {
    "coalition": ["adaptive_coalition_threshold"],
    "antagonism": ["adaptive_antagonism_threshold"],
    "pliure": ["adaptive_pliure_threshold"],
    "all": [
        "adaptive_coalition_threshold",
        "adaptive_antagonism_threshold",
        "adaptive_pliure_threshold",
    ],
}


def _build_adaptive_guards(strategy: str) -> list[dict]:
    """Construit les conditions de garde 'is_not_null' en tête,
    une par champ adaptatif consommé. R6 dégradation gracieuse : si
    P3-WIRE OFF, les champs sont absents du context → None → ces
    conditions false → le principe ne déclenche pas."""
    return [
        {"field": f, "op": "is_not_null", "value": True}
        for f in STRATEGY_FIELDS[strategy]
    ]


def _build_adaptive_principle(src: dict, strategy: str) -> dict:
    """Construit le dict YAML du principe _ADAPTIVE à partir du source.
    Force status=SHADOW, injecte guards en tête, conserve scope/emits/
    bounds/notes. Conserve la traçabilité via notes."""
    new = {
        "id": f"{src['id']}_ADAPTIVE",
        "version": 1,
        "origin": "V9-P3-CONSUME-EXTEND",
        "status": "SHADOW",
        "v9_status": "SHADOW",
        "kind": src.get("kind", "node_rule"),
        "created_by": "hermes_v9",
        "created_at": "2026-07-14",
        "promoted_at": None,
        "scope": dict(src.get("scope", {})),
        "conditions": _build_adaptive_guards(strategy) + list(
            src.get("conditions", [])
        ),
        "emits": dict(src.get("emits", {})),
        "bounds": dict(src.get("bounds", {})),
        "anti_signal_bias": src.get("anti_signal_bias", False),
        "notes": (
            f"P3-CONSUME-EXTEND (2026-07-14) — variante _ADAPTIVE du principe "
            f"{src['id']} (origin={src.get('origin','?')}). "
            f"Stratégie : {strategy}. Consomme les seuils adaptatifs posés par "
            f"P3-WIRE ({', '.join(STRATEGY_FIELDS[strategy])}) via 3 conditions "
            f"de garde 'is_not_null' en tête. Dégradation gracieuse R6 : si "
            f"P3-WIRE est OFF (kill switch V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=0), "
            f"les champs adaptatifs sont absents du context, les gardes sont "
            f"false, le principe ne déclenche pas. SHADOW par défaut (R25'), "
            f"promotion ACTIVE = motion CEO distincte + DECISIONS_LOG.\n\n"
            f"Source originale : {src.get('notes','').strip()}"
        ).strip(),
    }
    return new


def _generate_one(src_filename: str, strategy: str) -> Path:
    """Génère un _ADAPTIVE.yaml à partir d'un source. Retourne le path
    du fichier généré. Skip si source absent (fail-fast)."""
    src_path = PRINCIPLES_DIR / src_filename
    if not src_path.exists():
        raise FileNotFoundError(f"source principle absent : {src_path}")
    with src_path.open("r", encoding="utf-8") as f:
        src = yaml.safe_load(f)
    if not isinstance(src, dict) or "id" not in src:
        raise ValueError(f"source YAML invalide : {src_path}")
    new = _build_adaptive_principle(src, strategy)
    dst_filename = f"{src['id']}_ADAPTIVE.yaml"
    dst_path = PRINCIPLES_DIR / dst_filename
    with dst_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(new, f, allow_unicode=True, sort_keys=False, width=100)
    return dst_path


def _generate_group(group: list[tuple[str, str]], label: str) -> list[Path]:
    """Génère un groupe complet. Affiche progression."""
    print(f"[{label}] génération de {len(group)} principes _ADAPTIVE...")
    out = []
    for src_filename, strategy in group:
        try:
            p = _generate_one(src_filename, strategy)
            print(f"  ✓ {p.name} (stratégie={strategy})")
            out.append(p)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ✗ {src_filename} : {e}")
            raise
    return out


def main() -> int:
    """Génère les 3 groupes. Args CLI : 'all' (défaut), 'node', 'birth', 'grammar'."""
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    groups = []
    if arg in ("all", "node"):
        groups.append((GROUP_NODE_RULE, "node_rule"))
    if arg in ("all", "birth"):
        groups.append((GROUP_BIRTH_BREAK, "birth_break"))
    if arg in ("all", "grammar"):
        groups.append((GROUP_GRAMMAR, "grammar"))
    if not groups:
        print(f"argument inconnu: {arg!r} (attendu: all|node|birth|grammar)")
        return 2
    total = 0
    for group, label in groups:
        out = _generate_group(group, label)
        total += len(out)
    print(f"\n[OK] {total} principes _ADAPTIVE générés dans {PRINCIPLES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
