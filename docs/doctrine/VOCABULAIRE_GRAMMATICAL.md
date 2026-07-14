# Vocabulaire grammatical V9 — Principes kind: grammar sans conditions

## Identification
- **Date** : 2026-07-08
- **Branche** : `feat/v9-foundation-clean` (post-Phase 9.10.1 + 14b)
- **Doctrine** : R25' reformulée 2026-07-08 Phase 9.8 B2

---

## Contexte doctrinal

R25' (Règle 25 reformulée) énonce :
> Les principes `kind: grammar` sont du **vocabulaire descriptif de lecture**,
> pas des hypothèses de rentabilité à valider statistiquement. Promotion
> SHADOW → ACTIVE conditionnée à la maturité structurelle (conditions
> réellement écrites + champs contexte PROPAGÉS + décision Søn tracée,
> sauf mandat CEO explicite contraire)
> *(R25' assoupli 2026-07-14, DOCTRINE.md)*
> — jamais à un hit_rate arbitraire.

**Conséquence directe** : un principe `kind: grammar` sans `conditions:`
n'est **pas un bug ni un DORMANT** (au sens R27). C'est une **entrée
documentaire** du vocabulaire de la scène. Il peut déclencher 0 fois
pendant 3 jours, 3 mois ou 3 ans sans que cela pose problème.

---

## Liste des 12 principes vocabulaire (kind: grammar, conditions vides)

| Principe | Origine | Statut | Verdict readiness |
|---|---|---|---|
| GRAMMAR_ABSORPTION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_ANTAGONISME | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_COALITION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_CROISEMENT | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_EXHAUSTION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_EXTENSION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_LEADER_FOLLOWER | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_LOCK | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_OPPOSITION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_RESPIRATION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_SQUEEZE | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |
| GRAMMAR_TENSION | V6 | SHADOW (vocabulaire) | `INERT_NO_CONDITIONS` — **normal** |

**Note** : `GRAMMAR_GRAVITE` et `GRAMMAR_INVERSION` (autres V6 grammar)
sont déjà **archivés** (Phase 9.8 B5, classe C MIGRATION_POLICY,
donnée source V9 absente — voir `core/v9/principles/_archive/ARCHIVE_MANIFEST.md`).

---

## Justification du maintien en SHADOW (anti-archivage)

### Pourquoi NE PAS archiver ?

1. **R25' prime sur l'efficacité** : un vocabulaire est par définition
   inerte (pas de signal à valider). L'efficacité n'est pas le critère.

2. **R27 (DORMANT) ne s'applique PAS** : R27 concerne les **champs
   contexte DORMANT** (entrées de `_load_shared_context` avec valeur
   par défaut jamais produite). Les 12 principes n'ont pas de champ
   contexte — ce sont des descripteurs YAML, pas des champs.

3. **R8 n'autorise pas l'archivage de vocabulaire** : R8 limite la
   modification de `principles/*.yaml` à la doctrine. L'archivage
   massif des 12 = perte de vocabulaire = violation de la complétude
   grammaticale (CHARTE §1.2 liste 19 termes de grammaire).

4. **Test de la complétude** : si un opérateur ou un agent veut
   annoter manuellement un pattern avec "ANTAGONISME" ou "TENSION",
   la présence du YAML permet de l'indexer. Archiver = perdre cette
   capacité.

### Coût du maintien

- **~0 ligne DB par cycle** : `principle_evaluations` n'est peuplé
  QUE pour les principes avec conditions. Les 12 sans conditions
  = 0 ligne ajoutée. (Confirmé par AUDIT_DB §5 : 0/65555+ triggers
  pour les SHADOW inertes.)
- **~0 CPU** : `evaluate_condition` retourne immédiatement
  `conditions: []` → court-circuit à 1 ligne.
- **Lisibilité** : la table des 25 fichiers (11 ACTIVE + 14 SHADOW
  + 2 archivés) reste lisible. 14 SHADOW dont 12 vocabulaire
  + 2 avec conditions (GRAMMAR_BREAK, GRAMMAR_PULLBACK refondu Phase 14b).

---

## Alternative considérée : archivage massif

**Si Søn veut malgré tout archiver** (par souci de minimalisme), la
procédure serait :
1. Backup MD5 du dossier `core/v9/principles/` complet
2. Déplacer les 12 YAML vers `core/v9/principles/_archive/`
3. Mettre à jour `ARCHIVE_MANIFEST.md` avec raison
4. Ajouter entrée DECISIONS_LOG CEO datée
5. Risque : violation R25' (vocabulaire = descripteur, pas signal),
   violation R8 (modification massive YAML sans décision tracée),
   perte de complétude CHARTE §1.2

**Recommandation CEO** : **NE PAS archiver**, maintenir le vocabulaire
en SHADOW conformément à R25'. Si Søn insiste, décision explicite
datée nécessaire (pas d'archivage silencieux).

---

## Suivi dans le temps

- **Phase 9.8 B2** (2026-07-08) : R25' reformulée → SHADOW sans
  conditions = vocabulaire (pas bug)
- **Phase 13 readiness** (2026-07-08) : verdict `INERT_NO_CONDITIONS`
  = état normal, pas une alerte
- **Phase 14b** (2026-07-08) : refonte GRAMMAR_PULLBACK résout le
  bottleneck du `BLOCKED_NO_TRIGGER` ; les 2 conditions-écrites
  (BREAK + PULLBACK) restent en cours d'accumulation de triggers
- **Phase 15+** : à chaque checkpoint, vérifier que le vocabulaire
  (12) reste intact, et que les 2 avec conditions (BREAK + PULLBACK)
  accumulent des triggers. Si PULLBACK passe à ≥50 triggers, évaluer
  promotion R30 + R25'.

---

## Références

- `docs/DOCTRINE.md` R25' (vocabulaire descriptif, promotion structurelle)
- `docs/DOCTRINE.md` R27 (DORMANT — ne s'applique pas aux principes)
- `docs/doctrine/CHARTE_COGNITIVE_V9.md` §1.2 (vocabulaire 19 termes)
- `core/v9/principles/_archive/ARCHIVE_MANIFEST.md` (2 archivés existants)
- `docs/calibration/AUDIT_DB_20260708.md` §5 (vérification empirique
  0/65555+ triggers pour les 12, confirme que c'est de l'inertie
  structurelle et non un bug)
- `docs/calibration/PHASE_9_10_1_CALIBRATION_20260708.md` (rapport
  readiness post-promo GC)
- DECISIONS_LOG §« Phase 14b : refonte GRAMMAR_PULLBACK » (référence
  au pattern de refonte pour PULLBACK, applicable à BREAK si besoin)

---

*Généré par Hermes (Claude Sonnet) — CEO architect, mode Y
proactif. 2026-07-08, branche `feat/v9-foundation-clean`.*
