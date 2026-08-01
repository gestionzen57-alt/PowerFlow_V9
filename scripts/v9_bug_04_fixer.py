"""v9_bug_04_fixer.py — Phase 102 motion CEO 48H (post-audit v2 Perplexity).

Fix dedie BUG-04 : indentation pathologique DD protector section 3a5.
v2 : cherche le try: a 28 espaces et le dedente a 16.

Auteur : Hermes (Phase 102 motion CEO 48H non-stop, 01/08/2026)
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

log = logging.getLogger("v9.bug_04_fixer")

TRADE_ENGINE_PATH = Path("core/v9/trade_engine.py")


def fix_dd_protector_indentation_v2(content: str) -> tuple[str, int]:
    """Fix BUG-04 v2 : dedente le bloc try: du DD protector.

    Le bloc try: devrait etre a 16 espaces (apres 'if (:)' au niveau 12).
    On dedente tout ce qui est > 16 espaces jusqu'a la prochaine ligne
    au niveau <= 16.
    """
    # Trouver le marqueur de debut
    start_marker = 'result["drawdown_protector"] = None'
    if start_marker not in content:
        return content, 0
    start_idx = content.find(start_marker)
    line_start = content.rfind("\n", 0, start_idx) + 1
    # Trouver end : prochain statement au niveau <= 16 (apres les 12 de base)
    end_marker = "# 3a6."
    end_idx = content.find(end_marker, start_idx)
    if end_idx < 0:
        return content, 0
    end_line_start = content.rfind("\n", 0, end_idx) + 1
    # Extraire le bloc
    block = content[line_start:end_line_start]
    lines = block.split("\n")
    # Trouver toutes les lignes > 16 espaces d'indentation (pathologiques)
    pathological = [i for i, line in enumerate(lines)
                    if line.strip() and len(line) - len(line.lstrip()) > 16]
    if not pathological:
        return content, 0
    # Trouver le niveau de base du bloc try:
    # Si try: est a 28, dedente a 16 (-12)
    # Si try: est a 24, dedente a 16 (-8)
    try_lines = [i for i, line in enumerate(lines)
                 if line.strip().startswith("try:")]
    if not try_lines:
        return content, 0
    first_try = try_lines[0]
    try_indent = len(lines[first_try]) - len(lines[first_try].lstrip())
    target_indent = 16
    delta = try_indent - target_indent
    if delta <= 0:
        return content, 0
    # Appliquer le delta a toutes les lignes pathologiques
    new_lines = []
    fixed_count = 0
    for i, line in enumerate(lines):
        if i in pathological:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            new_indent = current_indent - delta
            new_line = " " * new_indent + stripped
            new_lines.append(new_line)
            fixed_count += 1
        else:
            new_lines.append(line)
    new_block = "\n".join(new_lines)
    new_content = content[:line_start] + new_block + content[end_line_start:]
    return new_content, fixed_count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="V9 BUG-04 fixer v2")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    print("=" * 70)
    print("V9 BUG-04 FIXER v2 (Phase 102)")
    print("=" * 70)
    content = TRADE_ENGINE_PATH.read_text(encoding="utf-8")
    new_content, fixed = fix_dd_protector_indentation_v2(content)
    print(f"Lines fixed : {fixed}")
    if fixed > 0:
        if args.apply:
            TRADE_ENGINE_PATH.write_text(new_content, encoding="utf-8")
            print(f"Written : {TRADE_ENGINE_PATH}")
        else:
            print("Dry-run : use --apply to write")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())