---
name: powerflow-scene-brainstorming
description: "Méthode de co-construction avec Søn — brainstorming taxonomie fenêtres, défauts subjectifs, scénarios live"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, brainstorming, taxonomy, co-construction, søn]
statut: actif-v9
derniere_maj: 2026-07-31
---
# Powerflow Scene Brainstorming

# PowerFlow Scene Brainstorming

## Rôle
Méthode de co-construction avec Søn (style antagoniste + arbitrage) pour brainstormer sur taxonomie, défauts subjectifs, ou scénarios live. Évite le monologue LLM et l'effet "je ponds 50 options".

## Quand charger
- Création d'un nouveau type de fenêtre (A5, B2, etc.).
- Søn dit "j'ai une idée floue, on structure" ou "brainstormons".
- Défaut subjectif à borner (§3 taxonomie ancres).

## Format Søn (validé 26/06 Telegram)
**Avant d'écrire une EI (Expression d'Intention) 13 sections**, Søn demande :
- 3 options tech
- 1 recommandation
- 4 questions A-E (choix multiples bornés)

**Exemple** :
```
Søn : "faut ajouter fenêtre A3 meanrev_low"
Moi : 
  3 options :
  A. Détecteur symétrique à A2 mais filtre RSI<30/Bollinger
  B. Variante A2 + session=NY_ONLY
  C. Variante A2 + zscore_gbp<-1.5
  Reco : A (historiquement WR 64% sur meanrev)
  4 questions :
  a. TF ancre = M30 ou M15 ?
  b. Direction autorisé = SHORT uniquement ?
  c. Calibration sample = 200 ou 500 décisions ?
  d. Hardcode GBPUSD confirmé ?
```

## Livrables brainstorm
1. **EI 13 sections** (Expression d'Intention) — une fois options tranchées.
2. **Plan d'implémentation** — 1 page max, jalons chiffrés.
3. **Critères GO/NO-GO** — seuils WR, nombre tests, fenêtre évaluation.

## Pièges
- Pondre 50 options sans demander arbitrage → Søn coupe ("trop").
- Poser 4 questions ouvertes au lieu de A-E → pas actionnable.
- Oublier le hardcode GBPUSD → question (d) toujours présente.
- Brainstormer sans avoir lu BORD_M3 → redondance avec décisions passées.

## Style antagoniste
Charger en parallèle `hermes_free4` (nvidia qwen) et `hermes_free5` (nvidia nemotron) pour avoir 2 avis contradictoires avant arbitrage.

