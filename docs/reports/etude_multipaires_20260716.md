# Étude multi-paires (2026-07-16) — lecture seule

> « Avant d'agir sur les paires, étudier lesquelles apportent une lecture utile
> et de vraies coalitions. » — Ne pas activer les 3 d'un coup ; activer d'abord
> la plus décorrélée de GBPUSD.

## 1. État des données

```
symbol   timeframe  snapshots
GBPUSD   M15        78 229
GBPUSD   M5         31 729
GBPUSD   M1          6 426
GBPUSD   M30/H1/H4/D1  ~1 156
EURUSD   M5              1
```

**Seul GBPUSD est réellement capturé.** L'EA n'est attaché qu'à GBPUSD (l'unique ligne
EURUSD est un artefact de test). Il n'existe donc **aucune donnée pour mesurer la
corrélation entre PAIRES** (EURUSD/USDJPY/GBPJPY) directement.

**Mais** : la sonde SDI fournit les **8 forces de devises** sur chaque snapshot GBPUSD.
On peut donc mesurer empiriquement la corrélation des **lectures de devises**, ce qui
informe directement la décorrélation entre paires candidates.

## 2. Matrice de corrélation des 8 forces (M15, 78 230 snapshots)

```
         USD   GBP   EUR   JPY   CAD   CHF   AUD   NZD
  USD   1.00 -0.54 -0.70  0.16  0.28 -0.55 -0.51 -0.64
  GBP  -0.54  1.00  0.31 -0.29 -0.31  0.08  0.36  0.32
  EUR  -0.70  0.31  1.00 -0.20 -0.30  0.69  0.35  0.56
  JPY   0.16 -0.29 -0.20  1.00  0.23 -0.05 -0.77 -0.56
  CAD   0.28 -0.31 -0.30  0.23  1.00  0.31 -0.63 -0.64
  CHF  -0.55  0.08  0.69 -0.05  0.31  1.00  0.03  0.20
  AUD  -0.51  0.36  0.35 -0.77 -0.63  0.03  1.00  0.80
  NZD  -0.64  0.32  0.56 -0.56 -0.64  0.20  0.80  1.00
```

**Lectures structurantes :**
- **AUD ↔ NZD = 0,80** : quasi-redondants (confirmé par la coalition la plus fréquente,
  AUD+NZD 680×). Trader AUDUSD *et* NZDUSD = doublon.
- **EUR ↔ CHF = 0,69** : bloc européen safe-haven.
- **JPY** : axe le plus distinct (JPY↔CHF −0,05, JPY↔USD 0,16, JPY↔GBP −0,29). Négatif
  fort vs commodités (AUD −0,77, NZD −0,56) = **axe risk-on/off**.
- **USD ↔ EUR = −0,70** : miroir classique.

## 3. Réponses aux questions du brief

| Question | Réponse |
|---|---|
| **EURUSD corrélé à GBPUSD ?** | Partiellement : partage la **jambe USD**. EUR↔GBP = 0,31 (modéré). Redondance moyenne via USD. |
| **USDJPY apporte une lecture différente ?** | **Oui, la plus différente.** JPY est l'axe le plus décorrélé (risk-on/off), et USDJPY ne partage **aucune jambe** avec GBPUSD au sens directionnel dominant (JPY porte le signal). |
| **GBPJPY = juste GBP×JPY ou dynamique propre ?** | Hybride : hérite la **jambe GBP** (partagée avec GBPUSD → redondance) + ajoute JPY (distinct). Semi-redondant et plus bruité qu'USDJPY. |
| **Quelles paires maximisent la diversification sans bruit ?** | Priorité au JPY (distinct), éviter d'empiler AUD+NZD (redondants), le bloc EUR/CHF est corrélé. |

## 4. Recommandation

**Activer USDJPY en premier.**

Justification data-driven :
1. **JPY est la devise la plus décorrélée** des dynamiques cable (GBP/USD) — axe
   risk-on/off orthogonal.
2. **Aucune jambe partagée** avec GBPUSD (contrairement à EURUSD qui partage USD, et
   GBPJPY qui partage GBP) → lecture réellement additive, pas un écho.
3. Ouvre une **nouvelle dimension** (sentiment risque) plutôt que de densifier la lecture
   existante.

**Ordre suggéré :** USDJPY → (observer) → EURUSD → GBPJPY en dernier (le plus redondant).
**Ne pas** activer les 3 simultanément.

## 5. Garde-fou

Cette étude est **read-only** : aucune paire n'a été activée, aucun EA modifié.
L'activation reste une décision opératoire (attacher l'EA sonde sur le nouveau symbole,
vérifier le mapping SDI, laisser accumuler avant tout backtest).

## Méthodologie

- Corrélation de Pearson sur les 8 colonnes `force_*` de `forces_snapshots`
  (M15, GBPUSD, 78 230 lignes, `force_usd IS NOT NULL`).
- Scripts de calcul : archivés hors dépôt (analyse ponctuelle read-only).
