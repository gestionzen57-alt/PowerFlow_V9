"""v9_onboarding_doc_gen.py — Phase 91 motion CEO 48H (post-Plan C).

Genere une doc d'onboarding pour un nouveau developpeur sur V9.
Sections : quickstart, kill_switches, live_deploy, troubleshooting.

Auteur : Hermes (Phase 91 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger("v9.onboarding")

SECTIONS = ["quickstart", "kill_switches", "live_deploy", "troubleshooting"]


def generate_quickstart() -> str:
    """Section quickstart."""
    return """## Quickstart

```bash
# 1. Cloner et installer
git clone https://github.com/gestionzen57-alt/PowerFlow_V9.git
cd PowerFlow_V9
uv sync

# 2. Lancer les tests
python -m pytest tests/ -q -m "not slow" -p no:cacheprovider

# 3. Verifier la sante
python scripts/v9_real_money_preflight.py

# 4. Lire les docs cles
cat docs/USER_GUIDE.md
cat docs/DOCTRINE_48H_NONSTOP.md
cat reports/BILAN_AUDIT_PERPLEXITY_V9.md
```

**Prerequisites** : Python 3.11+, uv, git-bash (Windows) ou bash (Unix).
"""


def generate_kill_switches_doc() -> str:
    """Section kill switches."""
    return """## Kill Switches (DOCTRINE R25')

Les kill switches sont dans `config/v9_kill_switches.env` (58 charges).

**Les plus critiques** :
```
V9_TRADE_ENGINE_ENABLED=1         # ON/OFF master
V9_KILL_DD_PIPS=-100              # DD threshold
V9_KILL_WR_FLOOR=0.40             # WR minimum
V9_MEGA_EDGE_ENABLED=1            # 17 leviers SQL
V9_PAPER_TRADE_HALT=0             # HALT total paper
V9_MT4_BRIDGE_ENABLED=1           # Bridge MT4 actif
V9_DYNAMIC_RISK_ENABLED=1         # DRM SL/TP adaptatifs
V9_NO_BAISSIERE=0                 # Force haussiere global
```

**⚠ WARNING** : toute modification necessite un commit + push + audit.
"""


def generate_live_deploy_doc() -> str:
    """Section live deploy."""
    return """## Live Deploy (FTMO)

**Pre-requis obligatoire** :
1. Walk-forward OOS 7j (Phase 12 cible)
2. Sharpe OOS > 0.5 (validation edge)
3. Tokens Telegram valides (rotation < 7j)
4. MT4 EA compile + deploye sur tous charts M1
5. Backup DB avant chaque LIVE motion

**Commandes** :
```bash
# 1. Backup avant LIVE
bash scripts/v9_backup_strategy.py --keep-daily 7

# 2. Verifier pre-flight
python scripts/v9_real_money_preflight.py

# 3. Activer LIVE (mini-lot 0.01)
export V9_PAPER_TRADE_HALT=0
export V9_FTMO_DAILY_DD_PCT=0.04
export V9_FTMO_TOTAL_DD_PCT=0.08

# 4. Monitorer
python scripts/v9_live_metrics.py --watch
```

**FTMO rules** :
- Max DD daily : 4%
- Max DD total : 8%
- Profit target : 10% (phase 1), 5% (phase 2)
"""


def generate_troubleshooting_doc() -> str:
    """Section troubleshooting."""
    return """## Troubleshooting (problemes connus)

**Probleme** : `DB lock timeout iteration N`
- **Cause** : DB verouillee par un autre process
- **Fix** : `python scripts/v9_circuit_breaker.py --reset`

**Probleme** : Telegram alert ne part pas
- **Cause** : Token expire / mal configure
- **Fix** : `python scripts/v9_token_rotation.py --history` puis `@BotFather /revoke`

**Probleme** : Trades bloques par HARD_BLACKLIST
- **Cause** : GBPUSD/USDCHF/EURUSD hard-blacklistes (audit 30j)
- **Fix** : Consulter `core/v9/v9_mega_edge_filter.py` L1-L17

**Probleme** : `NameError: risk_go_context` ou `context` (FIXED 310de1e)
- **Cause** : variable utilisee avant definition
- **Fix** : appliquer BUG-01 + BUG-03 fixes (commit 310de1e)

**Probleme** : `MIN_CONFIDENCE_GATE` skip legitime
- **Cause** : ordre cascade boost avant gate (FIXED 046669f)
- **Fix** : appliquer BUG-04 fix (commit 046669f)

**Probleme** : DB integrity > 1GB
- **Cause** : accumulation de snapshots
- **Fix** : `python scripts/v9_backup_strategy.py --keep-daily 3`
"""


def generate_full_doc() -> str:
    """Compose toutes les sections."""
    today = date.today().strftime("%Y-%m-%d")
    parts = [
        f"# V9 Onboarding ({today})\n",
        "Documentation generee par v9_onboarding_doc_gen.py — Phase 91.\n",
        generate_quickstart(),
        generate_kill_switches_doc(),
        generate_live_deploy_doc(),
        generate_troubleshooting_doc(),
    ]
    return "\n".join(parts)


def export_doc(content: str, output_path: Path) -> bool:
    """Exporte la doc vers un fichier."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("export_doc failed: %s", exc)
        return False


def main(argv=None) -> int:
    """Genere la doc d'onboarding."""
    parser = argparse.ArgumentParser(description="V9 onboarding doc generator")
    parser.add_argument("--output", default="./docs/ONBOARDING.md")
    args = parser.parse_args(argv)
    print("=" * 70)
    print("V9 ONBOARDING DOC (Phase 91)")
    print("=" * 70)
    md = generate_full_doc()
    out = Path(args.output)
    ok = export_doc(md, out)
    print(f"Output  : {out}")
    print(f"Sections : {len(SECTIONS)}")
    print(f"Length  : {len(md)} chars")
    print(f"Written : {ok}")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())