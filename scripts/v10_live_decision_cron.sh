#!/usr/bin/env bash
# V10 Live Decision Cron — boucle décision temps-réel (Sprint 15).
# Produit les décisions BUY/SELL/WAIT sur les 6 paires + persiste le rapport.
set -uo pipefail
cd /c/projet/V9 || exit 2
PY=python
TMPD="C:/projet/V9/.tmp_v10live"
mkdir -p "$TMPD"

echo "=== V10 LIVE DECISION $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

$PY scripts/v10_live_decision.py --ticks 1 >"$PWD/reports/v10_live_decision_latest.json" 2>/tmp/v10_live_dec.err
RC=$?
if [ $RC -ne 0 ]; then
  echo "ERROR v10_live_decision rc=$RC: $(tail -1 /tmp/v10_live_dec.err)"
  exit 1
fi

# Cortex live — interprétation continue (mémoire + cohérence + mémorisation)
$PY scripts/v10_cortex_live.py --ticks 1 >"$PWD/reports/v10_cortex_live_latest.json" 2>/tmp/v10_cortex_live.err
CX_RC=$?
if [ $CX_RC -ne 0 ]; then
  echo "WARN v10_cortex_live rc=$CX_RC: $(tail -1 /tmp/v10_cortex_live.err)"
else
  echo "OK v10_cortex_live"
fi

# Extrait les actions BUY/SELL (signaux exploitables)
python - <<'PYEOF'
import json, os
p=os.path.join(os.getcwd(),'reports','v10_live_decision_latest.json')
try:
    d=json.load(open(p,encoding='utf-8'))
    active=[r for r in d.get('tick_results',[]) if r.get('action') in ('BUY','SELL')]
    waits=[r for r in d.get('tick_results',[]) if r.get('action')=='WAIT']
    print(f"ACTIVE_SIGNALS={len(active)} WAIT={len(waits)}")
    for r in active:
        print(f"  {r['pair']} {r['action']} (regime={r.get('regime')}, level={r.get('filtered_level')}, lot={r.get('lot_size')})")
    if not active:
        print("  (aucun signal actif)")
except Exception as e:
    print(f"parse_error: {e}")
PYEOF

# Notifie les signaux sur Telegram (si configuré)
$PY scripts/v10_telegram_alert.py >>"$TMPD/telegram.log" 2>>"$TMPD/telegram.err"
TG_RC=$?
if [ $TG_RC -ne 0 ]; then
  echo "WARN telegram_alert rc=$TG_RC (canal non requis): $(tail -1 "$TMPD/telegram.err" 2>/dev/null)"
else
  echo "OK telegram_alert"
fi

# Résout les outcomes dès que des barres futures existent (pas d'attente 24h)
$PY scripts/v10_resolve_outcomes.py >"$TMPD/resolve_out.json" 2>>"$TMPD/resolve.err"
RESOLVE_RC=$?
if [ $RESOLVE_RC -ne 0 ]; then
  echo "ERROR resolve_outcomes rc=$RESOLVE_RC: $(tail -1 "$TMPD/resolve.err" 2>/dev/null)"
else
  echo "OK resolve_outcomes"
fi

rm -rf "$TMPD"
echo "=== DONE ==="
