# Brainstorm doctrinal — Biais HTF & lecture multi-sens
**Date** : 2026-07-07 15:24 CEST
**Statut** : brouillon — NE PAS Promu dans DOCTRINE.md ni core/v9/
**Source** : conversation Søn post-redémarrage MT4
**Auteur** : Hermes orchestrateur (capture seulement)

---

## Constat Søn — verbatim reformulé

1. **Le système veut tout aligné sur le HTF alors qu'il est en retard.**
   Le HTF est le TF le plus lent : si on attend sa confirmation, le mouvement
   est déjà consummé (souvent 2e jambe, voire extension 3e jambe).

2. **Tout dépend de la zone** :
   - **Naissance** (nouveau combat) → le LT peut être neutre, on lit le LT à la volée.
   - **2e jambe / continuation** → le LT doit confirmer la dynamique.
   - **Re-test / battle** → lecture différente.
   Le système actuel ne distingue pas explicitement ces 3 cas. Il applique
   un filtre cross-TF uniforme.

3. **Court terme n'empêche pas long terme — les 2 sens coexistent.**
   Un signal M5 haussier peut être valide même si H4 reste baissier.
   H4 raconte **d'où vient la rivière**, pas où elle va.
   Le « où elle va » se lit sur les TF inférieurs **pendant** qu'elle coule.

4. Le filtre actuel (ANTAGONIST_NODE + COALITION_NODE + window_gate) impose
   une cohérence HTF→LT. C'est, dans la lecture Søn, **la mauvaise vision**.

5. Métaphore : « on voit la rivière d'où elle vient mais elle continue de couler ».

---

## Tension avec la doctrine existante

- §3BIS (mémoire Hermes) : « un SDI de 75 n'est pas un événement, c'est son
  histoire d'arrivée qui donne sens ». Cohérent avec la lecture Søn.
- Mais la doctrine actuelle applique quand même un **plafond HTF first**
  via la chaîne :
  ```
  H4 state → H1 state → M30 → M15 → M5
  ```
  qui se lit comme un cascade descending, où chaque niveau peut invalider
  le précédent. Søn : c'est un biais inherited de V8 qui n'a plus lieu d'être.

- Règles 9-11 actuelles (cf. DOCTRINE.md à confirmer) sur la primauté HTF
  datent de V8 où le microstructure était moins fiable.

---

## Idées de lecture alternatives (à arbitrer par Søn)

### Idée A — Lecture par zone, pas par TF
Définir 3 régimes de zone :
- **Naissance** : LT peut être neutre, on accepte un signal LT-audible
  même si H4/H1 n'ont pas encore bougé.
- **2e jambe confirmée** : LT doit être aligné (sinon = piège/épuisement).
- **Continuation** : LT doit confirmer la direction (filtre HTF actif).

### Idée B — Temporalité symétrique
Le M5 et le H4 ne se contredisent pas : ils **parlent de temps différents**.
- H4 parle des 4h précédentes.
- M5 parle des 5 dernières minutes.
- Un signal M5 haussier pendant que H4 reste baissier n'est pas un
  « conflit », c'est un **changement en cours de digestion**.

### Idée C — Le LT s'écoute en parallèle, pas en filtre
Aujourd'hui : LT = filtre (peut invalider).
Demain (proposition Søn) : LT = contexte additionnel (peut enrichir).

### Idée D — Doctrines opposées coexistent
Dans 1 même scène :
- Un trade LT peut être baissier (LT = structure héritée).
- Un trade CT peut être haussier (naissance CT).
- Un opérateur humain arbitre le LOT SIZE / horizon en fonction de la stratégie.

---

## Implications techniques (si Søn tranche « oui, on bascule »)

À NE PAS faire sans feu vert explicite — périmètre Phase 9.7 = lecture seule.

### Fichiers concernés (théorique, hors session)
- `core/v9/arbiter.py` — fonction `consolidate()` : changer la pondération
  HTF (aujourd'hui probablement 50%+) vers 30% avec M5/M15 qui montent.
- `core/v9/exploitability_evaluator.py` — fenêtre « absente » par défaut
  quand H1/H4 non alignés. Au contraire : autoriser fenêtre « naissance CT »
  même si HTF pas aligné, avec HITL renforcé.
- `core/v9/principles/ANTAGONIST_NODE.yaml` — exige h1_state ≠ NEUTRAL.
  Peut être trop strict si H1 n'a pas eu le temps de matérialiser.
- `core/v9/principles/COALITION_NODE.yaml` — coalition_mtf_score ≥ 3
  sur 4 TF. Peut tuer les naissances CT.
- `core/v9/window_gate.py` — politique « fenêtre absente par défaut ».

### Fichiers NON concernés (gelé par règle 11)
- `core/v9/config.py` (gelé règle X)
- `core/v9/orchestrator.py` (gelé)

---

## Question pour Søn (avant tout commit doctrinal)

1. Tu confirmes que c'est bien un **biais doctrinal**, pas une option technique ?
2. Tu veux que ce document entre dans la file « à étudier après Phase 13 »
   (≥50 WIN/LOSS) ou tu veux qu'il soit traité en **urgence** (chantier dédié) ?
3. Tu l'as déjà écrit ailleurs (V8 / mémoire Perplexity / note Telegram) ?
   Si oui, je rapatrie la source — pas de re-création ex nihilo.

---

## Statut pipeline (vérifié 2026-07-07 15:24 CEST)

✅ **MT4 redémarré par Søn** — flux tick reprend :
- M5/M1 ont un nouveau snapshot récent (15:22 / 15:24 UTC) — capture repart
- Stale-rate historique reste élevé (21K anciens M5 stale dominent le %)
  mais le **flux nouveau arrive** : Forces 57K → 64K en 30 min
- M15 / M30 / H1 / H4 / D1 : ✅ propres

Sans incidence sur la discussion doctrinale — la doctrine se construit
**indépendamment** de la santé du pipeline.

---

## Référence aux sources Søn connues (mémoire)

- Doctrine V8 complétée 2026-06-15 (HTF primacy, WR patterns, false_birth_risk)
- §3BIS (Decision #148) — Doctrine LECTURE_MARCHE — 6 dimensions scène
- Vélocié_t0 = confirmation, pas trigger ; volume forex = 0 ; delta_vol proxy
- EA V8 switch 12:07 Paris 19/06/2026 ; PERIOD_M1 hardcodé V7 (cause racine résolue)
- force_usd stored inverted (100-force_usd) ; force_snapshots_v2 1 ligne/min

→ Tout ça suggère une **histoire longue** de calibration autour du même
sujet : « comment le système lit, et où il se trompe ». Ton brainstorming
d'aujourd'hui en est la suite logique.
