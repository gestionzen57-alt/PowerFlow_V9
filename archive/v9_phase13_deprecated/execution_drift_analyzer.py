#!/usr/bin/env python3
"""execution_drift_analyzer.py — Analyse du slippage entre Conseil et Exécution.

Ce script quantifie combien de signaux validés par RiskManager (70+) 
auraient été exécutés avec le seuil strict (85+).
"""

import json
import sqlite3
import argparse
from pathlib import Path
from collections import Counter

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "v9_forces.db"

def analyze_drift():
    print("🔍 Analyse du slippage Confiance (70% vs 85%)...")
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # On récupère les décisions validées par RiskManager (en supposant qu'elles sont en DB)
        # Note: RiskManager ne marque pas la DB, on filtre donc sur la confiance brute
        cursor.execute(
            "SELECT decision_id, symbol, direction, confiance "
            "FROM decisions "
            "WHERE confiance >= 70 AND direction != 'neutre'"
        )
        all_signals = cursor.fetchall()
        
        if not all_signals:
            print("❌ Aucun signal >= 70% trouvé en base.")
            return

        total = len(all_signals)
        executed = [s for s in all_signals if s["confiance"] >= 85]
        drift = total - len(executed)
        
        print(f"\n📊 RÉSULTATS :")
        print(f"  - Signaux 'Conseil' (>= 70%) : {total}")
        print(f"  - Signaux 'Exécution' (>= 85%) : {len(executed)}")
        print(f"  - Slippage (perte d'opportunités) : {drift} signaux ({drift/total*100:.1f}%)")
        
        # Distribution par tranche
        bins = {
            "70-75": 0, "76-80": 0, "81-84": 0, "85-90": 0, "91-100": 0
 la}
        for s in all_signals:
            c = s["confiance"]
            if 70 <= c <= 75: bins["70-75"] += 1
            elif 76 <= c <= 80: bins["76-80"] += 1
            elif 81 <= c <= 84: bins["81-84"] += 1
            elif 85 <= c <= 90: bins["85-90"] += 1
            elif c > 90: bins["91-100"] += 1
        
        print("\n📉 Distribution de confiance :")
        for b, count in bins.items():
            print(f"  {b} : {count} signaux")

        conn.close()
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    analyze_drift()
