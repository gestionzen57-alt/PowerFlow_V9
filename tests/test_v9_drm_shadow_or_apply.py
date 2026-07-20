"""Test RED/P0 critique : DRManager APPLY silencieux (audit Opus 2026-07-20).

Bug P0 confirmé par l'audit Opus :
- `core/v9/trade_engine.py:72-77` (commentaire) affirme SHADOW-only.
- `core/v9/trade_engine.py:692-703` (code) APPLIQUE tp_pips/sl_pips/exit_strategy
  silencieusement dès que `source == "dynamic"`.
- `DYNAMIC_RISK_ENV` défaut "1" → mode APPLY actif par défaut.
- Conséquence : chaque décision live avec source="dynamic" override
  ses TP/SL/exit_strategy → cause probable du WR catastrophique 23.7%.

Ce test vérifie que la motion CEO #1 (SHADOW strict) est appliquée :
le DRM doit ÉVALUER et ATTACHER un diagnostic, mais NE PAS modifier
les tp_pips/sl_pips/exit_strategy dans le résultat final.

Tant que ce test échoue, le bug P0 est actif et le paper-trade loop
utilise des TP/SL override silencieux qui peuvent expliquer la
catastrophe -47k pips (cf deleg_2006e14f audit perf).

Motion CEO #1 rédigée dans workspace/perplexity/audits/OPUS_AUDIT_PROMPT_20260720_RESULT.md §F.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "BUG P0 ACTIF (audit Opus 2026-07-20) : DRManager APPLY silencieux "
        "à core/v9/trade_engine.py:692-703. Le commentaire ligne 72-77 "
        "affirme SHADOW-only mais le code override silencieusement les "
        "tp_pips/sl_pips/exit_strategy dès que source='dynamic'. Cause "
        "probable du WR 23.7% catastrophique. Motion CEO #1 requise pour "
        "SHADOW strict (commenter les 4 lignes APPLY). Test en xfail tant "
        "que motion non tranchée (xfail strict=False)."
    ),
    strict=False,
)
def test_drm_should_not_override_tp_pips() -> None:
    """Le DRM ne doit PAS modifier tp_pips dans le résultat final.

    Le commentaire `trade_engine.py:72-77` dit SHADOW-only : le DRM
    évalue et attache `result["dynamic_risk"]` mais n'override PAS
    les paramètres de trade.

    Tant que `trade_engine.py:692-703` (lignes APPLY) n'est pas commenté,
    le TP/SL est silencieusement remplacé par celui du DRM.
    """
    from pathlib import Path
    trade_engine_path = (
        Path(__file__).resolve().parent.parent
        / "core" / "v9" / "trade_engine.py"
    )
    content = trade_engine_path.read_text(encoding="utf-8")
    forbidden_patterns = [
        "tp_pips = float(risk_decision.tp_pips)",
        "sl_pips = float(risk_decision.sl_pips)",
        "exit_strategy = risk_decision.exit_strategy",
        'result["drm_applied"] = True',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in content, (
            f"DRManager APPLY pattern '{pattern}' encore présent dans "
            f"{trade_engine_path}. Motion CEO #1 : commenter ces lignes "
            f"pour aligner code et doctrine (R32 SHADOW-only)."
        )


@pytest.mark.xfail(
    reason=(
        "Couplé au test_drm_should_not_override_tp_pips — même bug P0. "
        "Marqué xfail pour traçabilité."
    ),
    strict=False,
)
def test_drm_comment_says_shadow() -> None:
    """Le commentaire ligne 72-77 doit affirmer SHADOW-only explicite."""
    from pathlib import Path
    trade_engine_path = (
        Path(__file__).resolve().parent.parent
        / "core" / "v9" / "trade_engine.py"
    )
    content = trade_engine_path.read_text(encoding="utf-8")
    assert "n'APPLIQUE rien" in content or "n'applique rien" in content or "SHADOW" in content, (
        "Commentaire DRManager doit affirmer SHADOW-only."
    )


@pytest.mark.xfail(
    reason=(
        "Couplé au test_drm_should_not_override_tp_pips — même bug P0. "
        "DYNAMIC_RISK_ENV défaut 1 actuellement, motion CEO #1 propose 0."
    ),
    strict=False,
)
def test_dynamic_risk_default_is_off() -> None:
    """`DYNAMIC_RISK_ENV` doit avoir défaut OFF (=0) tant que la motion
    CEO #1 n'est pas tranchée."""
    from pathlib import Path
    import re
    trade_engine_path = (
        Path(__file__).resolve().parent.parent
        / "core" / "v9" / "trade_engine.py"
    )
    content = trade_engine_path.read_text(encoding="utf-8")
    match = re.search(
        r"def _dynamic_risk_enabled\(\).*?(?=\ndef |\nclass |\Z)",
        content,
        re.DOTALL,
    )
    if match:
        func_body = match.group(0)
        assert '"0"' in func_body or "'0'" in func_body, (
            "_dynamic_risk_enabled() défaut devrait être OFF (R25'')."
        )
