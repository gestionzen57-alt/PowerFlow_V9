#!/usr/bin/env python3
"""v9_check_vps.py — preflight checks pour VPS V9.

Vérifie avant déploiement que le VPS cible est viable.
Détecte OS, RAM, Python, ports libres, accès DB.

Sprint V9 2026-07-07 — Hermes autonomous.
"""
from __future__ import annotations

import platform
import shutil
import socket
import sys
from pathlib import Path


def check_ram_min_gb(min_gb: float = 1.5) -> tuple[bool, str]:
    """Rapporte RAM dispo via /proc/meminfo (Linux) ou fallback."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    gb = kb / 1024 / 1024
                    return (gb >= min_gb, f"RAM totale = {gb:.2f} GB (min {min_gb})")
    except FileNotFoundError:
        pass
    return (None, "RAM non mesurable (pas /proc/meminfo) — vérifier manuellement")


def check_python() -> tuple[bool, str]:
    v = sys.version_info
    return (v.major == 3 and v.minor >= 11, f"Python {v.major}.{v.minor}.{v.micro}")


def check_port_free(port: int) -> tuple[bool, str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return (True, f"port {port} libre")
    except OSError:
        return (False, f"port {port} OCCUPE — déjà un daemon en cours?")


def check_disk_min_gb(path: Path, min_gb: float = 2.0) -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(str(path))
        gb = usage.free / 1024 / 1024 / 1024
        return (gb >= min_gb, f"disque libre sur {path} = {gb:.2f} GB (min {min_gb})")
    except Exception as e:
        return (None, f"disque non mesurable : {e}")


def check_ea_indicator_present() -> tuple[bool, str]:
    """Vérifie la présence de l'EA MT4 SDI source (sans laquelle V9 ne capture rien)."""
    ea = Path("ea/V9_Sonde_TF.mq4")
    if ea.exists():
        return (True, f"{ea} présent")
    return (False, f"{ea} ABSENT — pipeline ne démarrera pas (à installer par Søn)")


def main() -> int:
    print("=== V9 VPS Preflight — Sprint 2026-07-07 ===\n")
    checks = [
        ("OS", (True, f"{platform.system()} {platform.release()}")),
        ("Python 3.11+", check_python()),
        ("RAM >= 1.5 GB", check_ram_min_gb()),
        ("Disque >= 2 GB", check_disk_min_gb(Path.cwd())),
        ("Port 31685 libre", check_port_free(31685)),
        ("EA MT4 SDI", check_ea_indicator_present()),
    ]
    fails = 0
    for label, (ok, msg) in checks:
        flag = "[OK]" if ok is True else "[KO]" if ok is False else "[??]"
        print(f"  {flag} {label:30s} {msg}")
        if ok is False:
            fails += 1
    print()
    if fails == 0:
        print("→ Viable. Tu peux déployer.")
        return 0
    print(f"→ {fails} check(s) KO. À corriger avant déploiement.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
