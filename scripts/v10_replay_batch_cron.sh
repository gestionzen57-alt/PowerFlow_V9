#!/usr/bin/env bash
# V10 Replay Batch Cron — replay profondeur complète + rafraîchit la carte des edges (Sprint).
# Rejoue toute l'historique, identifie les edges, notifie le CEO sur Telegram.
set -uo pipefail
cd /c/projet/V9 || exit 2
PY=python
TMPD="C:/projet/V9/.tmp_v10replay"
mkdir -p "$TMPD"

echo "=== V10 REPLAY BATCH $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Replay batch profondeur complète (rafraîchit carte des edges + modèle)
$PY scripts/v10_replay_batch.py >"$TMPD/replay_out.json" 2>"$TMPD/replay.err"
REPLAY_RC=$?
if [ $REPLAY_RC -ne 0 ]; then
  echo "ERROR replay_batch rc=$REPLAY_RC: $(tail -1 "$TMPD/replay.err")"
  exit 1
fi
echo "OK replay_batch"

# 2. Résumé de la carte des edges
python - <<'PYEOF'
import json, os
p=os.path.join(os.getcwd(),'reports','v10_replay_batch_20260805.json')
# prend le plus récent
import glob
files=sorted(glob.glob(os.path.join(os.getcwd(),'reports','v10_replay_batch_*.json')))
if files:
    p=files[-1]
try:
    d=json.load(open(p,encoding='utf-8'))
    lm=d.get('learning_model',{})
    print(f"REPLAY trades={lm.get('n_trades_total')} wr={lm.get('wr')} edges={d.get('n_edges_yes')} drift={lm.get('drift_detected')} persisté={lm.get('persisted')}")
    for k,v in d.get('edge_map',{}).items():
        if v.get('edge')=='YES':
            print(f"  {k}: WR={v['wr']:.2f} ({v['n']} trades, {v['direction']})")
except Exception as e:
    print(f"parse_error: {e}")
PYEOF

# 3. Notifie la carte des edges sur Telegram (si configuré)
$PY scripts/v10_edges_telegram_alert.py >"$TMPD/edges_tg_out.txt" 2>>"$TMPD/replay.err"
TG_RC=$?
if [ $TG_RC -ne 0 ]; then
  echo "WARN edges_telegram rc=$TG_RC (canal non requis): $(tail -1 "$TMPD/replay.err" 2>/dev/null)"
else
  echo "OK edges_telegram"
fi

rm -rf "$TMPD"
echo "=== DONE ==="
