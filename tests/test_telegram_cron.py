"""Tests minimaux pour les wrappers Telegram notifier.

Vérifie que les scripts sont :
- Présents dans scripts/
- Contiennent les paths/commandes critiques
- Référencent le bon script Python + bons logs

Ne teste PAS l'exécution réelle (nécessite Windows + admin).

Mis à jour 2026-07-14 (audit ZCode) : install_telegram_cron.bat supprimé
(chemin D:\ obsolète, doublon de install_v9_telegram_cron.ps1). Tests
d'installation adaptés pour vérifier le .ps1 qui le remplace.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8", errors="replace")


# ── start_telegram_notifier.bat (wrapper watchdog) ────────────────

def test_start_bat_present() -> None:
    assert (SCRIPTS / "start_telegram_notifier.bat").exists()


def test_start_bat_uses_pythonw() -> None:
    """pythonw.exe = mode silencieux Windows (pas de fenêtre qui flashe)."""
    content = _read("start_telegram_notifier.bat")
    assert "pythonw.exe" in content, "doit utiliser pythonw.exe (silencieux)"
    assert "python.exe" not in content or content.count("python.exe") == 0 or \
        "PYTHONW_EXE" in content  # pas de python.exe brut, juste la var


def test_start_bat_references_correct_script() -> None:
    """Le wrapper doit pointer vers scripts/v9_telegram_notifier.py."""
    content = _read("start_telegram_notifier.bat")
    assert "v9_telegram_notifier.py" in content
    assert "--watch" in content


def test_start_bat_has_watchdog_loop() -> None:
    """Boucle watchdog (redémarrage si crash) — pattern 'always-on minimal'."""
    content = _read("start_telegram_notifier.bat")
    assert ":loop" in content, "label :loop manquant"
    assert "goto loop" in content, "saut vers :loop manquant"
    assert "timeout" in content, "délai entre redémarrages manquant"


def test_start_bat_logs_to_correct_dir() -> None:
    """Les 2 logs vont dans logs/."""
    content = _read("start_telegram_notifier.bat")
    assert "logs\\telegram_notifier.log" in content
    assert "logs\\telegram_watchdog.log" in content


def test_start_bat_pythonw_path_is_placeholder() -> None:
    """Le path pythonw.exe doit être un placeholder éditable (pas codé en dur
    dans le repo de l'opérateur)."""
    content = _read("start_telegram_notifier.bat")
    assert "PYTHONW_EXE=" in content
    # Vérifie qu'on n'a PAS mis un path user-spécifique en dur
    assert "C:\\Users\\" not in content, \
        "ne pas hardcoder un path user-spécifique"


# ── install_v9_telegram_cron.ps1 (installateur PowerShell) ────────
# Remplace install_telegram_cron.bat (supprimé 2026-07-14, chemin D:\ obsolète).

def test_install_ps1_present() -> None:
    assert (SCRIPTS / "install_v9_telegram_cron.ps1").exists()


def test_install_ps1_uses_schtasks() -> None:
    """L'installateur crée la tâche via schtasks /create."""
    content = _read("install_v9_telegram_cron.ps1")
    assert "schtasks /create" in content or "schtasks" in content
    assert "V9_TelegramAgent" in content


def test_install_ps1_references_notifier_script() -> None:
    """L'installateur pointe vers v9_telegram_notifier.py --watch."""
    content = _read("install_v9_telegram_cron.ps1")
    assert "v9_telegram_notifier.py" in content
    assert "--watch" in content


def test_install_ps1_has_uninstall_hint() -> None:
    """L'installateur affiche ou documente la commande de désinstallation."""
    content = _read("install_v9_telegram_cron.ps1")
    assert "schtasks /delete" in content or "delete" in content.lower()


def test_consistency_task_name() -> None:
    """Le nom de tâche doit être cohérent dans l'installateur .ps1."""
    installer = _read("install_v9_telegram_cron.ps1")
    assert "V9_TelegramAgent" in installer