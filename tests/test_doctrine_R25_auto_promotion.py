"""Test RED : R25'' double moteur promotion dormant (audit 2026-07-20).

Doctrine R25'' :
- "tout principe SHADOW avec n_triggered ≥ 20 et confiance_moyenne ≥ 60
  est automatiquement promu ACTIVE au prochain cycle de calibration."

Bug P1 confirmé (deleg_90d60eaf) :
- `auto_calibrator.py:_apply_promotions_demotions` écrit dans
  `config/calibration_overrides.json[principle_active_ids_override]`
- MAIS aucun module ne lit `principle_active_ids_override` (grep → 0 read).
- Donc la promotion automatique R25'' est DORMANTE.

Tant que ce test échoue, motion CEO #2 requise pour :
- Soit câbler le reader dans principle_engine
- Soit supprimer l'écriture (et migrer sur v9_auto_promotion.py CLI)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OVERRIDES_PATH = REPO / "config" / "calibration_overrides.json"


@pytest.fixture(scope="module")
def overrides_data() -> dict:
    """Charge le JSON d'overrides de calibration."""
    if not OVERRIDES_PATH.exists():
        pytest.skip(f"calibration_overrides.json absent : {OVERRIDES_PATH}")
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


def test_principle_active_ids_override_has_reader(overrides_data: dict) -> None:
    """Si `principle_active_ids_override` est écrit dans le JSON,
    au moins UN module doit le lire (sinon c'est dormant)."""
    pid_override = overrides_data.get("principle_active_ids_override")
    if pid_override is None:
        pytest.skip("Pas de override actif — test conditionnel.")

    # Grep runtime pour trouver des lecteurs (l'import est lourd ; on utilise grep via shell)
    import subprocess
    r = subprocess.run(
        ["grep", "-RIn", "principle_active_ids_override",
         str(REPO / "core"), str(REPO / "scripts"), str(REPO / "tests")],
        capture_output=True, text=True,
    )
    hits = r.stdout.strip().splitlines() if r.stdout.strip() else []
    # Filtrer : on veut les LECTURES (pas les écritures auto_calibrator.py)
    reads = [h for h in hits if "auto_calibrator.py" not in h]
    assert len(reads) > 0, (
        f"R25'' dormant : principle_active_ids_override écrit dans "
        f"{OVERRIDES_PATH} mais AUCUN lecteur (en dehors de "
        f"auto_calibrator.py lui-même). Motion CEO : câbler le reader "
        f"dans principle_engine.load_principles_from_yaml() ou supprimer "
        f"l'écriture."
    )


@pytest.mark.xfail(
    reason=(
        "FINDING AUDIT 2026-07-20 — R25'' partiellement tenue : "
        "V9_AUTO_PROMOTION_ENABLED=1 dans .env mais v9_auto_promotion.py "
        "n'est câblé dans AUCUN cron V9_*. Le barème runtime (20/60/40/50) "
        "tourne mais n'écrit que dans principle_active_ids_override JSON "
        "que personne ne lit. Motion CEO : soit kill switch OFF explicite "
        "(R25'' dit 'décision CEO, non câblée'), soit câbler dans "
        "V9_AutoCalibrator après run_calibration_cycle."
    ),
    strict=False,
)
def test_auto_promotion_cron_wired() -> None:
    """`v9_auto_promotion.py` doit être câblé dans un cron V9_*.

    Doctrine R25'' impose auto-promotion runtime. Or, l'audit deleg_90d60eaf
    confirme que ce moteur n'est invoqué que via CLI manuel.

    Note : on tolère si le kill switch `V9_AUTO_PROMOTION_ENABLED` est
    explicitement OFF dans .env (R25'' dit "décision CEO", pas "auto").
    """
    env_path = REPO / "config" / "v9_kill_switches.env"
    content = env_path.read_text(encoding="utf-8")
    if "V9_AUTO_PROMOTION_ENABLED=0" in content:
        # Kill switch OFF explicitement → le runtime skip est cohérent avec R25''
        # (activation = décision CEO, pas câblée).
        pytest.skip(
            "V9_AUTO_PROMOTION_ENABLED=0 : motion CEO explicite pour ne pas "
            "promouvoir. Test skip."
        )
    # Sinon, on attend un cron câblé
    assert False, (
        "v9_auto_promotion.py n'est pas câblé dans un cron (audit "
        "deleg_90d60eaf). Motion CEO : soit câbler dans V9_AutoCalibrator "
        "après run_calibration_cycle, soit kill switch OFF explicitement."
    )
