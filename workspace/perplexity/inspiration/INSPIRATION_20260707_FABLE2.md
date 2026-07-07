# INSPIRATION_20260707_FABLE2 — Distillation LLM via LM Studio + Hermes local

> **Statut** : Note d'inspiration (non décisionnelle). Source 100% transcript (pas de screens dédiés disponibles).
> **Source** : YouTube `P51ebCFwnss` — vidéo "Claude Fable distilled via LM Studio + Hermes" (~25 min, juillet 2026, suite de mVbwTrj1-hw)
> **Transcript** : 45 788 chars extraits via `youtube-content` skill
> **Référencé par** : `INSPIRATION_20260707_FABLE.md` (1ère vidéo), `agents/AGENTIC_MAP.md`
> **Conformité** : règle 22 — 0 code, juste cartographie doc

---

## 1. Résumé de la vidéo

Suite directe de la 1ère vidéo. Message central : **Anthropic a retiré Claude Fable/Mythos de l'abonnement**, les rendant pay-per-token. Solution : **distiller le comportement** de Fable dans un **petit modèle open-source** (4-30B paramètres) qu'on peut faire tourner **localement avec LM Studio**, et l'**intégrer dans Hermes Agent** comme provider LLM.

**4 takeaways pour V9** :
1. **Distillation = extraire le "savoir-faire" (traces, agentic patterns)**, pas la "connaissance brute" d'un modèle géant.
2. **Dataset Hugging Face** = 2.3M exemples de traces Fable (cybersec, coding, dev) — **un dataset de travail, pas de conversation**.
3. **LM Studio** = interface gratuite pour servir un modèle local via API HTTP compatible OpenAI.
4. **Hermes Agent + LM Studio** = `provider: lm-studio` + `base_url: http://localhost:1234/v1` — c'est exactement le pattern déjà documenté dans `D:/hermes/profiles/powerflow/config.yaml` (provider `ollama-local`).

---

## 2. Patterns V9 APPLICABLES tels quels (validation supplémentaire)

| Pattern vidéo | Équivalent V9 / Hermes | Statut |
|---|---|---|
| **Provider local LLM via API OpenAI-compat** | `ollama-local` provider dans `config.yaml` (D:/hermes/profiles/powerflow/) | ✅ Déjà actif |
| **Fallback chain** (modèle principal → fallback) | `fallback_providers: []` (à étoffer Phase 13) | ⚠️ Vide, à remplir |
| **Modèle 4-12B suffisant pour 80% des tâches** | qwen25-fast, phi3-fast, gemma3-fast, llama-fast | ✅ 4 modèles déclarés |
| **Quantization Q4-Q8** (compromis perf/précision) | Pas de quantization sur ollama-local (modèles pré-quantifiés) | ✅ Implicite |
| **Context length adaptatif** (RAM vs contexte) | `context_length: 65536` (openrouter/nvidia) | ✅ Configuré |
| **Distillation pour cas d'usage spécifique** | **Phase 13 (V9-trader-mini)** = distillation du comportement "lecture de marché" | 🆕 À ouvrir Phase 13 |
| **Dataset de traces (pas de conversation)** | **Future** : exporter traces V9 (signals + decisions + WIN/LOSS) | 🆕 Phase 13+ |
| **Modèle reasoning vs non-reasoning** | deepseek-v4-flash (reasoning) vs qwen3-coder-next (non) | ✅ Choix explicite dans `.env` |

→ **5 patterns sur 8 sont déjà opérationnels.** Le pattern critique "V9-trader-mini" est dans la roadmap Phase 13 (piste 3.4 de INSPIRATION_20260707_FABLE.md).

---

## 3. Idées NOUVELLES spécifiques à cette vidéo

### 3.1 Export traces V9 → dataset de distillation (Phase 13)

**Vidéo** : "A conversation dataset only teaches you how to speak. A dataset of traces learns how to work."

**V9 actuel** : `v9_forces.db` contient 43 747 snapshots + 76 décisions/24h (0 WIN/LOSS résolus). Aucun export structuré.

**Piste expansion** : un script `scripts/v9_export_traces.py` qui extrait au format JSONL :
- `snapshot_id`, `bar_time`, `symbol`, `timeframe`
- `forces_json` (8 devises), `scene_json`, `behavior_json`, `window_json`
- `principles_triggered` (ACTIVE), `signal_direction`, `signal_conf`
- `decision_id`, `decision_action`, `is_win` (quand résolu)
- `resolution_pips`, `time_to_resolution`

→ Ce JSONL devient un **dataset d'entraînement** pour un mini-modèle "V9-trader-mini".

**Complexité** : faible (1 script, 1 test). À ouvrir **uniquement si WIN/LOSS ≥ 50 résolus** (règle 25 implicite).

### 3.2 LM Studio comme provider de fallback (Phase 13+)

**Vidéo** : LM Studio sert un modèle local via `http://localhost:1234/v1` (API OpenAI-compat).

**V9 actuel** : `ollama-local` déjà configuré dans `config.yaml`. LM Studio utiliserait la même interface.

**Piste expansion** : ajouter `lm-studio` comme provider de fallback dans `config.yaml` :
```yaml
providers:
  lm-studio:
    api_key: lm-studio
    api_mode: chat_completions
    base_url: http://127.0.0.1:1234/v1
    default_model: qwen3-coder-next
    context_length: 32768
    type: openai-compatible
fallback_providers: ['ollama-local', 'lm-studio', 'openrouter']
```

