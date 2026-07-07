# GAPS_RESIDUELS — Alias workspace/perplexity/

**Source canonique** : [`docs/architecture/GAPS_RESIDUELS.md`](../../docs/architecture/GAPS_RESIDUELS.md)
(Créé au commit `52e39d0` le 2026-07-07.)

Cet alias existe pour la reprise rapide via le workspace de continuité
Perplexity/Hermes. Toute modification doit être faite dans le fichier
canonique, puis reportée ici si nécessaire (synchronisation manuelle).

## État au 2026-07-07

| # | Priorité | Gap | Statut |
|---|----------|-----|--------|
| 1 | P1 | Seuils PROVISIONAL (ANTAGONISM, PLIURE) | Ouvert |
| 2 | P2 | REGIME_LOOKBACK_BARS = 20 fixe | Ouvert |
| 3 | P2 | SIMILARITY_THRESHOLD = 0.65 hérité V8 | Ouvert |
| 4 | P2 | Cross-TF direction sur max(forces) | Ouvert |
| 5 | P3 | vitesse = 1 devise seulement (proxy) | Accepté |
| 6 | P3 | REPLAY_MIN_CAS = 3 (volontaire) | Accepté |
| 7 | P3 | PLIURE_THRESHOLD proxy (P90 pente) | Accepté |
| 8 | P3 | **GAP-001 — 7 décisions orphelines** (signal_id introuvable, pré-fix 8697d84) | Archivé non bloquant |

## GAP-001 (détail)

- Détecté : `validate-coherence.py` check 2, session 2026-07-07
- IDs concernés : `dec_df961c3f104b` + 6 autres H4/M15/M1/M5 2026-07-06
- Cause probable : ancien format `signal_id` avant fix `8697d84`
- Impact : aucun sur pipeline live actuel (toutes décisions 2026-07-07 OK)
- Décision : **archivé — non bloquant Phase 10**
- Rouverture si : check 2 détecte de nouveaux orphelins post-fix

## Vérification rapide

```bash
python scripts/validate-coherence.py
# Attendus au 2026-07-07 :
#   Check 2 ERROR : 7 issues (les 7 décisions orphelines)
#   Check 4 WARNING : >0 issues (historique J-1 normal)
#   Autres : OK
# Exit code : 2 (tant que GAP-001 persiste)
```