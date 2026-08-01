"""tests/test_v9_phase84.py — Phase 84 motion CEO 48H (post-Plan C).

Tests pour docker_compose_gen.
"""
import pytest
from pathlib import Path


def test_generate_dockerfile():
    from scripts.v9_docker_compose_gen import generate_dockerfile
    df = generate_dockerfile()
    assert "FROM python" in df
    assert "WORKDIR" in df
    assert "COPY" in df
    assert "CMD" in df


def test_generate_dockerfile_with_py_version():
    from scripts.v9_docker_compose_gen import generate_dockerfile
    df = generate_dockerfile(python_version="3.12")
    assert "python:3.12" in df


def test_generate_docker_compose():
    from scripts.v9_docker_compose_gen import generate_docker_compose
    dc = generate_docker_compose()
    assert "version:" in dc or "services:" in dc
    assert "v9-pipeline" in dc
    assert "v9-cron" in dc
    assert "v9-watcher" in dc


def test_generate_docker_compose_with_port():
    from scripts.v9_docker_compose_gen import generate_docker_compose
    dc = generate_docker_compose(api_port=9090)
    assert "9090" in dc


def test_generate_env_file():
    from scripts.v9_docker_compose_gen import generate_env_file
    env = generate_env_file()
    assert "V9_DB_PATH" in env
    assert "V9_TELEGRAM_BOT_TOKEN" in env


def test_write_all_files(tmp_path):
    from scripts.v9_docker_compose_gen import write_all
    ok = write_all(tmp_path)
    assert ok is True
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / "docker-compose.yml").exists()
    assert (tmp_path / ".env.example").exists()


def test_dockerfile_has_requirements_install():
    from scripts.v9_docker_compose_gen import generate_dockerfile
    df = generate_dockerfile()
    assert "pip install" in df
    assert "requirements" in df


def test_docker_compose_has_volumes():
    from scripts.v9_docker_compose_gen import generate_docker_compose
    dc = generate_docker_compose()
    assert "volumes:" in dc
    assert "data" in dc or ":/app" in dc


def test_env_file_has_critical_vars():
    from scripts.v9_docker_compose_gen import generate_env_file
    env = generate_env_file()
    assert "V9_TRADE_ENGINE_ENABLED" in env
    assert "V9_KILL_DD_PIPS" in env


def test_main_demo(tmp_path, capsys):
    from scripts.v9_docker_compose_gen import main
    exit_code = main(["--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DOCKER COMPOSE" in captured.out
    assert (tmp_path / "Dockerfile").exists()