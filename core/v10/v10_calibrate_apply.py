"""V10 Calibrate Apply — active réellement la recalibration R8 (Phase R).

Branche les seuils recalibrés par l'auto-recalibrator (R8) dans le pipeline
live de décision. C'est la boucle R8 ACTIVE (pas juste recommandée) :
  trade clôturé → métrique → si KPI < seuil → recalibration bayésienne
  → seuils persistés → APPLIQUÉS au pipeline live → re-test.

Composants :
  1. `ensure_active_thresholds()` — s'assure qu'un fichier de seuils actif
     existe (recalibré si nécessaire, sinon dernier connu).
  2. `apply_to_config()` — injecte le chemin de seuils dans la config de
     décision live (consommé par compose_signal_with_context).

R10 : ne mute JAMAIS de constantes module (additif R2) — les seuils sont
chargés à runtime via thresholds_pair_tf_path, réversibles.
"""
from __future__ import annotations

import glob
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]  # C:\projet\V9
DEFAULT_SEUILS_DIR = ROOT / "config"
ACTIVE_SEUILS_NAME = "v10_active_thresholds.json"


def find_recalibrated_thresholds() -> Optional[str]:
    """Retourne le chemin du dernier fichier de seuils recalibrés (R8).

    Cherche dans l'ordre :
      1. config/v10_auto_recalib_*.json (produit par auto-recalibrator)
      2. config/v10_bayesian_thresholds_pair_tf*.json (recalibration Phase 21)
    R6 : aucun trouvé → None (fail-open, pipeline utilise les défauts).

    ⚠️ R9 (fix ZCode 2026-08-06) : un fichier auto_recalib peut être VIDE
    (recalibration échouée → thresholds_by_pair_tf={}). On ne sélectionne
    que les fichiers avec des seuils réels — sinon le pipeline live
    consomme un fichier vide (zone morte R8).
    """
    import json

    patterns = [
        "config/v10_auto_recalib_*.json",
        "config/v10_bayesian_thresholds_pair_tf*.json",
    ]
    for pat in patterns:
        files = sorted(glob.glob(str(ROOT / pat)))
        for f in reversed(files):
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
                if data.get("thresholds_by_pair_tf"):
                    return f
            except Exception:
                continue
    log.warning("Aucun fichier de seuils recalibrés non-vide trouvé (R6 fail-open)")
    return None


def ensure_active_thresholds(force_recalib: bool = False,
                             db_path: str = "data/v9_forces.db") -> dict:
    """S'assure qu'un fichier de seuils actif existe et retourne son état.

    Si force_recalib=True, relance l'auto-recalibration (R8).
    Sinon, réutilise le dernier fichier recalibré si présent.
    """
    active = ROOT / "config" / ACTIVE_SEUILS_NAME

    # 1. Relance la recalibration si demandée
    if force_recalib:
        try:
            from core.v10.v10_auto_recalibrator import run_auto_recalibration
            dec = run_auto_recalibration(db_path=db_path)
            if dec.threshold_path and Path(dec.threshold_path).exists():
                # Copie vers le fichier actif
                import shutil
                shutil.copy(dec.threshold_path, active)
                return {
                    "status": "recalibrated",
                    "threshold_path": str(active),
                    "decision": dec.decision,
                    "before_wr": dec.before_wr,
                    "after_wr": dec.after_wr,
                }
        except Exception as exc:
            log.warning("Recalibration R8 échouée (R6 fail-open): %s", exc)

    # 2. Sinon, réutilise le dernier fichier recalibré
    last = find_recalibrated_thresholds()
    if last:
        import shutil
        try:
            shutil.copy(last, active)
            return {
                "status": "active_from_last",
                "threshold_path": str(active),
                "source": last,
            }
        except Exception as exc:
            log.warning("Copie seuils échouée (R6): %s", exc)

    # 3. Aucun seuil → fail-open (le pipeline utilise les défauts)
    return {"status": "no_thresholds", "threshold_path": None}


def apply_to_decision_config(threshold_path: Optional[str] = None) -> dict:
    """Produit la config de décision avec le chemin de seuils actif.

    Returns
    -------
    dict : {"thresholds_pair_tf_path": str|None, ...} à passer au pipeline.
    """
    path = threshold_path or find_recalibrated_thresholds()
    return {
        "thresholds_pair_tf_path": path,
        "r8_active": path is not None,
    }


__all__ = [
    "find_recalibrated_thresholds",
    "ensure_active_thresholds",
    "apply_to_decision_config",
    "ACTIVE_SEUILS_NAME",
]
