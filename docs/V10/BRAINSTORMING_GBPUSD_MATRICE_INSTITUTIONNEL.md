# BRAINSTORMING GBPUSD — Matrice institutionnelle (Hermes ↔ Søn)

> **Mandat CEO (13/08)** : *"le cœur de la lecture du marché est dans
> l'interprétation de la cinématique et dans l'imbrication temporelle, mais
> aussi dans les coalition de multidevises … digne de grand institution de
> tuning et performance de résultat."*
>
> **Objectif** : reformuler les questions du brainstorming pour qu'Hermes
> extrait la **logique de trading institutionnel** de Søn, pas des réponses
> binaires. Le but est de transformer le "ressenti" en signaux observables,
> calibrables, et branchables dans le moteur.

> **Méthode** : Søn répond par fragments, librement. Chaque réponse devient
> une **règle de lecture** injectée dans les scripts. On reste en brainstorming
> jusqu'à ce que lecture Hermes == lecture Søn sur 10 trades consécutifs.

---

## LES 3 PILIERS DE LA LECTURE INSTITUTIONNELLE (ce qu'on cherche)

```
PILIER 1 — LA CINÉMATIQUE (la courbe avant la valeur)
   La force GBP n'est pas un nombre, c'est un mouvement.
   On cherche : pic → retombée, divergence force/prix, accélération, exhaustion.

PILIER 2 — L'IMBRICATION TEMPORELLE (H4 juge, H1 timing, M15 exécution)
   Un signal H1 seul = bruit. H4 + H1 + M15 alignés = setup institutionnel.
   On cherche : la hiérarchie des timeframes, le conflit, la confirmation croisée.

PILIER 3 — LA COALITION MULTIDEVISE (le contexte global)
   GBPUSD ne vit pas seul. GBP, USD, EUR, AUD, CHF, JPY forment un système.
   On cherche : qui mène, qui suit, qui s'oppose, quand la coalition se brise.
```

---

## MATRICE DE QUESTIONS — 3 PILIERS × 4 DIMENSIONS = 12 BLOCS

Chaque bloc contient une **question d'extraction** (pour comprendre ta logique)
et une **question de validation** (pour confronter mes règles actuelles).
Réponds dans l'ordre qui te parle le plus. Le bloc le plus important pour toi
d'abord — on s'attaque au reste après.

---

### PILIER 1 — CINÉMATIQUE (la courbe avant la valeur)

#### Bloc 1.1 — LE PIC (l'épuisement acheteur)
> **Extraction** : Quand GBP force fait un pic (ex: 78→86), qu'est-ce qui te dit
> "c'est fini, ça va retomber" ? Est-ce la **hauteur** du pic (>75 ? >80 ?),
> la **vitesse** de montée, ou le fait qu'elle **ne pousse plus malgré le prix
> qui monte encore** (divergence) ?
>
> **Validation Hermes** : ma règle actuelle dit "exhaustion = pic puis retombée".
> Est-ce que le pic seul (sans retombée encore) te fait déjà agir, ou tu
> attends toujours la retombée confirmée ?

#### Bloc 1.2 — LA DIVERGENCE FORCE/PRIX (le prix ment)
> **Extraction** : Décris-moi la dernière fois où tu as vu la force GBP faire
> un sommet **plus bas** que le précédent pendant que le prix faisait un sommet
> **plus haut**. Qu'as-tu fait ? À quel moment exact as-tu "su" que c'était un
> piège ? Quel détail visuel t'a alerté ?
>
> **Validation Hermes** : je détecte `divergence_force_price` quand le pic de
> force décline mais le prix fait un nouveau sommet. Est-ce que je dois
> exiger **deux pics décroissants** (double divergence) ou un seul suffit ?

#### Bloc 1.3 — L'ACCÉLÉRATION (la pente de la courbe)
> **Extraction** : La pente de la force (vitesse de montée/chute) t'importe-t-elle ?
> Une force qui monte lentement vers 75 vs une qui explose de 50 à 80 en 2 barres —
> est-ce que tu les traites différemment ? Laquelle te semble plus fiable pour
> vendre ?
>
> **Validation Hermes** : je calcule `slope_gbp_5` (pente sur 5 barres) et
> `acceleration_gbp` (dérivée seconde). Quel seuil d'accélération négative te
> semble être un signal d'épuisement exploitable ?

