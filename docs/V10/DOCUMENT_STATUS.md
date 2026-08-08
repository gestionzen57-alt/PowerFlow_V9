# V10 DOCUMENT STATUS — Hiérarchie de vérité

**Dernière MAJ :** 2026-08-08 20:34 CEST — Perplexity GitHub MCP (Sprint 24)

---

## 📂 Documents actifs (source de vérité)

| Document | Rôle | Fréquence MAJ |
|---|---|---|
| `docs/V10/CACHE_BOARD.md` | Snapshot live opérationnel | Chaque session |
| `docs/V10/STATE.md` | État pipeline complet | Chaque phase livrée |
| `docs/V10/SPRINT_24_ROADMAP.md` | Backlog + tracking Sprint 24 | Sprint actif |
| `docs/V10/RL_PROMOTION_TRACKER.md` | Suivi gates SHADOW→ACTIVE | Chaque run shadow |
| `docs/V10/P3_NETTOYAGE_V9.md` | Audit V9 skip (P3 mandat CEO) | Statique |
| `docs/V10/DOCUMENT_STATUS.md` | Ce fichier | Chaque sprint |

---

## 🏛️ Hiérarchie de vérité

```
1. CACHE_BOARD.md     ← snapshot le plus récent (état actuel)
2. STATE.md           ← historique des phases (référence)
3. SPRINT_24_ROADMAP  ← backlog courant
4. Rapports JSON      ← audit trails (reports/)
5. Tests pytest       ← vérité code (1310/1310 verts)
```

---

## 📋 Documents obsolètes / archivés

| Document | Statut | Remplacé par |
|---|---|---|
| Anciens SESSION_CACHE | Archivé | CACHE_BOARD.md |
| AUDIT_BIAIS_V10 | Statique (audit 2026-08-06) | STATE.md section Phase Cognitive |

---

## 🔒 Gouvernance

- **Source de vérité tests** : résultat pytest live sur `feat/v9-foundation-clean`
- **Source de vérité DB** : `data/v9_forces.db` (Hermes, port 31685)
- **Mandat CEO actif** : P3 Nettoyage V9 (2026-08-08) — exécuté ✅
- **Sprint actif** : Sprint 24 (2026-08-08 →)

---

*MAJ automatique Perplexity GitHub MCP — 2026-08-08 20:34 CEST*
