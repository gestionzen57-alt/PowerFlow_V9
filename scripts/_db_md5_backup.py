#!/usr/bin/env python3
"""Create an MD5 manifest for a database before/after a destructive audit step."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/_db_md5_backup.py <output-dir>")
        return 2
    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(__file__).resolve().parent.parent / "data" / "v9_forces.db"
    manifest = output_dir / "MD5SUMS.txt"
    try:
        before = md5_file(db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE opened_at >= ? AND opened_at < ? "
                "AND snapshot_id LIKE ?",
                ("2026-07-17T15:00:00", "2026-07-17T20:00:00", "v9-GBPUSD-%"),
            ).fetchone()[0]
        finally:
            conn.close()
        manifest.write_text(
            "# V9 paper_trades batch MD5 audit\n"
            f"# generated_utc={datetime.now(timezone.utc).isoformat()}\n"
            f"# db={db_path}\n"
            f"# target_count={count}\n"
            f"{before} *{db_path.as_posix()}\n",
            encoding="utf-8",
        )
        print(f"MD5={before} target_count={count} manifest={manifest}")
        return 0
    except Exception as exc:
        print(f"MD5 backup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
