# V10 DOCUMENT STATUS — Hiérarchie de vérité

**Dernière MAJ :** 2026-08-11 19:00 UTC — Hermes (PLEINE PUISSANCE — edge OVERLAP + doctrine)

---

## 📂 Documents actifs (source de vérité)

| Document | Rôle | Fréquence MAJ |
|---|---|---|
| `docs/V10/DOCTRINE_PLEIN_POTENTIEL.md` | **La loi** — autonomie totale, performant prime | Référence |
| `docs/V10/MANIFESTE_EXISTENCE_HERMES.md` | Héritage + état de l'edge | Chaque jalon |
| `docs/V10/STATE.md` | État pipeline complet (état courant en tête) | Chaque phase livrée |
| `docs/V10/CACHE_BOARD.md` | Snapshot live opérationnel | Chaque session |
| `reports/v10_shadow_edge_*.json` | Track record edge OVERLAP | Chaque run |
| `docs/V10/DOCUMENT_STATUS.md` | Ce fichier | Chaque sprint |

---

## 🏛️ Hiérarchie de vérité

```
1. DOCTRINE_PLEIN_POTENTIEL  ← la loi
2. STATE.md                  ← état courant (tête) + historique
3. Rapports JSON             ← audit trails (edge, replay, live)
4. Tests pytest              ← vérité code (1380/1380 verts)
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