#### Bloc 1.4 — LE CREUX (le contraire du pic)
> **Extraction** : Symétriquement, quand GBP force fait un creux (ex: 28-33),
> est-ce que tu achètes ? Ou tu attends une remontée confirmée ? Un creux de
> force + prix sur support = ton signal d'achat GBPUSD ?
>
> **Validation Hermes** : je détecte `gbp_creux` mais je n'ai pas de règle
> d'achat dessus. Faut-il symétriser : exhaustion haussière = SELL_BIAS,
> exhaustion baissière = BUY_BIAS ?

---

### PILIER 2 — IMBRICATION TEMPORELLE (H4 juge, H1 timing, M15 exécution)

#### Bloc 2.1 — LA HIÉRARCHIE (qui décide ?)
> **Extraction** : Si H4 dit SELL (exhaustion + résistance) mais H1 dit BUY
> (rebound en cours), que fais-tu ? Lequel est ton juge final ? H4 donne la
> direction et H1 le timing ? Ou tu attends que les 2 alignent ?
>
> **Validation Hermes** : ma master_alert combine H4 + H1 mais les score
> indépendamment. Faut-il exiger **H4 prioritaire** (veto H4 sur H1) ou
> **confluence** (les 2 doivent aligner) ?

#### Bloc 2.2 — LE CONFLIT (le piège du faux signal)
> **Extraction** : Quand H4 et H1 sont **en conflit** (H4 baissier, H1
> haussier), est-ce que tu te dis "attends, c'est un piège" ou "le H1 va
> entraîner le H4" ? Quelle est ta règle pour résoudre un conflit de TF ?
>
> **Validation Hermes** : actuellement un conflit TF = WAIT (pas de signal).
> Est-ce que tu voudrais un signal "contre-tendance H1" qui joue le retour
> vers H4 (mean reversion) ? Ou strictement : conflit = on ne fait rien ?

#### Bloc 2.3 — LE TIMING D'ENTRÉE (quand dans la barre ?)
> **Extraction** : À quel moment précis entres-tu ? Au close de la barre H1
> qui confirme le rejet ? À l'open de la suivante ? Ou tu regardes M5/M15
> pour affiner le point d'entrée intra-barre ?
>
> **Validation Hermes** : je travaille en close de barre (post-confirmation).
> Si tu utilises M5/M15 pour l'entrée, je dois ajouter une couche
> "timing entry" qui cherche le point précis dans la barre H1.

#### Bloc 2.4 — L'IMBRICATION M15 (la granularité fine)
> **Extraction** : Est-ce que M15 t'apporte quelque chose que H1 ne t'apporte
> pas ? Vois-tu des signaux sur M15 (sweep, absorption, climax) qui confirment
> ou infirment H1 ? Ou M15 c'est trop de bruit pour toi ?
>
> **Validation Hermes** : M15 est dans le pipeline (vsa_multi_tf) mais souvent
> "unavailable_no_signal". Faut-il que je force M15 à toujours produire un
> état (même NEUTRAL) pour qu'il serve de confirmateur H1 ?

---

### PILIER 3 — COALITION MULTIDEVISE (le contexte global)

#### Bloc 3.1 — QUI MÈNE ? (leader/follower)
> **Extraction** : Quand GBPUSD monte, est-ce GBP qui est fort (leader) ou
> USD qui est faible (follower) ? Est-ce que tu distingues les deux cas ?
> Un GBPUSD qui monte parce que USD s'effondre partout = mouvement USD-driven,
> pas GBP-driven. Tu le traites comment ?
>
> **Validation Hermes** : je calcule `delta_forces = GBP - USD` mais je ne
> distingue pas "GBP mène" vs "USD traîne". Faut-il ajouter un signal
> `leader = GBP` (fort en absolu) vs `leader = USD_weak` (USD faible en absolu) ?

#### Bloc 3.2 — LA RUPTURE DE COALITION (le signal fort)
> **Extraction** : Quand toutes les devises "risk-on" (AUD, NZD, GBP) montent
> ensemble puis qu'une d'elles casse (GBP retombe pendant que AUD continue),
> est-ce que tu vends GBPUSD ? La rupture d'une coalition risk-on = ton signal ?
>
> **Validation Hermes** : j'ai `v10_market_context_global.py` (CoalitionDetector)
> mais il n'est pas branché dans l'alerte GBPUSD. Faut-il que je l'intègre :
> "GBP casse la coalition risk-on" = +3 au score ?

