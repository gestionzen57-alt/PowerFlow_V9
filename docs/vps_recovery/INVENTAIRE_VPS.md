# INVENTAIRE V9 → VPS — Ce qui doit être sur le VPS

> **Rôle** : CEO architect. Inventaire complet de tout ce que le VPS doit avoir
> pour que V9 soit opérationnel 24/7. Angles morts identifiés et résolus.
> **Date** : 2026-07-09
> **Source** : inventaire réel du PC local

---

## LÉGENDE

| Symbole | Signification |
|---------|---------------|
| ✅ | Déjà sur le VPS ou déjà dans Git |
| ⚠️ | Existe sur le PC, à transférer/créer sur le VPS |
| ❌ | Angle mort — n'existe nulle part, à créer |
| 🔴 | Critique — bloque le fonctionnement |

---

## 1. CODE — Dans Git, `git pull` suffit

| Élément | Statut | Taille | Notes |
|---------|--------|--------|-------|
| 34 scripts/ | ✅ Git | ~500KB | `git pull` |
| 39 modules core/v9/ | ✅ Git | ~1MB | `git pull` |
| 25 YAML principles/ | ✅ Git | ~50KB | `git pull` |
| 76 tests/ | ✅ Git | ~500KB | `git pull` |
| 107 docs/ | ✅ Git | ~2MB | `git pull` |
| pyproject.toml | ✅ Git | ~3KB | `git pull` |
| requirements.txt | ✅ Git | ~1KB | `git pull` |
| .gitignore | ✅ Git | ~2KB | `git pull` |

**Total Git** : ~4MB — transfert instantané.

---

## 2. EA MT4 — À compiler et transférer

| Élément | Statut | Taille | Action |
|---------|--------|--------|--------|
| `ea/V9_Sonde_TF.mq4` | ✅ Git | 15KB | Source dans Git |
| `ea/V9_Sonde_M1.mq4` | ✅ Git | 12KB | Source dans Git |
| `V9_Sonde_TF.ex4` | ❌ 🔴 | ~50KB | **À compiler** sur le VPS (MetaEditor) |
| `V9_Sonde_M1.ex4` | ❌ 🔴 | ~50KB | **À compiler** sur le VPS (MetaEditor) |

**Angle mort** : les `.ex4` ne sont pas dans Git (binaires). Il faut :
1. Installer MT4 sur le VPS
2. Copier les `.mq4` dans `MQL4/Experts/`
3. Compiler avec MetaEditor (F7)
4. Attacher sur 7 charts (M1, M5, M15, M30, H1, H4, D1)

---

## 3. CONFIG & SECRETS — Jamais dans Git

| Élément | Statut | Taille | Action |
|---------|--------|--------|--------|
| `config/telegram.json` | ⚠️ | 230B | **À copier** (BOT_TOKEN + CHAT_ID) |
| `.env` | ⚠️ | 275B | **À copier** (API keys) |
| `config/telegram.json.example` | ✅ Git | 71B | Template, pas les vraies clés |
| `.env.example` | ✅ Git | 771B | Template, pas les vraies clés |

**Angle mort** : ces fichiers sont dans `.gitignore`. Il faut les copier manuellement
sur le VPS (scp, clé USB, ou les retaper).

---

## 4. BASE DE DONNÉES — Le plus gros morceau

| Élément | Statut | Taille | Action |
|---------|--------|--------|--------|
| `data/v9_forces.db` | ⚠️ | **1.4 GB** | Trop grosse pour transfert brut |
| `data/v9_forces.zip` | ⚠️ | 330 MB | Version zippée, encore grosse |
| `data/economic_calendar.json` | ✅ Git | 1.7 KB | Dans Git |
| `data/v9_live_test.db` | ❌ | 136 KB | À recréer sur VPS |

**Angle mort critique** : 1.4 GB de DB. Solutions :
- **Option A (recommandée)** : `python scripts/v9_vps_seed.py --days 7` → DB allégée (~50MB)
- **Option B** : transférer le zip (330MB) via scp/Tailscale
- **Option C** : DB vierge, le pipeline la remplit en ~24h

**Recommandation** : Option A. 7 jours de données suffisent pour le contexte.

---

## 5. PYTHON & DÉPENDANCES

| Élément | Statut | Version | Action |
|---------|--------|---------|--------|
| Python | ⚠️ | ≥ 3.11 | VPS a souvent 3.10, vérifier |
| pip | ⚠️ | - | Aucune dépendance (stdlib only) |
| pytest | ⚠️ | ≥ 7.0 | Pour les tests, optionnel en prod |

