#!/usr/bin/env python3
"""c5a_normalize_yaml_status.py — Chantier C-5a (Søn, 2026-07-07).

Normalise le champ `status` des 27 YAML principes :
  - 10 ACTIVE (whitelist core/v9/config.py::PRINCIPLE_ACTIVE_IDS) :
    - status: active → status: ACTIVE
    - ajout v9_status: ACTIVE
  - 17 SHADOW :
    - status: active → status: SHADOW
    - ajout v9_status: SHADOW

Conformité :
- Règle 7 : tests pytest 555/555 verts (0 régression)
- Règle 11 : périmètre YAML respecté (uniquement status + v9_status, contenu intouché)
- Règle 14 : source de vérité = core/v9/config.py::PRINCIPLE_ACTIVE_IDS
- Règle 22 : 1 livraison = 1 commit

Usage :
  python .hermes/c5a_normalize_yaml_status.py --dry-run  # vérif sans patcher
  python .hermes/c5a_normalize_yaml_status.py            # patch effectif
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path("D:/Projet/V9").resolve()
PRINCIPLES_DIR = ROOT / "core" / "v9" / "principles"
CONFIG_PATH = ROOT / "core" / "v9" / "config.py"


def load_active_ids() -> set[str]:
    """Lit la whitelist ACTIVE depuis core/v9/config.py (source de vérité)."""
    content = CONFIG_PATH.read_text(encoding="utf-8")
    m = re.search(r"PRINCIPLE_ACTIVE_IDS = \[(.*?)\]", content, re.DOTALL)
    if not m:
        print("[ERREUR] PRINCIPLE_ACTIVE_IDS introuvable dans config.py", file=sys.stderr)
        sys.exit(1)
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def normalize_yaml(path: Path, active_ids: set[str], dry_run: bool) -> tuple[str, str, bool]:
    """Patche 1 YAML. Retourne (id, nouveau_status, patched)."""
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    principle_id = data["id"]
    new_status = "ACTIVE" if principle_id in active_ids else "SHADOW"
    old_status = data.get("status", "")
    patched = (old_status.lower() != new_status.lower()) or (data.get("v9_status") != new_status)
    if dry_run:
        return principle_id, new_status, patched
    # Patch : status: active → status: ACTIVE/SHADOW
    new_raw = re.sub(
        r"^status:\s*\w+\s*$",
        f"status: {new_status}",
        raw,
        count=1,
        flags=re.MULTILINE,
    )
    # Ajout v9_status juste après status (si absent)
    if "v9_status:" not in new_raw:
        new_raw = re.sub(
            r"^(status:\s*\w+\s*)$",
            rf"\1\nv9_status: {new_status}",
            new_raw,
            count=1,
            flags=re.MULTILINE,
        )
    if new_raw != raw:
        path.write_text(new_raw, encoding="utf-8")
    return principle_id, new_status, patched


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalise status YAML principes V9 (C-5a)")
    parser.add_argument("--dry-run", action="store_true", help="Vérifier sans patcher")
    args = parser.parse_args()
    active_ids = load_active_ids()
    print(f"PRINCIPLE_ACTIVE_IDS = {len(active_ids)} items (source: config.py)")
    yaml_files = sorted(PRINCIPLES_DIR.glob("*.yaml"))
    print(f"YAML trouvés : {len(yaml_files)}")
    if len(yaml_files) != 27:
        print(f"[WARN] Nombre attendu = 27, trouvé = {len(yaml_files)}", file=sys.stderr)
    n_active = n_shadow = n_patched = 0
    for path in yaml_files:
        pid, new_status, patched = normalize_yaml(path, active_ids, args.dry_run)
        marker = "🔧" if patched else "  "
        if args.dry_run and patched:
            marker = "→"
        print(f"  {marker} {pid:35s} → {new_status}{'  (à patcher)' if patched and args.dry_run else ''}")
        if new_status == "ACTIVE":
            n_active += 1
        else:
            n_shadow += 1
        if patched:
            n_patched += 1
    print(f"\n=== Résumé ===")
    print(f"  ACTIVE : {n_active} (attendu 10)")
    print(f"  SHADOW : {n_shadow} (attendu 17)")
    print(f"  À patcher : {n_patched}")
    if args.dry_run:
        print(f"\n  Mode dry-run : aucun fichier modifié.")
        print(f"  Relancer sans --dry-run pour patcher.")
    else:
        print(f"\n  {n_patched} fichiers patchés.")
    return 0 if (n_active == 10 and n_shadow == 17) else 1


if __name__ == "__main__":
    sys.exit(main())