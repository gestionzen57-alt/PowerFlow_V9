#!/usr/bin/env python3
"""execution_threshold_audit.py — Validation statistique du seuil d'exécution.

Compare le Win Rate (WR) des trades dans la zone [70, 85[ vs la zone [85, 100].
"""

import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "v9_forces.db"

def audit_thresholds():
    print("🔬 Audit statistique du seuil d'exécution (WR 70-85 vs 85+)...")
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # On analyse les trades résolus
        query = """
            SELECT confiance, is_win 
            FROM decisions 
            WHERE is_win IS NOT NULL 
              AND confiance >= 70
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ Aucun trade résolu avec confiance >= 70% trouvé.")
            return

        # Tranche 1: [70, 85[
        t1_wins = 0
        t1_total = 0
        # Tranche 2: [85, 100]
        t2_wins = 0
        t2_total = 0
        
        for r in rows:
            conf = r["confiance"]
            win = 1 if r["is_win"] == 1 else 0
            if conf < 85:
                t1_wins += win
                t1_total += 1
            else:
                t2_wins += win
                t2_total += 1
        
        wr1 = (t1_wins / t1_total * 100) if t1_total > 0 else 0
        wr2 = (t2_wins / t2_total * 100) if t2_total > 0 else 0
        
        print(f"\n📊 RÉSULTATS de l'Audit :")
        print(f"  - Tranche [70, 85[ : {t1_total} trades | WR = {wr1:.2f}%")
        print(f"  - Tranche [85, 100] : {t2_total} trades | WR = {wr2:.2f}%")
        
        if wr2 > wr1:
            diff = wr2 - wr1
            print(f"\n✅ CONCLUSION : Le seuil de 85 est VALIDÉ. Gain de précision : +{diff:.2f}%")
        else:
            print(f"\n⚠️ CONCLUSION : Le seuil de 85 n'améliore pas le WR. Vérifier la distribution.")

        conn.close()
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    audit_thresholds()
