# GAPS RÉSIDUELS — PowerFlow V9

## Rôle
Inventaire des écarts connus, non-bloquants, entre l'implémentation actuelle
de V9 et l'état idéal défini par la doctrine. Chaque gap est priorisé,
justifié, et associé à une condition de résolution.

**Règle** : un gap non documenté est un bug non diagnostiqué.
Un gap documenté sans priorité est un chantier fantôme.

Mis à jour à chaque session identifiant un nouvel écart ou résolvant un gap existant.

---

## Contexte
Ces gaps sont identifiés lors de la session de calibration du 2026-07-06
et confirmés sur n=22 438 forces live (session Asie → Tokyo → pré-London).
Ils sont **non-bloquants** pour la poursuite de la Phase 9.6 mais doivent
être résolus avant l'ouverture de la Phase 10.

---

## Inventaire

### P1 — Bloquant pour Phase 10 (résolution requise avant déblocage)

| # | Gap | Détail | Condition de résolution |
|---|-----|--------|------------------------|
| 1 | **Seuils PROVISIONAL** | `ANTAGONISM_THRESHOLD` (31.39) et `PLIURE_THRESHOLD` (1.7) sont PROVISIONAL — instables sur 3 runs Hermes (écart inter-run > 0.5). `COALITION_THRESHOLD` (5.38) est le seul seuil appliqué. | n>10 000 scènes live + convergence 3 runs consécutifs + WIN/LOSS ≥ 20 trades résolus (doctrine règle 25). |

### P2 — Amélioration calibrée (session dédiée requise)

| # | Gap | Détail | Condition de résolution |
|---|-----|--------|------------------------|
| 2 | **REGIME_LOOKBACK_BARS = 20 fixe** | Identique pour tous les timeframes (M5, M15, H1, H4, D1). Un M5 à 20 bars = 100 min, un H1 à 20 bars = 20h — la même fenêtre n'a pas la même signification. | Session de calibration dédiée : déterminer `REGIME_LOOKBACK_BARS` par TF via analyse de sensibilité sur données live. |
| 3 | **SIMILARITY_THRESHOLD = 0.65** | Seuil de similarité entre comportements hérité de V8, jamais recalibré sur les données V9. Impact direct sur le bonus de confiance dans `BehaviorAnalyzer.analyze_scene` (Anomalie #1). | Recalibration sur n>5 000 comportements V9 avec analyse de distribution des scores de similarité. |
| 4 | **Cross-TF direction sur max(forces)** | La direction cross-TF (h1_dir, m5_dir) est déterminée par la devise avec la `force` maximale — approximation qui ignore les cas d'équilibre ou de forces multiples alignées. | Implémenter une détection plus robuste (consensus de devises, seuil de majorité, ou weighted vote). |

### P3 — Accepté (non-bloquant, proxy suffisant)

| # | Gap | Détail | Justification |
|---|-----|--------|---------------|
| 5 | **vitesse = 1 devise seulement** | La colonne `vitesse` dans `forces_snapshots` est calculée par devise individuelle (ex: `force_gbp`), pas comme un panier des 8 devises. Le proxy utilisé par `scene_builder._compute_cinematics` est donc partiel. | Proxy acceptable pour la vélocité relative. Un panier complet nécessiterait une refonte de `forces_reader.py` (hors périmètre Phase 9). L'erreur est systématique et ne masque pas de signal. |
| 6 | **REPLAY_MIN_CAS = 3** | Le nombre minimum de cas de replay pour valider une exploitabilité est fixé à 3. En live naissant (0 replay disponible), cela applique un malus systématique à toutes les décisions. | **Volontaire** — doctrine règle 25 : ne pas masquer l'incertitude. Le malus disparaît naturellement à mesure que les cas de replay s'accumulent. **INTERDICTION** de passer à 1 (masquerait l'absence de précédents). |
| 7 | **PLIURE_THRESHOLD proxy** | Le seuil de pliure (1.7) est calibré via `_pliure_deltas_from_scenes()` qui utilise `abs(pente_t - pente_t-1)` comme proxy. La vraie pliure (changement de régime) n'est pas directement mesurée. | Proxy validé sur n=1 454 scènes M5+ (P90 des deltas de pente). Une mesure directe nécessiterait une couche de détection de changement de régime (Phase 10+). |

---

## Suivi

| Date | Action |
|------|--------|
| 2026-07-07 | Création du document. Gaps identifiés lors de la calibration post-London open (n=22 438). |
| — | — |

## Règle de mise à jour
- Un gap est **résolu** quand son code est livré ET que les tests associés passent.
- Un gap est **dépriorisé** quand une décision explicite le rétrograde (ex: P2→P3).
- Un gap est **fermé** quand la condition de résolution est remplie ET que le commit de fermeture référence ce document.
