# LECTURE GBPUSD — Questions & Règles (brainstorming Hermes ↔ Søn)

> **Statut** : brainstorming actif (2026-08-11). Document vivant.
> Objectif : aligner la lecture de l'indicateur Fatman entre Søn (pertinence
> humaine apprise) et Hermes (mécanique algorithmique). Chaque réponse de Søn
> devient une règle de lecture. Chaque règle d'Hermes est exposée pour que Søn
> la valide/corrige.
>
> Trade : **GBPUSD exclusivement**. R10 : lecture only, zéro ordre réel.

---

## PARTIE A — MES QUESTIONS (pour extraire ta logique, Søn)

Ces questions sont ce que je me pose pour rendre mes décisions claires.
Réponds librement, même par fragments. Chaque réponse devient une règle.

### A1. Le moment exact de vente
- Quand GBP force est à 76-80 et le prix au plus haut, qu'est-ce qui te fait
  passer de "il monte encore" à "c'est le moment de vendre" ?
- C'est le niveau ABSOLU de la force (ex: >75) ? Le fait qu'elle RETOMBE
  (momentum DOWN) ? Ou un signe sur le prix lui-même (ombre, close) ?

### A2. H4 vs H1 (le juge)
- Quand H4 est vendeur mais H1 acheteur, que fais-tu ?
- Lequel est ton juge final ? Le H4 donne-t-il la direction, le H1 le timing ?

### A3. Le rejet (confirmation)
- Tu vends dès que le prix touche le niveau avec force extrême ?
- Ou tu attends un REJET visible : ombre haute, close sous le niveau,
  bougie baissière après le sommet ?

### A4. L'anomalie / divergence
- Quelle lecture te semble "cassée" et te pousse à agir ?
- Ex: force GBP très haute mais prix qui ne monte plus (divergence) ?
- Ex: force qui retombe vite après un pic (épuisement) ?

### A5. Le niveau de force "sain" vs "extrême"
- À partir de quelle force GBP considères-tu le marché "surchauffé" ?
- Y a-t-il une zone où la force est trop haute pour continuer ?

### A6. Le timing intraday
- Y a-t-il des heures où tu préfères vendre GBPUSD (Londres, NY, Overlap) ?
- Évites-tu certaines heures (Asie, news) ?

### A7. Le stop et la cible
- Où mets-tu ton SL quand tu vends un pic ? (au-dessus du sommet ?)
- Quelle est ta cible ? (niveau de support, ratio, pips fixes ?)

### A8. Le contexte macro
- Tiens-tu compte des news / calendrier économique pour GBPUSD ?
- Un choc (BoE, NFP, CPI) invalide-t-il ta lecture technique ?

### A9. La force des autres devises
- La force USD compte-t-elle ? (GBP fort + USD faible = GBPUSD monte)
- Ou tu ne regardes que GBP ?

### A10. Le sentiment / ressenti
- Tu as dit "je le lis par sentiment et ressenti". Peux-tu décrire ce
  ressenti en mots ? (ex: "le prix fatigue", "la force ment", "il pousse
  mais ne casse pas")

---

## PARTIE B — MES RÈGLES DE LECTURE ACTUELLES (ce que je sais)

Ce que mon lecteur fait aujourd'hui. Dis-moi ce qui est juste, faux, ou à
affiner. C'est la base que ta pertinence va corriger.

### B1. Fatman (forces)
- `get_fatman_live(GBPUSD, H4)` lit les forces réelles de la DB.
- GBP force >= 65 → "très fort" (potentiel épuisement).
- GBP force >= 60 ET momentum DOWN → "épuisement acheteur".
- Rang GBP parmi 8 devises (1 = plus fort).

### B2. Niveaux (structure)
- Détection de résistances : swing highs (hauts locaux) + clusters.
- Prix à <= 25 pips d'une résistance → "sur résistance".
- Prix à <= 30 pips d'une résistance H4 → "à résistance majeure".

### B3. Rejet (confirmation de vente)
- Rejet confirmé = bougie qui touche la résistance PUIS close sous le niveau
  avec close < open. → score +3 (fort signal de vente).

### B4. Momentum
- Pente des closes H1 sur 10 barres. Négative → biais vendeur.

### B5. VSA
- État (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION/NEUTRAL).
- Stopping / climax / no_demand → signaux d'épuisement.

### B6. Score de confluence (alerte)
- Fatman fort (+1) + momentum DOWN (+1) + sur résistance H4 (+1) + sur
  résistance H1 (+1) + rejet (+3) + momentum H1 négatif (+1).
- Score >= 4 → STRONG → alerte Telegram.
- Score 2-3 → MODERATE. Score < 2 → WEAK.

### B7. Verdict actuel (11/08)
- GBPUSD H4 : GBP 76, momentum DOWN, sur résistance 1.35059 (0 pip),
  position range 87% → **SELL_BIAS** (pic + résistance majeure).
- VSA pas encore de climax confirmé → rejet à confirmer.

---

## PARTIE C — CE QUE JE NE SAIS PAS ENCORE (à apprendre de toi)

1. Le seuil exact de "force extrême" qui déclenche ta vente.
2. La hiérarchie H4 vs H1 dans ta décision.
3. Ta définition précise du "rejet" que tu attends.
4. Les heures que tu privilégies pour vendre GBPUSD.
5. Ton ratio SL/TP et ta gestion du risque.
6. Comment tu intègres le contexte macro.
7. Ton "ressenti" traduit en signaux observables.

---

## PROCHAINE ÉTAPE
Chaque réponse de Søn dans la Partie A est intégrée comme règle dans
`scripts/v10_gbpusd_alert.py` et `scripts/v10_market_reader_gbp.py`.
Le document est mis à jour à chaque itération. On reste en brainstorming
jusqu'à ce que la lecture Hermes == lecture Søn.
