"""Tests minimaux pour les wrappers .bat Telegram notifier.

Vérifie que les .bat sont :
- Présents dans scripts/
- Contiennent les paths/commandes critiques (sans casser Windows)
- Référencent le bon script Python + bons logs

Ne teste PAS l'exécution réelle du .bat (nécessite Windows + admin).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8", errors="replace")


def test_start_bat_present() -> None:
    assert (SCRIPTS / "start_telegram_notifier.bat").exists()


def test_install_bat_present() -> None:
    assert (SCRIPTS / "install_telegram_cron.bat").exists()


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
    """Les 2 logs vont dans D:/Projet/V9/logs/."""
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


def test_install_bat_uses_schtasks() -> None:
    """L'installateur crée la tâche via schtasks /create."""
    content = _read("install_telegram_cron.bat")
    assert "schtasks /create" in content
    assert "/tn" in content
    assert "/tr" in content
    assert "/sc onlogon" in content
    assert "/rl highest" in content


def test_install_bat_checks_admin() -> None:
    """L'installateur refuse de tourner sans privilèges admin."""
    content = _read("install_telegram_cron.bat")
    assert "net session" in content, "doit vérifier les privilèges admin"
    assert "administrateur" in content.lower()


def test_install_bat_references_wrapper() -> None:
    """L'installateur pointe vers le wrapper start_telegram_notifier.bat."""
    content = _read("install_telegram_cron.bat")
    assert "start_telegram_notifier.bat" in content
    assert "V9_TelegramNotifier" in content


def test_install_bat_has_uninstall_hint() -> None:
    """L'installateur affiche la commande de désinstallation."""
    content = _read("install_telegram_cron.bat")
    assert "schtasks /delete" in content


def test_no_windows_console_flash_in_bat() -> None:
    """Aucune commande qui ouvrirait une console visible (start /wait, cmd /c).

    Le wrapper tourne en background via schtasks onlogon — la fenêtre
    cmd elle-même ne doit pas flasher.
    """
    for name in ("start_telegram_notifier.bat", "install_telegram_cron.bat"):
        content = _read(name)
        # @echo off supprime l'echo (anti-flash de commandes)
        assert content.startswith("@echo off"), \
            f"{name} doit commencer par @echo off"


def test_bats_are_dos_line_endings() -> None:
    """Sanity check : les .bat doivent avoir des fins de ligne CRLF
    (sinon cmd.exe les interprète mal)."""
    for name in ("start_telegram_notifier.bat", "install_telegram_cron.bat"):
        path = SCRIPTS / name
        raw = path.read_bytes()
        assert b"\r\n" in raw, f"{name} doit avoir des fins de ligne CRLF"


def test_consistency_task_name() -> None:
    """Le nom de tâche doit être identique entre le wrapper (commentaire)
    et l'installateur (schtasks /tn)."""
    wrapper = _read("start_telegram_notifier.bat")
    installer = _read("install_telegram_cron.bat")
    assert "V9_TelegramNotifier" in wrapper
    assert "V9_TelegramNotifier" in installer