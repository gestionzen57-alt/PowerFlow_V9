# V9 Principle Context Enrichment

> Skill compact. Voir `powerflow-v9-principle-context-enrichment` pour l'intégral.

## 3 enrichissements

### B1 — coalition_strength (pour COALITION_NODE)

```python
coalition_strength = (len(aligned_devises) / 8.0) * (total_intensity / len(coalitions) / 50.0)
```

### B2 — Cross-TF H1/M5 (pour ANTAGONIST_NODE)

| Force | state | dir |
|-------|-------|-----|
| > 60 | HAUSSIERE | HAUSSIERE |
| < 40 | BAISSIERE | BAISSIERE |
| else | NEUTRAL | NEUTRE |

### B3 — absorption_factor (zone_detector)

```python
absorption_factor = tension * 0.4 + pullbacks * 0.3 + normalized_bars * 0.3
```

## 13 nouveaux champs (session 2026-07-06)

| Famille | Champs |
|---------|--------|
| Coalition MTF | `coalition_mtf_score`, `coalition_mtf_depth` |
| Coalition rotation | `coalition_rotation_detectee`, `ancien_leader`, `nouveau_leader` |
| Risk assessment | `risk_sentiment`, `risk_confidence`, `risk_on_score`, `risk_off_score`, `persistance_confirmee` |
| Bascule | `bascule_detectee`, `bascule_devise_dominante`, `bascule_intensite` |
| Contexte temporel | `session_marche`, `heure_utc`, `jour_semaine`, `marche_ouvert` |

## État des principes

| Principe | Statut |
|----------|--------|
| 9 node_rule ACTIVE | ✅ Tous déclenchables |
| GRAMMAR_REGIME | 📄 Grammar (n'émet jamais) |
| 12 SHADOW vocabulaire | 📄 Conditions vides (normal par R25') |
