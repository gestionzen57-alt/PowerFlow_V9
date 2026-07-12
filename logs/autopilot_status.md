# V9 AUTOPILOT STATUS — nuit du 2026-07-13

Mandate : Søn « go autopilot stratégique quant senior, enchaîne P1→P6 ».

## Telegram status — limitation honnête (R6)

Le token runtime Telegram n'est PAS dans `config/telegram.json` (placeholder
sanitisé `8932306765:***` visible, donc faux). Le vrai token est détenu par
un daemon runtime externe (variable d'environnement ou fichier séparé)
inaccessible depuis cette session Hermes. Test direct `getMe` → 404 Not Found.
`telegram_notifier.send_telegram` retourne False silencieusement.

**Conséquence** : pas de notification Telegram live pendant cette session.
Status déposé **uniquement** dans ce fichier. À lire en fin de session, ou
surveille `git log` en parallèle pour suivre les commits.

## Plan d'exécution — 6 actions prioritaires CEO 2026-07-13

| # | Action | Cible | Effort | Statut |
|---|--------|-------|--------|--------|
| P6 | vol_regime (nouveau module `core/v9/vol_regime.py`) | Calcule `vol_regime ∈ {LOW,NORMAL,HIGH,EXTREME}` sur ATR-30bars. Branché dans `_load_shared_context()` pour rendre le bloc YAML `vol_regime != EXTREME` opérationnel | 3-5h | ⏳ En cours |
| P1 | DYNAMIC dans le live (`signal_generator.py`) | Au lieu de `signal=None` quand window.absente + conf haute, insérer la stratégie `DYNAMIC` avec profil par session (Asie/London/Overlap/NY/After). Quick-win WR asie 84% vs TP_SL fixe ~40% | 6-8h | ⏳ Après P6 |
| P3 | Adaptive Thresholds | Seuils `COALITION/ANTAGONISM/CONFIANCE_MIN` modulés par `f(vol_implicite_30bars, news_proximity)`. Plus tard — chantier dédié | 8-12h | ⏳ Demain |
| P4 | Event Calendar dynamique | `data/economic_calendar.json` avec events + impact scoring 1-3. `news_context.py` enrichi pour éviter 30min autour NFP/CPI | 6-8h | ⏳ Demain |
| P5 | Long-term memory | `behavior_analyzer.load_history(limit=500)` au lieu de 50 | 4-6h | ⏳ Demain |
| P2 | Shadow mode parallèle | Pipeline doublé, publie tout dans `hitl_reviews` sans bloquer. Infrastructurel lourd | 16-24h | ⏳ J+2 |

## Règles doctrinales tenues
- R8 — backup MD5 avant chaque modif d'un `core/v9/*` existant
- R18 — 0 LLM dans la boucle critique
- R22 — un chantier = un commit (pas de mélange)
- R26 — tests verts avant chaque commit
- R25' — pas de promotion auto basée sur hit_rate

## Commits prévus

```
<P6 commit>  feat(v9): P6 vol_regime module — LOW/NORMAL/HIGH/EXTREME sur ATR-30bars
<P1 commit>  feat(v9): P1 signal_generator integrates DYNAMIC exit-strategy by session
```

## Session log

(Les commits seront marqués ici au fur et à mesure.)
