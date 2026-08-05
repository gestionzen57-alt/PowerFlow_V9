# SYNC_PROTOCOL — Protocole Collaboration Perplexity ↔ Hermes

> Version : 1.0 — 2026-08-05  
> Auteur : Perplexity (architecte externe)  
> Statut : **ACTIF**

---

## Problème résolu

Le fondateur ne peut pas recopier manuellement les sessions Hermes (VPS/mobile).
Ce protocole rend la collaboration **asynchrone, automatique et Git-native**.
Perplexity lit Git → écrit son analyse → Hermes lit → implémente → commit → Perplexity re-lit.

---

## Principe — Le Git est le bus de communication

```
[Fondateur] → [Hermes sur VPS] → git commit → GitHub
                                                  ↓
                                         [Perplexity lit @GitHub]
                                                  ↓
                              workspace/perplexity/PERPLEXITY_REVIEW.md
                                                  ↓
                                    [Hermes lit et implémente]
```

**Règle absolue** : aucune information ne transite par copier-coller manuel.
Tout passe par des fichiers Git committes.

---

## Fichiers du protocole

| Fichier | Propriétaire | Fréquence update |
|---|---|---|
| `workspace/perplexity/SYNC_PROTOCOL.md` | Perplexity | Évolution protocole |
| `workspace/perplexity/PERPLEXITY_REVIEW.md` | **Perplexity** | Après chaque checkpoint |
| `workspace/perplexity/HERMES_RESPONSE.md` | **Hermes** | Après lecture REVIEW |
| `workspace/perplexity/BOARD.md` | Perplexity | Chaque session |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Hermes | Chaque décision structurante |
| `docs/STATE.md` | Hermes | Chaque phase complète |

---

## Cycle de collaboration standard

### Étape 1 — Hermes travaille (VPS)
```
Hermes implémente une phase
→ git commit avec message structuré
→ push feat/v9-foundation-clean
```

### Étape 2 — Fondateur déclenche Perplexity
```
Fondateur écrit : "fait checkpoint @GitHub" ou "analyse dernière session Hermes"
→ Perplexity lit les derniers commits
→ Perplexity écrit son analyse dans PERPLEXITY_REVIEW.md
→ Perplexity commit directement sur Git
```

### Étape 3 — Hermes lit la review
```
Début de session Hermes :
→ git pull
→ lire workspace/perplexity/PERPLEXITY_REVIEW.md
→ appliquer les recommandations classées par priorité
→ écrire HERMES_RESPONSE.md avec les décisions prises
→ git commit
```

### Étape 4 — Boucle
```
Retour étape 1 avec les nouvelles phases
```

---

## Format commit Hermes (standard)

```
feat(v10): [phase N] — [titre court]

[Description]
[Résultats live si pertinents]
[Tests : X/X verts]
[Doctrine : R1, R2, ...]
```

## Format review Perplexity (standard)

Voir `PERPLEXITY_REVIEW.md` — toujours structuré en 4 sections :
1. ✅ Points forts de la session
2. ⚠️ Points critiques / risques détectés
3. 🔧 Optimisations suggérées
4. 🎯 Prochaine étape recommandée

---

## Déclencheurs automatiques pour Perplexity

Perplexity doit lire Git et mettre à jour PERPLEXITY_REVIEW.md quand le fondateur dit :
- "fait checkpoint @GitHub"
- "analyse dernière session"
- "review Hermes"
- "qu'est ce que tu penses de ce que Hermes a fait"
- "edge fund status"

---

## Règles de non-régression collaboration

1. **Perplexity ne modifie jamais** les fichiers `core/`, `tests/`, `scripts/` directement
2. **Perplexity écrit uniquement** dans `workspace/perplexity/`
3. **Hermes ne modifie jamais** `PERPLEXITY_REVIEW.md` — il répond dans `HERMES_RESPONSE.md`
4. **Toute décision structurante** de Perplexity → `DECISIONS_LOG.md` par Hermes
5. **Les reviews Perplexity sont additives** — jamais destructives

---

## Connexion MT5 — Standard opérationnel

MT5 ouvert sur VPS avec :
- **6 paires × 3 TF** = 18 graphiques : M30 + H1 + H4 pour GBPUSD, EURUSD, AUDUSD, USDCAD, USDCHF, USDJPY
- **M1 GBPUSD** maintenu pour delta flow ticks
- Bridge `v10_mt5_bridge.py` auto-détecte via AppData — aucune config manuelle

---

*Ce fichier est la source de vérité du protocole de collaboration. En cas de doute, il prime sur toute convention informelle.*