**Angle mort** : Vérifier `python --version` sur le VPS. Si < 3.11, V9 ne tourne pas
(zoneinfo natif requis). Python 3.14.5 sur le PC, mais le VPS peut avoir une version
plus ancienne.

---

## 6. SUPERVISION & CRONS — Rien n'est installé

| Élément | Statut | Action |
|---------|--------|--------|
| Heartbeat check (5min) + alert (60min) + autorestart | ❌ 🔴 | **Scripté** : `scripts/install_v9_crons.ps1` (PowerShell, idempotent — préférer aux commandes `schtasks` manuelles ci-dessous, mêmes tâches) |
| Telegram notifier | ❌ | **À créer** : `schtasks /CREATE /TN "V9_TelegramNotifier" /SC ONLOGON /TR "python D:\Projet\V9\scripts\v9_telegram_notifier.py --watch"` |
| Daily report (23h UTC) | ❌ | **À créer** : `schtasks /CREATE /TN "V9_DailyReport" /SC DAILY /ST 23:00 /TR "python D:\Projet\V9\scripts\v9_daily_report.py --no-color"` |
| Principle alert (hourly) | ❌ | **À créer** : cron Hermes ou schtasks |
| WIN/LOSS resolver (5min) | ❌ | **À créer** : daemon ou cron |
| Auto-calibrateur (quotidien, 2026-07-13, Brief Q2) | ❌ | **Scripté** : `scripts/install_auto_calibrator_cron.ps1` — installe la tâche planifiée, **ne bascule pas** `V9_AUTO_CALIBRATOR_ENABLED` (reste à 0, propose-only, cf DECISIONS_LOG §2026-07-12 Brief Q2) |

**Angle mort critique** : **0 cron V9 installé.** Les seuls crons existants sont V8 legacy.
Sans heartbeat, si le pipeline crashe à 3h du matin, personne ne le sait avant le matin.

**Note de portée (2026-07-13)** : l'exécution réelle de ce chapitre (clone git sur le VPS,
copie des secrets, compilation EA, lancement des installateurs de cron) est une **action
opérateur** — aucune session Claude Code autopilot ne s'y connecte ni ne l'exécute à
distance sans accès VPS explicitement configuré dans cette session. Ce document reste la
checklist de référence pour l'opérateur qui effectue le déploiement.

---

## 7. TAILSCALE — Déjà sur le PC

| Élément | Statut | Adresse | Action |
|---------|--------|---------|--------|
| Tailscale | ✅ | 100.85.75.40 | Déjà actif sur le PC |
| Funnel | ✅ | https://minipc2.tail1da5a5.ts.net | Déjà actif |
| Exposition pipeline | ❌ | - | `tailscale serve --https 443 / http://127.0.0.1:31685` |

**Angle mort** : le pipeline n'est pas exposé via Tailscale. Impossible d'y accéder
depuis le téléphone.

---

## 8. WORKSPACE & MÉMOIRE — Dans Git

| Élément | Statut | Fichiers | Action |
|---------|--------|----------|--------|
| workspace/perplexity/ | ✅ Git | 43 fichiers | `git pull` |
| DECISIONS_LOG.md | ✅ Git | Append-only | `git pull` |
| ACTIVE_TASKS.md | ✅ Git | Chantiers en cours | `git pull` |
| JOURNAL.md | ✅ Git | Deltas ops | `git pull` |
| exchange.md | ✅ Git | Bus Hermes↔Zcode | `git pull` |

**Total workspace** : ~200KB — transfert instantané.

---

## 9. LOGS — À recréer sur le VPS

| Fichier | Taille | Action |
|---------|--------|--------|
| `logs/v9_capture.log` | ⚠️ | Se recrée au démarrage |
| `logs/v9_ops.log` | ⚠️ | Se recrée au démarrage |
| `logs/heartbeat.log` | ⚠️ | Se recrée au 1er heartbeat |
| `logs/telegram_notifier.log` | ⚠️ | Se recrée au 1er envoi |
| `logs/v9_resolve_daemon.log` | ⚠️ | Se recrée au démarrage |
| `logs/v9_principle_alert.log` | ⚠️ | Se recrée au 1er run |

**Angle mort** : le dossier `logs/` doit exister sur le VPS. Les fichiers se créent
automatiquement, mais le dossier doit être présent.

---

## 10. RÉPERTOIRES À CRÉER SUR LE VPS

