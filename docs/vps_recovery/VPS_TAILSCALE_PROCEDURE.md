# VPS_TAILSCALE_PROCEDURE.md — Tailscale + Conteneurs PowerFlow V9

> **Statut** : Procédure de déploiement Tailscale pour le VPS PowerFlow V9.
> **Prérequis** : VPS avec Python 3.11+, Git, pipeline V9 opérationnel.
> **Date** : 2026-07-09

---

## 1. Pourquoi Tailscale sur le VPS V9 ?

| Usage | Sans Tailscale | Avec Tailscale |
|-------|---------------|----------------|
| Voir le dashboard depuis le téléphone | ❌ Impossible (port 31685 en local) | ✅ `tailscale serve` expose en HTTPS |
| Debug à distance | ❌ SSH + tunnel manuel | ✅ Accès direct via IP Tailscale |
| Conteneurs futurs (Phase 10+) | ❌ Réseau complexe | ✅ MagicDNS + subnet routing |
| Sécurité | ⚠️ Port forwarding risqué | ✅ Chiffré, zero port ouvert |
| Quota | ✅ Gratuit | ✅ Gratuit (100 devices, perso) |

**Principe V9** : Tailscale remplace ngrok (V8 legacy). 0 quota, 0 port forwarding, chiffré par défaut.

---

## 2. Installation Tailscale sur le VPS

### 2.1 Installer Tailscale

```bash
# Linux (Debian/Ubuntu)
curl -fsSL https://tailscale.com/install.sh | sh

# Vérifier
tailscale version
```

### 2.2 Connecter au réseau

```bash
sudo tailscale up
```

Un lien s'affiche dans le terminal. Ouvrir dans un navigateur, se connecter avec le compte Google/Microsoft/Email.

**Vérifier** :
```bash
tailscale status
# Attendu : une ligne avec le hostname du VPS + votre PC local
```

### 2.3 Activer MagicDNS (optionnel mais recommandé)

```bash
# Dans l'admin console Tailscale : DNS → Enable MagicDNS
# Puis :
tailscale status --json | grep DNSName
```

MagicDNS permet d'accéder au VPS par `hostname.tail<hash>.ts.net` au lieu de l'IP.

---

## 3. Exposer le pipeline V9 via Tailscale

### 3.1 Exposer le serveur de capture (port 31685)

```bash
# Depuis le VPS
sudo tailscale serve --https 443 / http://127.0.0.1:31685
```

**Résultat** : le port 31685 est accessible en HTTPS depuis n'importe quel device Tailscale :
```
https://<vps-hostname>.tail<hash>.ts.net/
```

### 3.2 Vérifier l'accès distant

Depuis ton PC local ou téléphone (connecté au même réseau Tailscale) :

```bash
curl https://<vps-hostname>.tail<hash>.ts.net/
# Réponse attendue : un message JSON du capture_server ou une erreur 400 (normal, c'est un socket TCP brut)
```

### 3.3 Exposer le dashboard (si besoin)

```bash
# Si tu veux un endpoint HTTP simple pour le dashboard
sudo tailscale serve --https 443 /dashboard/ http://127.0.0.1:8080
```

---

## 4. Architecture conteneurs future (Phase 10+)

### 4.1 Principe

V9 n'utilise **pas** de conteneurs aujourd'hui (100% stdlib Python, zéro dépendance). Mais l'architecture future (Phase 10 : fédération d'agents, Phase 11 : MT4 ticks) peut bénéficier de conteneurs pour isoler les services.

### 4.2 Topologie cible avec Tailscale

```
┌─────────────────────────────────────────────────────┐
│                   VPS (Tailscale)                    │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ capture  │  │ pipeline │  │  agent_bus       │   │
│  │ server   │  │ 9 couches │  │  (SQLite pub/sub)│   │
│  │ :31685   │  │ :31686   │  │  :31687          │   │
│  └────┬─────┘  └────┬─────┘  └───────┬──────────┘   │
│       │             │                │              │
│       └─────────────┼────────────────┘              │
│                     │                               │
│              ┌──────▼──────┐                        │
│              │  tailscale  │                        │
│              │  serve 443  │                        │
│              └──────┬──────┘                        │
│                     │                               │
└─────────────────────┼───────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
    ┌────▼───┐  ┌────▼───┐  ┌────▼───┐
    │  PC    │  │  Phone │  │ Laptop │
    │ local  │  │ (Søn)  │  │ dev    │
    └────────┘  └────────┘  └────────┘
```

### 4.3 Conteneurs Docker (quand nécessaire)

Si tu veux dockeriser les composants V9 plus tard :

```dockerfile
# Dockerfile.capture
FROM python:3.11-slim
WORKDIR /app
COPY core/v9/ core/v9/
COPY scripts/ scripts/
EXPOSE 31685
CMD ["python", "-m", "core.v9.capture_server"]
```