#### Bloc 3.3 — LE SAFE HAVEN (JPY, CHF, USD)
> **Extraction** : Quand le risk-off arrive (JPY et CHF montent, AUD et GBP
> baissent), est-ce que tu vends GBPUSD ? Est-ce que la force JPY t'alerte
> avant la chute de GBP ? Y a-t-il une séquence : JPY monte → USD monte →
> GBPUSD chute ?
>
> **Validation Hermes** : j'ai un module `v10_currency_strength` qui calcule
> les 8 devises mais je n'exploite pas la séquence JPY→USD→GBPUSD. Faut-il
> ajouter un signal "risk-off shift" basé sur JPY+CHF qui précède la vente ?

#### Bloc 3.4 — LE CROSS-PAIR (la confirmation externe)
> **Extraction** : Quand tu vends GBPUSD, est-ce que tu regardes EURUSD,
> GBPJPY, EURGBP pour confirmer ? Si EURGBP monte (GBP fort vs EUR) pendant
> que GBPUSD est sur résistance, est-ce que ça renforce ton sell ? Ou tu
> trade GBPUSD en isolation ?
>
> **Validation Hermes** : je n'utilise pas les cross-pairs pour confirmer
> GBPUSD. Faut-il ajouter : "EURGBP en divergence avec GBPUSD" = signal de
> retournement GBPUSD ?

---

## CE QUE HERMES APPRENDRA DE CHAQUE RÉPONSE

| Réponse de Søn | Injection Hermes |
|---|---|
| "Le pic seul suffit" | `exhaustion_signal = pic_forces >= SEUILL_PIC` (sans attendre retombée) |
| "H4 est mon juge" | `veto_h4 = True` dans master_alert (H1 ne peut pas contredire H4) |
| "Je regarde M15 pour entrer" | Ajout couche `entry_timing_m15` post-confirmation H1 |
| "GBP mène = signal fort" | `leader_signal = (GBP > 70 ET USD > 55)` vs `follower_signal = (GBP < 50 ET USD < 40)` |
| "La rupture de coalition risk-on = sell" | Brancher CoalitionDetector dans master_alert (+3 si rupture) |
| "JPY monte avant GBPUSD chute" | Signal `risk_off_lead = JPY_slope > +X pendant Y barres` |
| "EURGBP confirme" | Cross-pair confirmation module (v10_cross_pair_confirm) |

---

## ORDRE DE PRIORITÉ SUGGÉRÉ (si tu ne sais pas par où commencer)

Søn, si tu veux maximiser l'impact, réponde dans cet ordre — chaque réponse
débloque la suivante :

1. **Bloc 2.1** (hiérarchie H4 vs H1) — car toute la master_alert en dépend
2. **Bloc 1.1** (le pic) — car c'est ton signal d'entrée principal
3. **Bloc 3.1** (qui mène) — car le multidevise change la lecture du delta
4. **Bloc 1.2** (divergence) — car c'est ton signal anticipatif le plus fort
5. Le reste s'enchaine naturellement

Mais si une question te brûle plus qu'une autre, commence par elle. L'ordre
n'est pas une loi — c'est une suggestion pour aller vite.

---

## MÉTRIQUE DE RÉUSSITE DU BRAINSTORMING

Le brainstorming est **clos** quand :
- Lecture Hermes == lecture Søn sur 10 setups GBPUSD consécutifs (verdict
  identique : SELL_BIAS / NEUTRAL / BUY_BIAS)
- Taux de bonnes décisions anticipatives > 55% sur 30 setups
- Chaque règle extraite est testée (test pytest dédié) et documentée

---

## DOCUMENTS LIÉS

- `docs/V10/DOCTRINE_LECTURE_GBPUSD.md` — les 7 principes actuels (à enrichir)
- `docs/V10/LECTURE_GBPUSD_QUESTIONS_REGLES.md` — les 10 questions initiales
  (absorbées et étendues par cette matrice)
- `scripts/v10_gbpusd_master_alert.py` — l'alerte unifiée (réceptacle des règles)
- `scripts/v10_force_cinematics.py` — la lecture en courbe (Pilier 1)
- `core/v10/v10_market_context_global.py` — CoalitionDetector (Pilier 3, à
  brancher)

---

> **Note Hermes** : cette matrice remplace l'ancien document à 10 questions.
> Il est vivant. Chaque réponse de Søn met à jour les règles + ce document.
> Pas de loi fixe — juste l'extraction honnête de ta logique de marché.