**Complexité** : faible (5 LOC YAML, 0 test). À ouvrir Phase 13 si Søn veut expérimenter local.

### 3.3 Choix quantization documenté dans la doctrine (Phase 13+)

**Vidéo** : Q4-Q8 = compromis perf/précision. Q2 = trop d'erreurs, F16 = trop gourmand.

**V9 actuel** : aucun doc sur quantization. Les modèles `ollama-local` sont pré-quantifiés par Ollama.

**Piste expansion** : ajouter un §"Quantization policy" dans `docs/architecture/` ou `docs/V9_FONCTIONNEMENT.md` :
- Q4_K_M = minimum acceptable (erreurs < 5%)
- Q5_K_M / Q6_K = défaut recommandé
- Q8_0 = max précision, RAM × 2
- F16 = recherche uniquement

**Complexité** : doc only. À intégrer dans le passage Phase 13 du `V9_FONCTIONNEMENT.md`.

### 3.4 Anti-pattern à éviter : croire que "petit modèle = même qualité"

**Vidéo** : "It's not Claude Fable on your computer. This is a student model that doesn't have Professor Claude Fable's complete brain, but it has observed his gestures, choices, reflexes, and way of working."

**V9 doctrine (règle 18)** : aucune dépendance bloquante à un LLM pour le cœur cognitif. V9 = code pur (forces → scènes → ... → décision), LLM = observateur uniquement. **On ne tombera pas dans le piège** d'utiliser un petit modèle distillé pour la chaîne cognitive critique (les 9 couches). Le mini-modèle ne servirait qu'à : scoring, calibration, dialogue Telegram enrichi.

**Action** : ajouter un §"LLM usage policy" dans `V9_FONCTIONNEMENT.md` qui formalise ce que LLM peut / ne peut PAS faire dans V9.

**Complexité** : doc only.

---

## 4. Confirmation de la stratégie VPS

**Vidéo (passage clé)** : "Instead of installing paid VPS subscriptions, you have the option of installing it locally and learning how to use it there. Once you're proficient and able to create your automations and workflows, you can consider the following question: is it worth putting my Hermes online?"

→ **Validation indirecte** de ta décision : VPS 1 GB = profil contraintes. Le VPS doit servir le **cœur cognitif V9** (Python pur, ~200 MB), pas un LLM. Si un LLM est nécessaire sur VPS, c'est un petit modèle 4B local (LM Studio), pas un modèle payant via API.

**Recommandation consolidée** (mise à jour `AGENTIC_MAP.md` §5) :
- VPS = **code pur + DB + notifier** (Phase 9.8, déjà conçu)
- PC local Søn = **LLM pour chat Telegram enrichi + scoring** (qwen3-coder-next via Ollama Cloud)
- Phase 13+ = **V9-trader-mini local** (4-12B quantifié) sur PC Søn, pas VPS

---

## 5. Synthèse — ce qu'on garde, ce qu'on ouvre

### 5.1 Confirmations (rassurant, pas d'action immédiate)
- 5 patterns vidéo = déjà opérationnels dans V9/Hermes.
- VPS 1 GB = bon profil pour Phase 9.8 (code pur).
- Phase 13 (V9-trader-mini) déjà prévue dans ROADMAP.

### 5.2 Backlog d'expansion (post-Phase 11, conditionnel WIN/LOSS ≥ 50)
| # | Piste | Phase | Effort | Dépendance |
|---|---|---|---|---|
| 3.1 | `v9_export_traces.py` (dataset distillation) | 13 | faible | WIN/LOSS ≥ 50 |
| 3.2 | `lm-studio` provider fallback YAML | 13+ | faible | demande Søn |
| 3.3 | §"Quantization policy" dans doc | 13+ | doc only | aucune |
| 3.4 | §"LLM usage policy" dans doc | anytime | doc only | aucune |

### 5.3 Anti-patterns à éviter
- **Croire qu'un petit modèle peut remplacer les 9 couches cognitives** (règle 18).
- **Payer pour un LLM sur VPS** (1 GB RAM = pas de marge pour un modèle).
- **Distiller sans WIN/LOSS résolus** (dataset biaisé, modèle inutile).

---

## 6. Action concrète immédiate (sans attendre Phase 13)

**C-4 enrichi** : ajouter un §"LLM usage policy" dans `V9_FONCTIONNEMENT.md` (point 3.4 ci-dessus).
- Effort : 20 lignes de doc.
- Risque : 0.
- Permet de **formaliser la règle 18** pour les futurs agents (Zcode, Claude Code, etc.).

→ Je l'intègre dans le même commit C-4 que je viens de faire, via patch.

---

## 7. Références

- Transcript complet : `/tmp/transcript2.txt` (45 788 chars)
- 1ère vidéo (loop engineering) : `INSPIRATION_20260707_FABLE.md` (déjà commité `1996fa2`)
- Vidéo source : https://www.youtube.com/watch?v=P51ebCFwnss
- Modèles locaux Hermes : `D:/hermes/profiles/powerflow/config.yaml` (providers ollama-local, openrouter, nous, nvidia)
- Phase 13 V9-trader-mini : `INSPIRATION_20260707_FABLE.md` §3.4 + `AGENTIC_MAP.md` §3

---

**Note close — V9 confirmé cohérent avec l'état de l'art distillation 2026.**
**Prochaine action : enrichir V9_FONCTIONNEMENT.md avec LLM usage policy + quantization policy.**