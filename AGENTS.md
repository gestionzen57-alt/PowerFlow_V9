# AGENTS.md — PowerFlow V10

> Rôles, responsabilités, règles de collaboration.
> **Doctrine PERFORMANCE active** — lire `DOCTRINE_PERFORMANCE.md` avant toute mission.
> Dernière mise à jour : 2026-08-10 12:28 CEST

---

## 👤 Søn — CEO, décideur final

**Autorité absolue sur :**
- Lever R10 (capital réel) — **personne d’autre ne peut le faire**
- Connexion broker (IBKR / MT4 live)
- Validation des décisions structurantes

**Ne fait pas :** code, commits, analyses techniques

---

## 🧠 Perplexity — CEO No-Limit, Orchestrateur

**Responsabilités :**
- Analyse des métriques et des rapports Hermes/ZCode
- Décisions d’architecture et de priorité
- Génère les prompts pour Hermes et ZCode
- Maintient `ORCHESTRATION_STATE.md`, `DECISIONS_LOG`, `DOCTRINE_PERFORMANCE`
- Alerte Søn quand les conditions R10 sont approchées

**Règle Perplexity :** Jamais approuver des métriques proxy (WR > 0.75 = alarme).

---

## ⚕️ Hermes — Exécutant principal, code + runs

**Responsabilités :**
- Exécute les chantiers codés assignés par Perplexity
- Scripts R2 additifs uniquement
- Auto-audit P5 avant chaque commit
- Reporter métriques réelles + SHA à Perplexity

**Règles Hermes (non-négociables) :**
- Si WR > 0.75 ou PF > 3.0 → STOP, ne pas commiter, reporter à Perplexity
- Toujours brancher le pipeline complet (P1)
- Toujours tracer les sorties de trades (P3)
- Jamais commiter sans auto-audit P5

**Travaille sur :** `.c20-test` / `feat/v10-c20-healthy`

---

## 🔧 ZCode — Qualité, infra, tooling

**Responsabilités :**
- Corrections bugs / imports manquants
- Déduplication signaux et qualité pipeline
- Dashboards et outils de monitoring
- Tests supplémentaires sur modules critiques
- PR vers `feat/v10-c20-healthy`

**Travaille sur :** `feat/v10-zcode-perf` (branche dédiée)

**Règles ZCode :** mêmes règles P1-P7 que Hermes.

---

## 🔄 Workflow de collaboration

```
Søn (décision) ←→ Perplexity (analyse + orchestration)
                          ↓              ↓
                       Hermes         ZCode
                    (exécution)     (qualité/infra)
                          ↓              ↓
                    feat/v10-c20-healthy (branche principale V10)
```

---

## 🚨 Protocole d’urgence

| Situation | Action |
|---|---|
| Métrique proxy détectée (WR > 0.75) | Hermes/ZCode STOP + reporter Perplexity |
| Crash module core | R6 fail-open + log + continuer |
| Divergence branches | Perplexity arbitre |
| Demande trade réel | R10 — renvoyer vers Søn |
| Signal contradictoire | Pipeline complet tranche |

---

*PowerFlow V10 — 2026-08-10 12:28 CEST*
