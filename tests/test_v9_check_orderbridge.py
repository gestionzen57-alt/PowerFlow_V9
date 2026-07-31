"""tests/test_v9_check_orderbridge.py — Phase 13 motion CEO « EDGE FUND MAX »."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path):
    """Cree un faux workspace avec V9_OrderBridge.mq4 minimal (externs Phase 13)."""
    (tmp_path / "mt4_bridge").mkdir()
    bridge = tmp_path / "mt4_bridge" / "V9_OrderBridge.mq4"
    bridge.write_text("""
//+------------------------------------------------------------------+
//| V9_OrderBridge.mq4                                                |
//+------------------------------------------------------------------+
#property copyright "PowerFlow V9"
#property version   "1.00"

extern string  OrderQueuePath = "C:\\\\projet\\\\V9\\\\data\\\\order_queue";
extern string  ProcessedPath  = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\processed";
extern string  FailedPath     = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\failed";
extern int     PollSeconds    = 5;
extern int     Slippage       = 3;
extern int     MagicNumber    = 90900001;
extern bool    DryRun         = true;    // MODE SAFE par defaut

int init() {
   Print("[V9_OrderBridge] DryRun = ", DryRun);
   return(0);
}

void OnTick() {
   if(DryRun) {
      Print("[V9_OrderBridge] DRY RUN mode, no real orders");
      return;
   }
   // Phase 12 LIVE : order ici avec Lots = 0.01
}
""", encoding="utf-8")
    return tmp_path


def test_check_bridge_ok(workspace):
    """Bridge avec DryRun=true + 4 externs → ok=True."""
    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(workspace)
    assert res["ok"] is True
    assert res["alert"] is False
    assert res["recommendation"] == "ready_phase12_live"


def test_check_bridge_dry_run_default(workspace):
    """DryRun=true doit etre detecte."""
    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(workspace)
    assert res["checks"]["dry_run_default"] is True


def test_check_bridge_required_externs(workspace):
    """7 externs requis : DryRun, 3 paths, PollSeconds, Slippage, MagicNumber."""
    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(workspace)
    externs = res["checks"]["required_externs"]
    assert externs["DryRun"] is True
    assert externs["OrderQueuePath"] is True
    assert externs["ProcessedPath"] is True
    assert externs["FailedPath"] is True
    assert externs["PollSeconds"] is True
    assert externs["Slippage"] is True
    assert externs["MagicNumber"] is True


def test_check_bridge_missing_file(tmp_path):
    """Pas de bridge → alert verifier_mt4_bridge_deployment."""
    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(tmp_path)
    assert res["ok"] is False
    assert res["alert"] is True
    assert res["recommendation"] == "verifier_mt4_bridge_deployment"


def test_check_bridge_dry_run_false_is_alert(tmp_path):
    """DryRun=false (live) → alert fatal."""
    (tmp_path / "mt4_bridge").mkdir()
    bridge = tmp_path / "mt4_bridge" / "V9_OrderBridge.mq4"
    bridge.write_text("""
extern string  OrderQueuePath = "C:\\\\projet\\\\V9\\\\data\\\\order_queue";
extern string  ProcessedPath  = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\processed";
extern string  FailedPath     = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\failed";
extern int     PollSeconds    = 5;
extern int     Slippage       = 3;
extern int     MagicNumber    = 90900001;
extern bool    DryRun = false;
""", encoding="utf-8")

    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(tmp_path)
    assert res["alert"] is True
    assert res["checks"]["dry_run_default"] is False


def test_check_bridge_missing_required_extern(tmp_path):
    """Il manque Slippage → alert."""
    (tmp_path / "mt4_bridge").mkdir()
    bridge = tmp_path / "mt4_bridge" / "V9_OrderBridge.mq4"
    bridge.write_text("""
extern string  OrderQueuePath = "C:\\\\projet\\\\V9\\\\data\\\\order_queue";
extern string  ProcessedPath  = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\processed";
extern string  FailedPath     = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\failed";
extern int     PollSeconds    = 5;
extern int     MagicNumber    = 90900001;
extern bool    DryRun = true;
""", encoding="utf-8")

    from scripts.v9_check_orderbridge import check_orderbridge
    res = check_orderbridge(tmp_path)
    assert res["ok"] is False
    assert res["checks"]["required_externs"]["Slippage"] is False


def test_main_cli(tmp_path, capsys):
    """CLI main() retourne 0 si ok, 1 si alert, JSON stdout."""
    (tmp_path / "mt4_bridge").mkdir()
    bridge = tmp_path / "mt4_bridge" / "V9_OrderBridge.mq4"
    bridge.write_text("""
extern string  OrderQueuePath = "C:\\\\projet\\\\V9\\\\data\\\\order_queue";
extern string  ProcessedPath  = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\processed";
extern string  FailedPath     = "C:\\\\projet\\\\V9\\\\data\\\\order_queue\\\\failed";
extern int     PollSeconds    = 5;
extern int     Slippage       = 3;
extern int     MagicNumber    = 90900001;
extern bool    DryRun = true;
""", encoding="utf-8")

    from scripts.v9_check_orderbridge import main
    exit_code = main([str(tmp_path)])
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert exit_code == 0
    assert out["ok"] is True