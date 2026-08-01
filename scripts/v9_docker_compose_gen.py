"""v9_docker_compose_gen.py — Phase 84 motion CEO 48H (post-Plan C).

Generateur de Dockerfile + docker-compose.yml + .env.example pour deploiement
prod du systeme V9.

Services :
- v9-pipeline : orchestrateur principal
- v9-cron : taches planifiees
- v9-watcher : monitoring + alertes

Auteur : Hermes (Phase 84 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("v9.docker_gen")


def generate_dockerfile(python_version: str = "3.11") -> str:
    """Genere le Dockerfile prod."""
    return f"""# V9 Dockerfile (Phase 84 motion CEO 48H)
FROM python:{python_version}-slim

# Deps systeme minimales
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential && rm -rf /var/lib/apt/lists/*

# Working dir
WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Healthcheck
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \\
    CMD python scripts/v9_real_money_preflight.py || exit 1

# CMD par defaut : orchestrateur
CMD ["python", "scripts/v9_cron_48h.sh"]
"""


def generate_docker_compose(api_port: int = 8080) -> str:
    """Genere le docker-compose.yml prod."""
    return f"""# V9 docker-compose (Phase 84 motion CEO 48H)
version: "3.9"

services:
  v9-pipeline:
    build: .
    container_name: v9-pipeline
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./backups:/app/backups
    env_file:
      - .env
    command: python scripts/v9_cron_48h.sh
    healthcheck:
      test: ["CMD", "python", "scripts/v9_real_money_preflight.py"]
      interval: 300s
      timeout: 30s
      retries: 3

  v9-cron:
    build: .
    container_name: v9-cron
    restart: unless-stopped
    depends_on:
      - v9-pipeline
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    env_file:
      - .env
    command: python -c "import scripts.v9_phase_tracker as t; t.run_scheduler()"

  v9-watcher:
    build: .
    container_name: v9-watcher
    restart: unless-stopped
    depends_on:
      - v9-pipeline
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    env_file:
      - .env
    ports:
      - "{api_port}:8080"
    command: python scripts/v9_live_metrics.py --port {api_port}

volumes:
  data:
  logs:
  backups:
"""


def generate_env_file() -> str:
    """Genere le .env.example."""
    return """# V9 Environment (Phase 84 motion CEO 48H)
# Copier ce fichier vers .env et remplir les valeurs

# Database
V9_DB_PATH=/app/data/v9_forces.db

# Telegram (optionnel)
V9_TELEGRAM_BOT_TOKEN=
V9_TELEGRAM_CHAT_ID=

# Webhook alertes (optionnel)
V9_ALERT_WEBHOOK_URL=

# Kill switches (defaults OK pour paper)
V9_TRADE_ENGINE_ENABLED=1
V9_KILL_DD_PIPS=-100
V9_KILL_WR_FLOOR=0.40
V9_DYNAMIC_RISK_ENABLED=1
V9_MEGA_EDGE_ENABLED=1
V9_PAPER_TRADE_HALT=0
V9_MT4_BRIDGE_ENABLED=1

# FTMO
FTMO_DAILY_DD_PCT=0.04
FTMO_TOTAL_DD_PCT=0.08

# Cron
V9_PHASE_TRACKER_MAX_HOURS=48
"""


def write_all(output_dir: Path) -> bool:
    """Ecrit Dockerfile + docker-compose.yml + .env.example."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "Dockerfile").write_text(generate_dockerfile())
        (output_dir / "docker-compose.yml").write_text(
            generate_docker_compose(),
        )
        (output_dir / ".env.example").write_text(generate_env_file())
        return True
    except Exception as exc:
        log.warning("write_all failed: %s", exc)
        return False


def main(argv=None) -> int:
    """Genere les fichiers Docker dans ./docker/."""
    import argparse
    parser = argparse.ArgumentParser(description="V9 Docker Compose generator")
    parser.add_argument("--output-dir", default="./docker")
    args = parser.parse_args(argv)
    out = Path(args.output_dir)
    print("=" * 70)
    print("V9 DOCKER COMPOSE GENERATOR (Phase 84)")
    print("=" * 70)
    print(f"Output dir : {out}")
    ok = write_all(out)
    print(f"Generated : {ok}")
    if ok:
        for f in ["Dockerfile", "docker-compose.yml", ".env.example"]:
            p = out / f
            print(f"  {p} ({p.stat().st_size} bytes)")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())