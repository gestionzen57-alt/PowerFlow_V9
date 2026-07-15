#!/usr/bin/env python3
"""mcp-v9-filesystem — MCP server ciblé pour accès scope C:\\projet\\V9\\.

Tools exposés (stdin/stdout JSON-RPC simplifié, transport subprocess Hermes) :
- read_file(path: str) → str
- write_file(path: str, content: str) → bool
- list_dir(path: str) → list[str]
- search_files(pattern: str, path: str) → list[str]

Sécurité : path absolu obligatoire, scope = ROOT_DIR (rejette tout ../).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9").resolve()


def _resolve_safe(rel_path: str) -> Path | None:
    """Résout un chemin relatif en absolu, garantit qu'il reste sous ROOT_DIR."""
    if not rel_path or rel_path.startswith(("/", "\\")):
        return None
    target = (ROOT_DIR / rel_path).resolve()
    try:
        target.relative_to(ROOT_DIR)
        return target
    except ValueError:
        return None


def handle_read_file(args: dict) -> dict:
    rel = args.get("path", "")
    p = _resolve_safe(rel)
    if not p:
        return {"error": f"path unsafe ou hors scope: {rel}"}
    if not p.exists():
        return {"error": f"file not found: {rel}"}
    if p.is_dir():
        return {"error": f"is a directory: {rel}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > 100_000:
            content = content[:100_000] + "\n... (tronqué à 100KB)"
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}


def handle_write_file(args: dict) -> dict:
    rel = args.get("path", "")
    content = args.get("content", "")
    p = _resolve_safe(rel)
    if not p:
        return {"error": f"path unsafe ou hors scope: {rel}"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"written": True, "path": rel, "bytes": len(content)}
    except Exception as e:
        return {"error": str(e)}


def handle_list_dir(args: dict) -> dict:
    rel = args.get("path", ".")
    p = _resolve_safe(rel)
    if not p:
        return {"error": f"path unsafe ou hors scope: {rel}"}
    if not p.is_dir():
        return {"error": f"not a directory: {rel}"}
    try:
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
        return {"entries": entries[:200], "truncated": len(entries) > 200}
    except Exception as e:
        return {"error": str(e)}


def handle_search_files(args: dict) -> dict:
    pattern = args.get("pattern", "")
    rel = args.get("path", ".")
    p = _resolve_safe(rel)
    if not p or not pattern:
        return {"error": "pattern ou path manquant"}
    try:
        regex = re.compile(pattern)
        matches = []
        for f in p.rglob("*"):
            if f.is_file() and regex.search(f.name):
                matches.append(str(f.relative_to(ROOT_DIR)))
                if len(matches) >= 100:
                    break
        return {"matches": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


HANDLERS = {
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "list_dir": handle_list_dir,
    "search_files": handle_search_files,
}


def main() -> None:
    """Boucle MCP standard + protocole legacy Hermes sur stdin/stdout."""
    from stdio_runtime import serve

    serve(HANDLERS, "v9-filesystem")


if __name__ == "__main__":
    main()