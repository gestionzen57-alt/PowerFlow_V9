#!/usr/bin/env bash
# V10 Night Cron — rapport nocturne consolidé + boucle R8 (auto).
# Exécute v10_night_report + v10_closed_loop, génère les JSON, sort stdout
# pour le cron (deliver Telegram).
set -uo pipefail
cd /c/projet/V9 || exit 2
PY=python
TMPD="C:/projet/V9/.tmp_v10cron"
mkdir -p "$TMPD"

echo "=== V10 NIGHT REPORT $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Rapport nocturne consolidé
$PY scripts/v10_night_report.py >/dev/null 2>"$TMPD/night.err"
NIGHT_RC=$?
if [ $NIGHT_RC -ne 0 ]; then
  echo "ERROR night_report rc=$NIGHT_RC: $(tail -1 "$TMPD/night.err")"
else
  echo "OK night_report"
fi

# 2. Boucle R8 (error learner → recalibration)
$PY scripts/v10_closed_loop.py >"$TMPD/loop_out.json" 2>"$TMPD/loop.err"
LOOP_RC=$?
if [ $LOOP_RC -ne 0 ]; then
  echo "ERROR closed_loop rc=$LOOP_RC: $(tail -1 "$TMPD/loop.err")"
else
  echo "OK closed_loop"
  TMPD="$TMPD" python - <<'PYEOF'
import json, os
tmpd=os.environ['TMPD']
try:
    d=json.load(open(os.path.join(tmpd,'loop_out.json'),encoding='utf-8'))
    rc=d['recalibration']
    ls=d['learner_state']
    print(f"CLOSED_LOOP trades={ls['n_trades']} wr={ls['n_wins']/max(1,ls['n_trades']):.3f} drift={ls['drift_detected']} decision={rc['decision']} reason={rc['reason']} before_wr={rc['before_wr']} after_wr={rc['after_wr']}")
except Exception as e:
    print(f"CLOSED_LOOP parse_error: {e}")
PYEOF
fi

# 3. Validation SHADOW→ACTIVE (gates R10)
$PY scripts/v10_shadow_promotion.py >/dev/null 2>"$TMPD/shadow.err"
SHADOW_RC=$?
if [ $SHADOW_RC -ne 0 ]; then
  echo "ERROR shadow_promotion rc=$SHADOW_RC: $(tail -1 "$TMPD/shadow.err")"
else
  echo "OK shadow_promotion"
fi

# 4. Risk dashboard R10 (net exposure + shield)
$PY scripts/v10_risk_dashboard.py >"$TMPD/riskd_out.json" 2>"$TMPD/riskd.err"
RISK_RC=$?
if [ $RISK_RC -ne 0 ]; then
  echo "ERROR risk_dashboard rc=$RISK_RC: $(tail -1 "$TMPD/riskd.err")"
else
  echo "OK risk_dashboard"
fi

# 5. Synthèse hebdomadaire (fermeture boucle R8)
$PY scripts/v10_weekly_summary.py >"$TMPD/weekly_out.json" 2>"$TMPD/weekly.err"
WEEKLY_RC=$?
if [ $WEEKLY_RC -ne 0 ]; then
  echo "ERROR weekly_summary rc=$WEEKLY_RC: $(tail -1 "$TMPD/weekly.err")"
else
  echo "OK weekly_summary"
fi

# 6. Alerte R8 Telegram (si recalibration requise)
$PY scripts/v10_r8_telegram_alert.py >"$TMPD/r8alert_out.txt" 2>"$TMPD/r8alert.err"
R8_RC=$?
if [ $R8_RC -ne 0 ]; then
  echo "WARN r8_telegram_alert rc=$R8_RC: $(tail -1 "$TMPD/r8alert.err" 2>/dev/null)"
else
  echo "OK r8_telegram_alert"
fi

# 7. Learning loop (apprentissage continu replay + live, boucle R8)
$PY scripts/v10_learning_loop.py --limit 200 >"$TMPD/learn_out.json" 2>"$TMPD/learn.err"
LEARN_RC=$?
if [ $LEARN_RC -ne 0 ]; then
  echo "ERROR learning_loop rc=$LEARN_RC: $(tail -1 "$TMPD/learn.err")"
else
  echo "OK learning_loop"
fi

# 8. Bilan de la journée (décisions + outcomes + apprentissage + reco)
$PY scripts/v10_daily_bilan.py >"$TMPD/bilan_out.json" 2>"$TMPD/bilan.err"
BILAN_RC=$?
if [ $BILAN_RC -ne 0 ]; then
  echo "ERROR daily_bilan rc=$BILAN_RC: $(tail -1 "$TMPD/bilan.err")"
else
  echo "OK daily_bilan"
fi

rm -rf "$TMPD"
echo "=== DONE ==="
