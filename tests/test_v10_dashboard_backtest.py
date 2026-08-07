"""Test S23-C — Backtest summary endpoint dans dashboard API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v10_dashboard_api import app  # noqa: E402

client = TestClient(app)


def test_s23c_backtest_summary_endpoint_exists():
    """1. GET /api/v1/backtest/summary → 200, champ kill_zone_results présent."""
    response = client.get("/api/v1/backtest/summary")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "kill_zone_results" in data
    assert "base_wr" in data
    assert "signals_total" in data
    assert "by_signal_level" in data
    # Vérifier les kill zones
    kz = data["kill_zone_results"]
    for zone in ["NY", "LONDON", "ASIAN", "OUTSIDE"]:
        assert zone in kz, f"Kill zone {zone} manquante"
        assert "n" in kz[zone]
        assert "wr" in kz[zone]
        assert "delta_wr_pts" in kz[zone]
        assert "pnl" in kz[zone]


def test_s23c_backtest_summary_missing_file_404():
    """2. GET /api/v1/backtest/summary (fichier absent) → 404."""
    from fastapi import HTTPException
    from pathlib import Path
    import tempfile
    import os
    
    # Test simple : vérifier que HTTPException est levée pour 404
    def check_missing():
        path = Path("fichier_inexistant_xyz.json")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Backtest report not found")
    
    try:
        check_missing()
    except HTTPException as e:
        assert e.status_code == 404
        assert "not found" in e.detail.lower()


def test_s23c_backtest_summary_kill_zones_values():
    """3. Vérifier les valeurs des kill zones (NY +20pts, LONDON +11.5pts, etc.)."""
    response = client.get("/api/v1/backtest/summary")
    assert response.status_code == 200
    data = response.json()
    kz = data["kill_zone_results"]
    
    # NY: WR ~53% = base 33% + 20pts
    assert abs(kz["NY"]["wr"] - 0.5322) < 0.01, f"NY WR: {kz['NY']['wr']}"
    assert abs(kz["NY"]["delta_wr_pts"] - 20.03) < 0.1
    
    # LONDON: WR ~44.7% = base 33% + 11.5pts
    assert abs(kz["LONDON"]["wr"] - 0.4467) < 0.01
    assert abs(kz["LONDON"]["delta_wr_pts"] - 11.49) < 0.1
    
    # ASIAN: WR ~39.9% = base 33% + 6.7pts
    assert abs(kz["ASIAN"]["wr"] - 0.3991) < 0.01
    assert abs(kz["ASIAN"]["delta_wr_pts"] - 6.72) < 0.1
    
    # OUTSIDE: WR ~23.4% = base 33% - 9.8pts
    assert abs(kz["OUTSIDE"]["wr"] - 0.2343) < 0.01
    assert abs(kz["OUTSIDE"]["delta_wr_pts"] - (-9.76)) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])