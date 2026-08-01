#!/usr/bin/env python3
"""v9_audit_skills — Audit skills workspace vs HEAD courant.

Sortie :
- Liste skills (workspace .zcode/skills/) avec derniere_maj + statut
- Alerte skills > 14j sans maj (rappel)
- Alerte skills legacy-v8 (doivent être re-taguées)
- Comparaison compteurs avec HEAD courant (git rev-parse)

Usage :
    python scripts/v9_audit_skills.py              # rapport complet
    python scripts/v9_audit_skills.py --stale 14   # seuil jours
    python scripts/v9_audit_skills.py --json       # sortie JSON

R8 — la doc maintenance des skills reste la source de vérité.
Ajouté 2026-07-31 (Resync MCP+skills motion CEO).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?)\n---\s*\n",
    re.DOTALL | re.MULTILINE,
)
STATUT_RE = re.compile(r"^statut:\s*(?P<v>.*?)\s*$", re.MULTILINE)
DATE_RE = re.compile(r"^derniere_maj:\s*(?P<v>\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
NAME_RE = re.compile(r"^name:\s*(?P<v>.*?)\s*$", re.MULTILINE)


def _g(pattern: re.Pattern, text: str, default: str = "") -> str:
    m = pattern.search(text)
    return m.group("v") if m else default


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.search(text)
    if not m:
        return {}
    fm = m.group("fm")
    return {
        "name": _g(NAME_RE, fm),
        "statut": _g(STATUT_RE, fm),
        "derniere_maj": _g(DATE_RE, fm),
    }


def list_skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.rglob("SKILL.md"))


def head_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT
        ).decode().strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit skills workspace V9")
    parser.add_argument("--stale", type=int, default=14, help="Seuil jours (défaut 14)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    head = head_short()
    today = date.today()

    rows = []
    for f in list_skill_files():
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm.get("name"):
            # Skip fichiers sans frontmatter (ex: computer-use, yuanbao, system)
            if "trading" not in str(f) and "skills/computer-use" not in str(f):
                continue
        try:
            d = datetime.strptime(fm["derniere_maj"], "%Y-%m-%d").date() if fm.get("derniere_maj") else None
        except ValueError:
            d = None
        age_days = (today - d).days if d else None
        rows.append({
            "path": str(f.relative_to(ROOT)),
            "name": fm.get("name", ""),
            "statut": fm.get("statut", ""),
            "derniere_maj": fm.get("derniere_maj", ""),
            "age_days": age_days,
        })

    # Stats
    n_total = len(rows)
    n_actif_v9 = sum(1 for r in rows if "actif-v9" in r["statut"] or r["statut"] == "actif")
    n_legacy_v8 = sum(1 for r in rows if r["statut"] == "legacy-v8")
    n_legacy_historique = sum(1 for r in rows if "legacy-historique" in r["statut"])
    n_active = sum(1 for r in rows if r["statut"] in ("actif", "actif-v9", "ACTIVE"))
    n_stale = sum(1 for r in rows if r["age_days"] is not None and r["age_days"] >= args.stale)
    n_no_date = sum(1 for r in rows if r["age_days"] is None)

    if args.json:
        out = {
            "head": head,
            "audit_date": today.isoformat(),
            "stale_threshold_days": args.stale,
            "n_total": n_total,
            "n_active": n_active,
            "n_actif_v9": n_actif_v9,
            "n_legacy_v8": n_legacy_v8,
            "n_legacy_historique": n_legacy_historique,
            "n_stale": n_stale,
            "n_no_date": n_no_date,
            "skills": rows,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print(f"=== V9 Skills Audit — HEAD {head} — {today.isoformat()} ===")
    print(f"Seuil stale : {args.stale} jours")
    print()
    print(f"Total skills : {n_total}")
    print(f"  Actives    : {n_active} (actif/actif-v9/ACTIVE)")
    print(f"  Legacy-v8  : {n_legacy_v8} (à re-taguer)")
    print(f"  Legacy hist: {n_legacy_historique}")
    print(f"  Stale >{args.stale}j : {n_stale}")
    print(f"  Sans date  : {n_no_date}")
    print()
    if n_legacy_v8:
        print(f"⚠️  {n_legacy_v8} skills marquées legacy-v8 (re-tagage requis) :")
        for r in rows:
            if r["statut"] == "legacy-v8":
                print(f"  - {r['path']} ({r['name']})")
        print()
    if n_stale:
        print(f"⚠️  {n_stale} skills stale > {args.stale}j :")
        for r in rows:
            if r["age_days"] is not None and r["age_days"] > args.stale:
                print(f"  - {r['path']} ({r['name']}, {r['age_days']}j)")
        print()
    if n_no_date:
        print(f"⚠️  {n_no_date} skills sans derniere_maj :")
        for r in rows:
            if r["age_days"] is None and r["name"]:
                print(f"  - {r['path']} ({r['name']})")
        print()
    return 0 if (n_legacy_v8 == 0 and n_stale == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
