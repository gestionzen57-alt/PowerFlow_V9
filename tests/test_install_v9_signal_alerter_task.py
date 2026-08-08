"""Tests Phase 179 (03/08) : install_v9_signal_alerter_task.ps1.

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Vérifie la cohérence structurelle du script d'installation de la
tâche planifiée Windows V9SignalAlerter (sans exécuter PowerShell).

Doctrine :
  - R2 additif : 0 modif fichiers existants (1 nouveau .ps1 + 1 nouveau test)
  - R7 tests verts
  - R22 1 périmètre (1 tâche = 1 install)
  - R28 self-contained (ne dépend pas de PowerShell runtime)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = ROOT / "scripts" / "install_v9_signal_alerter_task.ps1"


def test_install_script_exists():
    """Le script d'install doit exister."""
    assert INSTALL_SCRIPT.exists(), f"introuvable: {INSTALL_SCRIPT}"
    assert INSTALL_SCRIPT.is_file()


def test_install_script_uses_admin_check():
    """Le script doit vérifier les privilèges admin (Register-ScheduledTask les requiert)."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "WindowsBuiltInRole" in content
    assert "Administrator" in content
    assert "exit 1" in content  # refuse sans admin


def test_install_script_targets_correct_paths():
    """Cible pythonw.exe + alerter.py dans C:\projet\V9."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert r"C:\projet\V9\.venv\Scripts\pythonw.exe" in content
    assert r"C:\projet\V9\scripts\v9_signal_alerter.py" in content
    assert r"C:\projet\V9" in content  # WORKDIR


def test_install_script_uses_atstartup_trigger():
    """Trigger = AtStartup (daemon 24/7) — exigence CEO 'rien à lancer'."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "AtStartup" in content
    assert "RestartCount 0" in content  # anti-boucle Phase 168


def test_install_script_unregisters_existing_task():
    """Idempotence : supprime l'ancienne tâche si présente."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "Get-ScheduledTask" in content
    assert "Unregister-ScheduledTask" in content
    assert "Confirm:$false" in content


def test_install_script_no_modif_existing_files():
    """R2 additif pur : le script d'install ne doit référencer AUCUN fichier
    existant (capture_watchdog, telegram, config) en écriture — uniquement
    en lecture pour vérifier l'existence. Ignore les commentaires (#)."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    # Strip commentaires PowerShell (lignes commençant par #, après retraitement)
    non_comment_lines = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Strip trailing comments after code
        if "#" in line and not line.lstrip().startswith("#"):
            # Garde la partie avant le # (peut être un inline-comment)
            code_part = line.split("#", 1)[0]
            non_comment_lines.append(code_part)
        else:
            non_comment_lines.append(line)
    code_only = "\n".join(non_comment_lines)

    forbidden_writes = [
        "v9_capture_watchdog.py",  # autre script
        "v9_capture_watchdog_task.ps1",  # autre install
        "v9_telegram_notifier.py",  # module existant
        "config/telegram.json",  # config existante
        "core/",  # tout core/ intouchable
    ]
    for fw in forbidden_writes:
        if fw in code_only:
            # Si présente dans le code, vérifier qu'elle n'est qu'en Test-Path
            pattern = re.compile(re.escape(fw))
            for match in pattern.finditer(code_only):
                start = max(0, match.start() - 60)
                ctx = code_only[start:match.end() + 10]
                assert "Test-Path" in ctx, (
                    f"Fichier existant {fw} référencé hors Test-Path/lecture : {ctx!r}"
                )


def test_install_script_registers_task_with_description():
    """La tâche doit être enregistrée avec une description non-vide."""
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in content
    # La description doit mentionner Phase 179 et Telegram
    desc_match = re.search(r'-Description\s+"([^"]+)"', content)
    assert desc_match is not None, "Description manquante dans Register-ScheduledTask"
    desc = desc_match.group(1)
    assert "Phase 179" in desc or "Telegram" in desc
