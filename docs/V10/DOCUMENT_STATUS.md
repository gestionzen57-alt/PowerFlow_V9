# V10 DOCUMENT STATUS — Hiérarchie de vérité

**Dernière MAJ :** 2026-08-10 22:30 UTC — Hermes (NO-LIMIT — H-LIVE-REPORT + H-REPLAY-C21)

---

## 📂 Documents actifs (source de vérité)

| Document | Rôle | Fréquence MAJ |
|---|---|---|
| `docs/V10/CACHE_BOARD.md` | Snapshot live opérationnel | Chaque session |
| `docs/V10/STATE.md` | État pipeline complet | Chaque phase livrée |
| `docs/V10/DOCUMENT_STATUS.md` | Ce fichier | Chaque sprint |
| `reports/live_session_<ts>.json` | Rapport session live C22 (H-LIVE-REPORT) | Chaque run |
| `reports/replay_c21_validation_*.json` | Validation replay C21 | Chaque run |

---

## 🏛️ Hiérarchie de vérité

```
1. CACHE_BOARD.md     ← snapshot le plus récent (état actuel)
2. STATE.md           ← historique des phases (référence)
3. Rapports JSON      ← audit trails (reports/)
4. Tests pytest       ← vérité code (1401/1401 verts)
```

---

## 📋 Documents obsolètes / archivés

| Document | Statut | Remplacé par |
|---|---|---|
| SPRINT_24_ROADMAP | Archivé (sprint clos) | STATE.md sections H-* |
| RL_PROMOTION_TRACKER | Archivé | STATE.md S25-OMEGA |
| Anciens SESSION_CACHE | Archivé | CACHE_BOARD.md |
| AUDIT_BIAIS_V10 | Statique (audit 2026-08-06) | STATE.md section Phase Cognitive |

---

## 🔒 Gouvernance

- **Source de vérité tests** : résultat pytest live sur `feat/hermes-night` — **1401/1401 verts** (HEAD `99159b9`)
- **Source de vérité DB** : `data/v9_forces.db` (18 GB, Hermes, port 31685) — PAS `powerflow.db`
- **Branche active** : `feat/hermes-night` (base `feat/v10-c20-healthy` mergée)
- **Mandat CEO actif** : NO-LIMIT (H-LIVE-REPORT + H-REPLAY-C21 livrés)
- **Doctrine** : R2 additif pur · R6 fail-open · R9 audit JSON · R10 zéro ordre réel

---

*MAJ Hermes — 2026-08-10 22:30 UTC*
