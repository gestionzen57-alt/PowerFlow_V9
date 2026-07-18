# SKILL — Market Open V9

**Version** : 2026-07-18 (resync HEAD 26b0070)

---

## Heures marché Forex (faits gravés)

| Session | Ouverture UTC | Fermeture UTC |
|---|---|---|
| **Semaine** | Dimanche 22:00 | Vendredi 22:00 |
| Tokyo | 23:00 | 08:00 |
| Londres | 07:00 | 16:00 |
| New York | 12:00 | 21:00 |

**Réouverture hebdo** : dimanche 22h UTC = **lundi 00h00 Paris (CEST)**

**Règle P0** : Ne jamais diagnostiquer daemon mort ou absence de snapshots pendant la fermeture weekend. L'absence de données vendredi 22h → dimanche 22h UTC est **normale**.

## Checklist Market Open (dimanche ~22h UTC)

1. `git pull` sur VPS (branche `feat/v9-foundation-clean`)
2. Redémarrer capture_server : `python scripts/capture_server.py &`
3. Vérifier daemon actif sur port 31685
4. Attendre premier snapshot frais (< 5 min après ouverture)
5. Vérifier décisions GBPUSD → toutes directions haussières (long_only actif)
6. Vérifier Telegram Ipspx_bot : pas de flood, LLM OpenRouter actif
7. Log dans `docs/monitoring/MONITORING_LONG_ONLY_2026-07-18.md` (T+1 semaine Phase B)

## État kill switches au restart

```bash
# Vérifier l'état réel avant restart
cat config/v9_kill_switches.env
# Attendu :
# V9_GBPUSD_LONG_ONLY=1   ← doit être ON
# V9_BEAR_PERCEPTION_ENABLED=0  ← SHADOW
# V9_EXECUTION_ENABLED=0  ← INTERDIT
```

## Infrastructure VPS

- Tout le runtime sur VPS (plus PC local depuis ~1 semaine)
- Plateforme : **MT4** (≠ MT5) — EA MT4 → daemon Python
- Bot Telegram : `Ipspx_bot`, `TELEGRAM_BOT_TOKEN_IPSPX` dans `.env`
- LLM : OpenRouter `tencent/hy3:free`, clé `OPENROUTER_API_KEY`