```yaml
# docker-compose.yml (futur)
version: "3.8"
services:
  capture:
    build:
      context: .
      dockerfile: Dockerfile.capture
    ports:
      - "31685:31685"
    networks:
      - tailscale
    volumes:
      - ./data:/app/data

  pipeline:
    build:
      context: .
      dockerfile: Dockerfile.pipeline
    depends_on:
      - capture
    networks:
      - tailscale

  agent-bus:
    build:
      context: .
      dockerfile: Dockerfile.agent-bus
    depends_on:
      - pipeline
    networks:
      - tailscale

networks:
  tailscale:
    external: true
```

### 4.4 Tailscale + Docker

Pour que les conteneurs Docker soient accessibles via Tailscale :

```bash
# Option 1 : Tailscale sidecar container
docker run -d --name=tailscale \
  -v tailscale-data:/var/lib/tailscale \
  -v /dev/net/tun:/dev/net/tun \
  --network=host \
  --cap-add=NET_ADMIN \
  --cap-add=SYS_MODULE \
  tailscale/tailscale:latest \
  tailscale up

# Option 2 : tsnet (Tailscale native Go lib) — pour les services custom
# À implémenter dans les futurs agents V9 si besoin
```

**Recommandation V9** : ne pas dockeriser maintenant. Le pipeline tient dans 200 MB RAM, zéro dépendance. Docker ajoute de la complexité pour 0 gain tant que Phase 10 n'est pas ouverte.

---

## 5. Sécurité

### 5.1 Règles

- ❌ **Ne jamais ouvrir le port 31685 sur l'IP publique du VPS** — uniquement via Tailscale
- ❌ **Ne jamais mettre les secrets (Telegram token, API keys) dans Git**
- ✅ **Tailscale chiffre tout le trafic** (end-to-end encryption)
- ✅ **Tailscale = zero port ouvert** sur le pare-feu du VPS

### 5.2 ACL Tailscale (recommandé)

Dans l'admin console Tailscale → ACLs :

```json
{
  "acls": [
    // Søn peut tout voir
    {"action": "accept", "src": ["son@"], "dst": ["vps:*"]},
    // Les autres devices ne voient que le port 31685
    {"action": "accept", "src": ["*"], "dst": ["vps:31685"]}
  ]
}
```

---

## 6. Commandes utiles

```bash
# Statut Tailscale
tailscale status

# Liste des devices connectés
tailscale status --json | jq '.Peer[] | {HostName, TailscaleIPs}'

# Exposer un port
sudo tailscale serve --https 443 / http://127.0.0.1:31685

# Lister les exposes
tailscale serve status

# Retirer un expose
sudo tailscale serve --https 443 / off

# Vérifier la connectivité depuis un autre device
ping <vps-tailscale-ip>
curl https://<vps-hostname>.tail<hash>.ts.net/

# Désactiver Tailscale (urgence)
sudo tailscale down

# Désinstaller
sudo apt remove tailscale
```

---

## 7. Procédure de déploiement complète (VPS vierge)

```bash
# ── 1. Installer Tailscale ──
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# → ouvrir le lien, connecter le compte

# ── 2. Cloner V9 ──
git clone https://github.com/gestionzen57-alt/PowerFlow_V9.git /opt/v9
cd /opt/v9
git checkout feat/v9-foundation-clean

# ── 3. Vérifier Python ──
python3 --version  # >= 3.11

# ── 4. Créer la DB (seed 7 jours si besoin) ──
python scripts/v9_vps_seed.py --dest data/v9_forces.db --days 7

# ── 5. Configurer les secrets ──
# Créer config/telegram.json avec BOT_TOKEN et CHAT_ID
# (jamais dans Git)

# ── 6. Démarrer le pipeline ──
python scripts/v9_ops.py start

# ── 7. Exposer via Tailscale ──
sudo tailscale serve --https 443 / http://127.0.0.1:31685

# ── 8. Installer les crons ──
# heartbeat 5min
schtasks /CREATE /SC MINUTE /MO 5 /TN "V9_HeartbeatCheck" \
  /TR "python D:\Projet\V9\scripts\v9_heartbeat.py --check" /RL HIGHEST

# heartbeat alerte 60min
schtasks /CREATE /SC MINUTE /MO 60 /TN "V9_HeartbeatAlert" \
  /TR "python D:\Projet\V9\scripts\v9_heartbeat.py --heartbeat" /RL HIGHEST

# ── 9. Vérifier ──
python scripts/v9_ops.py status
tailscale status
curl https://<hostname>.tail<hash>.ts.net/
```

---

## 8. Références

- `docs/deployment/VPS_RUNBOOK.md` — Runbook VPS complet
- `docs/vps_recovery/NEW_HERMES_PROCEDURE.md` — Procédure reprise Hermes vierge
- `docs/vps_recovery/skills/v9-live-ops.md` — Opérations pipeline live
- `docs/vps_recovery/skills/v9-infra-optimization.md` — Framework OPT-N (Tailscale vs ngrok)
- [Tailscale Documentation](https://tailscale.com/kb/)
- [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve/)
- [Tailscale Docker](https://tailscale.com/kb/1282/docker/)
