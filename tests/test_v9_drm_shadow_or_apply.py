"""Test DRM APPLY permanent (motion CEO R32-CLOSE 2026-07-20).

Historique : ces tests étaient en xfail sous l'hypothèse d'un bug P0
« DRManager APPLY silencieux » (audit Opus 2026-07-20). La motion CEO
R32-CLOSE (Søren, 2026-07-20 13h10 CEST) tranche définitivement :

- DRM opère en mode **APPLY** par défaut — c'est le comportement voulu,
  pas un bug. R32 (SHADOW obligatoire) est **fermée**.
- Principe directeur : autonomie système, zéro friction doctrinal.

Les tests vérifient donc désormais que le mode APPLY est bien câblé :
`core/v9/trade_engine.py` propage tp_pips/sl_pips/exit_strategy issus du
DynamicRiskManager et le kill-switch `V9_DYNAMIC_RISK_ENABLED` est ON par
défaut. Retour SHADOW interdit sans nouvelle motion CEO explicite.

Cf. DOCTRINE.md R32 (révisée) + DECISIONS_LOG §2026-07-20 13h10 CEST.
"""

from __future__ import annotations

from pathlib import Path


def _trade_engine_source() -> str:
    trade_engine_path = (
        Path(__file__).resolve().parent.parent
        / "core" / "v9" / "trade_engine.py"
    )
    return trade_engine_path.read_text(encoding="utf-8")


def test_drm_applies_tp_sl() -> None:
    """Le DRM APPLIQUE tp_pips/sl_pips et marque result["drm_applied"].

    Motion CEO R32-CLOSE : APPLY est le mode permanent. Les lignes qui
    propagent la décision dynamique doivent être présentes dans le code.
    """
    content = _trade_engine_source()
    required_patterns = [
        "tp_pips = float(risk_decision.tp_pips)",
        "sl_pips = float(risk_decision.sl_pips)",
        'result["drm_applied"] = True',
    ]
    for pattern in required_patterns:
        assert pattern in content, (
            f"Pattern APPLY '{pattern}' absent de trade_engine.py. "
            f"DRM doit rester en mode APPLY (motion CEO R32-CLOSE) — "
            f"retour SHADOW interdit sans motion CEO explicite."
        )


def test_drm_comment_says_apply() -> None:
    """Le commentaire du bloc DRM doit refléter le mode APPLY."""
    content = _trade_engine_source()
    assert "APPLY" in content, (
        "Commentaire/bloc DRManager doit affirmer le mode APPLY "
        "(motion CEO R32-CLOSE — R32 fermée)."
    )


def test_dynamic_risk_default_is_on() -> None:
    """`V9_DYNAMIC_RISK_ENABLED` doit avoir défaut ON (=1).

    Motion CEO R32-CLOSE : DRM APPLY permanent. Le kill-switch reste
    disponible mais son défaut est ON.
    """
    import re
    content = _trade_engine_source()
    match = re.search(
        r"def _dynamic_risk_enabled\(\).*?(?=\ndef |\nclass |\Z)",
        content,
        re.DOTALL,
    )
    assert match, "_dynamic_risk_enabled() introuvable dans trade_engine.py."
    func_body = match.group(0)
    assert '"1"' in func_body or "'1'" in func_body, (
        "_dynamic_risk_enabled() doit avoir un défaut ON (=1) — "
        "DRM APPLY permanent (motion CEO R32-CLOSE)."
    )