| Dossier | Action |
|---------|--------|
| `D:\Projet\V9\` | `git clone` |
| `D:\Projet\V9\logs\` | `mkdir` (ou `git pull` le crée si .gitkeep) |
| `D:\Projet\V9\data\` | `mkdir` (ou `git pull` le crée) |
| `D:\Projet\V9\config\` | `mkdir` + copier `telegram.json` |

---

## 11. CHECKLIST DE DÉMARRAGE VPS (ordre chronologique)

```bash
# ── ÉTAPE 1 : PRÉ-REQUIS ──
python --version                    # doit être >= 3.11
git --version                       # présent
tailscale status                    # connecté au réseau

# ── ÉTAPE 2 : CLONER ──
git clone https://github.com/gestionzen57-alt/PowerFlow_V9.git D:\Projet\V9
cd D:\Projet\V9
git checkout feat/v9-foundation-clean
git pull

# ── ÉTAPE 3 : CONFIG ──
# Copier config/telegram.json (BOT_TOKEN + CHAT_ID)
# Copier .env (API keys)
mkdir -p logs data

# ── ÉTAPE 4 : DB ──
# Option A : seed 7 jours
python scripts/v9_vps_seed.py --dest data/v9_forces.db --days 7
# Option B : DB vierge (se crée au 1er démarrage)
python -c "from core.v9.db_schema import init_all_dbs; init_all_dbs()"

# ── ÉTAPE 5 : EA MT4 ──
# Installer MT4
# Copier ea/V9_Sonde_TF.mq4 et ea/V9_Sonde_M1.mq4 dans MQL4/Experts/
# Compiler (F7)
# Attacher sur 7 charts (M1, M5, M15, M30, H1, H4, D1)
# Inputs : ServerPort=31685, BrokerUTCOffsetHours=3, ShiftIndex=1

# ── ÉTAPE 6 : DÉMARRER PIPELINE ──
python scripts/v9_ops.py start
python scripts/v9_ops.py status    # vérifier
python scripts/v9_ops.py log       # vérifier le flux

# ── ÉTAPE 7 : EXPOSER VIA TAILSCALE ──
tailscale serve --https 443 / http://127.0.0.1:31685

# ── ÉTAPE 8 : CRONS ──
powershell -File D:\Projet\V9\scripts\install_v9_crons.ps1              # heartbeat check/alert + autorestart
powershell -File D:\Projet\V9\scripts\install_auto_calibrator_cron.ps1  # cycle 24h, propose-only (V9_AUTO_CALIBRATOR_ENABLED reste 0)

# ── ÉTAPE 9 : VÉRIFIER ──
python scripts/v9_supervisor.py --health
python -m pytest tests/ -q
tailscale status
```

---

## 12. RÉSUMÉ — CE QUI BLOQUE

| # | Blocage | Sévérité | Solution |
|---|---------|-----------|----------|
| 1 | **Pipeline stale** (dernier snapshot hier) | 🔴 Critique | `python scripts/v9_ops.py restart` |
| 2 | **0 cron V9 installé** | 🔴 Critique | Créer heartbeat 5min + 60min |
| 3 | **EA .ex4 non compilés** | 🔴 Critique | Compiler sur le VPS (MetaEditor) |
| 4 | **DB 1.4GB à transférer** | ⚠️ Lourd | Seed 7 jours (~50MB) |
| 5 | **Secrets à copier** | ⚠️ Manuel | telegram.json + .env |
| 6 | **Python version sur VPS** | ⚠️ À vérifier | `python --version` |
| 7 | **Pipeline non exposé Tailscale** | ⚠️ Confort | `tailscale serve` |
| 8 | **Pas de backup DB** | ⚠️ Risque | Script backup hebdo à créer |

---

## 13. CE QUI EST DÉJÀ PRÊT (rien à faire)

| Élément | Pourquoi |
|----------|----------|
| Code V9 complet | Dans Git, 34 scripts, 39 modules, 25 YAML |
| Tests (76, 873 verts) | Dans Git |
| Documentation (107 fichiers) | Dans Git |
| Kit reprise Hermes vierge | `docs/vps_recovery/` dans Git |
| Procédure Tailscale | `docs/vps_recovery/VPS_TAILSCALE_PROCEDURE.md` |
| Superviseur + heartbeat | Scripts déjà codés et testés |
| Point d'entrée unique | `v9_ops.py` (start/stop/status/boot) |
| Workspace mémoire | 43 fichiers dans Git |
| Aucune dépendance pip | 100% stdlib Python |
