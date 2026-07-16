"""Tests pytest pour les 5 MCP servers V9 (subprocess stdin/stdout JSON-RPC)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT_DIR = Path(r"C:\projet\V9").resolve()
PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"


def _call_mcp(server: str, tool: str, args: dict | None = None,
              timeout: int = 30) -> dict:
    """Lance un MCP server en subprocess et lui envoie une requête JSON-RPC.

    Utilise Popen + communicate() avec bytes bruts pour éviter les bugs
    d'encodage Windows (UTF-8 vs cp1252 dans les pipes). Unwrap automatiquement
    le champ "result" du JSON-RPC pour simplifier les asserts.
    """
    cmd = [str(PYTHON), str(ROOT_DIR / "mcp_servers" / f"{server}.py")]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env,
    )
    try:
        req = (json.dumps({"tool": tool, "args": args or {}}) + "\n").encode("utf-8")
        stdout, stderr = proc.communicate(input=req, timeout=timeout)
        if not stdout:
            err_msg = stderr.decode("utf-8", errors="replace")[-300:]
            return {"error": f"no output. stderr={err_msg}"}
        first_line = stdout.decode("utf-8", errors="replace").strip().splitlines()[0]
        envelope = json.loads(first_line)
        return envelope.get("result", envelope)
    finally:
        if proc.poll() is None:
            proc.kill()


def _exchange_standard_mcp(server: str, requests: list[dict], timeout: int = 30) -> list[dict]:
    """Échange plusieurs messages MCP standard JSON-RPC avec un serveur stdio."""
    cmd = [str(PYTHON), str(ROOT_DIR / "mcp_servers" / f"{server}.py")]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env,
    )
    try:
        payload = "".join(json.dumps(req) + "\n" for req in requests).encode("utf-8")
        stdout, stderr = proc.communicate(input=payload, timeout=timeout)
        if not stdout:
            err_msg = stderr.decode("utf-8", errors="replace")[-500:]
            raise AssertionError(f"MCP server produced no output: {err_msg}")
        return [json.loads(line) for line in stdout.decode("utf-8").splitlines() if line.strip()]
    finally:
        if proc.poll() is None:
            proc.kill()


STANDARD_MCP_TOOLS = {
    "filesystem_server": {"read_file", "write_file", "list_dir", "search_files"},
    "sqlite_server": {
        "query", "table_info", "list_tables", "snapshot_stats",
        "principle_scores_top", "paper_trades_audit",
    },
    "telegram_server": {"send_message", "send_alert", "get_chat_id"},
    "pipeline_server": {"start", "stop", "status", "health", "run_script"},
    "meta_agent_server": {"scan", "learn", "proposals", "emit", "stats"},
    "doctrine_server": {"rules", "get_rule", "motion_log", "assouplissement_summary"},
    "p3_consume_server": {
        "principle", "adaptive_thresholds", "principle_stats",
        "shadow_principles", "p3_consume_summary",
    },
}


@pytest.mark.parametrize("server, expected_tools", STANDARD_MCP_TOOLS.items())
def test_standard_mcp_initialize_and_tools_list(server: str, expected_tools: set[str]) -> None:
    """Claude CLI et ZCode doivent découvrir chaque serveur via le protocole MCP standard."""
    responses = _exchange_standard_mcp(server, [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])

    assert len(responses) == 2  # une notification ne reçoit aucune réponse
    initialized, listed = responses
    assert initialized["jsonrpc"] == "2.0"
    assert initialized["id"] == 1
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in initialized["result"]["capabilities"]

    tools = listed["result"]["tools"]
    assert {tool["name"] for tool in tools} == expected_tools
    assert all(tool["description"] for tool in tools)
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)


def test_standard_mcp_tools_call_executes_handler() -> None:
    """Un appel tools/call standard doit atteindre le handler V9 existant."""
    responses = _exchange_standard_mcp("filesystem_server", [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_dir", "arguments": {"path": "scripts"}},
        },
    ])

    response = responses[0]
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert "v9_ops.py" in payload["entries"]


# ── MCP filesystem ────────────────────────────────────────
def test_filesystem_list_dir() -> None:
    res = _call_mcp("filesystem_server", "list_dir", {"path": "scripts"})
    assert "entries" in res
    assert "v9_ops.py" in res["entries"]



def test_filesystem_read_file() -> None:
    res = _call_mcp("filesystem_server", "read_file", {"path": "pyproject.toml"})
    assert "content" in res
    assert "[project]" in res["content"] or "name" in res["content"]


def test_filesystem_security_rejects_traversal() -> None:
    res = _call_mcp("filesystem_server", "read_file", {"path": "../etc/passwd"})
    assert "error" in res


def test_filesystem_search_files() -> None:
    res = _call_mcp("filesystem_server", "search_files",
                     {"pattern": "^v9_.*\\.py$", "path": "scripts"})
    assert "matches" in res
    assert res["count"] > 0


# ── MCP sqlite ────────────────────────────────────────────
def test_sqlite_list_tables() -> None:
    res = _call_mcp("sqlite_server", "list_tables", {"db": "forces"})
    assert "tables" in res
    assert "forces_snapshots" in res["tables"]
    assert "decisions" in res["tables"]


def test_sqlite_query_readonly() -> None:
    """SELECT doit passer, INSERT doit être bloqué (read-only)."""
    res_ok = _call_mcp("sqlite_server", "query",
                       {"sql": "SELECT COUNT(*) as n FROM forces_snapshots"})
    assert "rows" in res_ok
    assert res_ok["rows"][0]["n"] > 0

    res_block = _call_mcp("sqlite_server", "query",
                          {"sql": "DELETE FROM decisions"})
    assert "error" in res_block
    assert "interdite" in res_block["error"]


def test_sqlite_snapshot_stats() -> None:
    res = _call_mcp("sqlite_server", "snapshot_stats")
    assert "forces_snapshots" in res
    assert "win_loss" in res
    assert "wins" in res["win_loss"]


def test_sqlite_table_info() -> None:
    res = _call_mcp("sqlite_server", "table_info", {"table": "decisions"})
    assert res["table"] == "decisions"
    assert res["row_count"] > 0
    assert any(c["name"] == "decision_id" for c in res["columns"])


def test_sqlite_whitelist_rejects() -> None:
    """Les tables hors whitelist (sqlite_master, etc.) sont bloquées en table_info."""
    res = _call_mcp("sqlite_server", "table_info", {"table": "sqlite_master"})
    assert "error" in res
    assert "whitelist" in res["error"]


def test_pipeline_run_script_whitelist() -> None:
    res = _call_mcp("pipeline_server", "run_script",
                     {"name": "v9_meta_agent", "args": "--scan --hours 24"})
    assert res.get("exit_code") == 0
    assert "stdout_tail" in res


def test_pipeline_run_script_rejects_unknown() -> None:
    res = _call_mcp("pipeline_server", "run_script", {"name": "rm_rf"})
    assert "error" in res
    assert "non whitelist" in res["error"]


# ── MCP telegram ──────────────────────────────────────────
def test_telegram_get_chat_id() -> None:
    res = _call_mcp("telegram_server", "get_chat_id")
    assert "chat_id" in res


def test_telegram_send_message() -> None:
    res = _call_mcp("telegram_server", "send_message",
                     {"text": "pytest MCP test (peut être ignoré)"})
    # Token présent dans .env → devrait envoyer OK
    if res.get("error"):
        # Si erreur config, c'est OK (pas de token en CI)
        pytest.skip(f"telegram config: {res['error']}")
    assert res["sent"] is True


def test_telegram_send_alert_anti_spam() -> None:
    """Anti-spam : 2 envois du même message en < 1h → 2ème bloqué."""
    import time
    text = f"pytest anti-spam test {int(time.time())}"
    res1 = _call_mcp("telegram_server", "send_alert", {"level": "INFO", "text": text})
    if res1.get("error"):
        pytest.skip(f"telegram config: {res1['error']}")
    res2 = _call_mcp("telegram_server", "send_alert", {"level": "INFO", "text": text})
    assert res2.get("anti_spam") is True
    assert res2.get("remaining_s", 0) > 0


# ── MCP meta-agent ────────────────────────────────────────
def test_meta_agent_stats() -> None:
    res = _call_mcp("meta_agent_server", "stats")
    assert "events" in res
    assert res["events"] >= 0


def test_meta_agent_scan() -> None:
    res = _call_mcp("meta_agent_server", "scan", {"hours": 24})
    assert res.get("exit_code") == 0
    assert "PATTERNS" in res.get("output", "") or "pattern" in res.get("output", "")


# ── MCP sqlite — outils ajoutés 2026-07-14 (B1 motion CEO) ──

def test_sqlite_principle_scores_top() -> None:
    """principle_scores_top(limit) : top combinaisons par win_rate.
    5 combinaisons insérées le 2026-07-14 (commit 080fb3f)."""
    res = _call_mcp("sqlite_server", "principle_scores_top", {"limit": 10})
    assert "rows" in res
    assert res["count"] >= 1
    assert res["total_in_table"] >= 1
    # Top combinaison (PRICE_LAG_AT_NODE_BIRTH seul) doit avoir WR > 80%
    top = res["rows"][0]
    assert "PRICE_LAG" in top["principle_id"]
    assert top["win_rate"] > 0.8


def test_sqlite_principle_scores_top_limit_validation() -> None:
    res = _call_mcp("sqlite_server", "principle_scores_top", {"limit": 500})
    assert "error" in res  # limite max = 200


def test_sqlite_paper_trades_audit_cleaned_or_trading() -> None:
    """paper_trades_audit() : 0 rows OU activité trade_engine (Phase 14+).

    État baseline 2026-07-14 commit 080fb3f = 0 rows ('cleaned').
    Depuis Phase 14 / trade_engine (2026-07-15), des paper-trades sont
    créés par run_paper_trade_cycle (--paper-trade cron). On accepte donc
    'cleaned' (0 rows) OU 'has_data' (n>=1 + by_direction/by_confiance).
    """
    res = _call_mcp("sqlite_server", "paper_trades_audit", {})
    assert res["status"] in ("cleaned", "has_data"), f"unexpected status: {res.get('status')}"
    assert "total" in res
    if res["status"] == "cleaned":
        assert res["total"] == 0
        assert "note" in res
    else:  # has_data
        assert res["total"] >= 1
        assert "by_direction" in res
        assert "by_confiance_bucket" in res


# ── MCP doctrine — nouveau 2026-07-14 (D motion CEO R25) ──

def test_doctrine_rules_total() -> None:
    """rules() : 30 règles + statut assouplissement 2026-07-14."""
    res = _call_mcp("doctrine_server", "rules", {})
    assert res["total"] == 30
    # 4 règles assouplies : 7, 22, 25', 28
    assert set(res["assouplies_2026_07_14"]) == {7, 22, "25'", 28}


def test_doctrine_get_rule_r7_assoupli() -> None:
    """R7 = assoupli 2026-07-14 (zéro régression NON justifiée)."""
    res = _call_mcp("doctrine_server", "get_rule", {"n": 7})
    assert "assoupli 2026-07-14" in res["statut"]
    assert "motion" in res


def test_doctrine_get_rule_r18_intacte() -> None:
    """R18 = intacte (pas de LLM dans le cœur cognitif)."""
    res = _call_mcp("doctrine_server", "get_rule", {"n": 18})
    assert res["statut"] == "intacte"


def test_doctrine_motion_log() -> None:
    """motion_log(limit) : extrait les sections DECISIONS_LOG « assoupli 2026-07-14 »."""
    res = _call_mcp("doctrine_server", "motion_log", {"limit": 5})
    assert "sections" in res
    assert res["count"] >= 1
    # Au moins une section doit mentionner 2026-07-14
    for s in res["sections"]:
        assert "2026-07-14" in s["header"] or "assoupli" in s["excerpt"].lower()


def test_doctrine_assouplissement_summary() -> None:
    """assouplissement_summary() : résumé factuel motion CEO 2026-07-14."""
    res = _call_mcp("doctrine_server", "assouplissement_summary", {})
    assert res["motion_ceo_date"] == "2026-07-14"
    assert set(res["rules_assouplies"]) == {7, 22, "25'", 28}
    assert res["rules_total"] == 30
    assert len(res["commits_lies"]) >= 1


# ── MCP p3-consume — nouveau 2026-07-14 (E motion CEO R25) ──

def test_p3_consume_adaptive_thresholds() -> None:
    """adaptive_thresholds() : seuils baseline + bornes MIN/MAX."""
    res = _call_mcp("p3_consume_server", "adaptive_thresholds", {})
    assert "VOL_MULTIPLIER" in res
    assert "BASELINE_THRESHOLDS" in res
    assert res["MIN_MULTIPLIER"] == "0.5"
    assert res["MAX_MULTIPLIER"] == "2.0"
    assert res["p3_consume_commit"] == "5e1b9df (premier consommateur: ADAPTIVE_VOL_GATE)"


def test_p3_consume_principle_adaptive_vol_gate() -> None:
    """principle(name) : ADAPTIVE_VOL_GATE existe, kind=node_rule.
    v9_status=SHADOW depuis DIVERSIFY 2026-07-16 (Mix CEO) — réanimé par
    fix d'échelle coalition, en observation 24-48h avant re-promotion ACTIVE."""
    res = _call_mcp("p3_consume_server", "principle", {"name": "ADAPTIVE_VOL_GATE"})
    assert res["name"] == "ADAPTIVE_VOL_GATE"
    assert res["yaml"]["kind"] == "node_rule"
    assert res["yaml"]["v9_status"] == "SHADOW"


def test_p3_consume_principle_stats() -> None:
    """principle_stats() : 53 principes total (25 ACTIVE + 23 SHADOW, 5 DORMANT).
    2026-07-14 : SIGNAL_OPEN + ADAPTIVE_VOL_GATE promus ACTIVE (motion CEO).
    Mandat CEO 2026-07-16 « boucle fermée » : promotion massive SHADOW→ACTIVE.
    DIVERSIFY 2026-07-16 (Mix CEO) : 4 réanimés rétrogradés ACTIVE→SHADOW
    en observation (ANTAGONIST_NODE, GRAMMAR_LOCK, GRAMMAR_RESPIRATION,
    ADAPTIVE_VOL_GATE). 44 ACTIVE + 9 SHADOW = 53 principes."""
    res = _call_mcp("p3_consume_server", "principle_stats", {})
    # DIVERSIFY couleur 2026-07-16 (Gap 5) : +VELOCITY_CLIMAX_GUARD (SHADOW).
    # OUVERTURE DES YEUX 2026-07-16 : +VOLUME_CONFIRMATION (SHADOW).
    assert res["total"] == 55
    assert res["active"] == 44
    assert res["shadow"] == 11


def test_p3_consume_shadow_principles() -> None:
    """shadow_principles() : 5 SHADOW structurels (ANTAGONIST_NODE_ADAPTIVE,
    GRAMMAR_EXHAUSTION_ADAPTIVE, GRAMMAR_LOCK_ADAPTIVE,
    GRAMMAR_RESPIRATION_ADAPTIVE, SIGNAL_OPEN_ADAPTIVE)."""
    res = _call_mcp("p3_consume_server", "shadow_principles", {})
    # DIVERSIFY couleur 2026-07-16 (Gap 5) : +VELOCITY_CLIMAX_GUARD → 10 SHADOW.
    # OUVERTURE DES YEUX 2026-07-16 : +VOLUME_CONFIRMATION → 11 SHADOW.
    assert res["count"] == 11  # 5 structurels + 4 réanimés + VELOCITY + VOLUME
    names = [p["name"] for p in res["shadows"]]
    assert "SIGNAL_OPEN" not in names  # reste ACTIVE (fix YAML trivial)
    assert "GRAMMAR_EXHAUSTION" not in names  # reste ACTIVE (fix YAML trivial)
    assert "COALITION_NODE_ADAPTIVE" not in names  # promu ACTIVE (mandat CEO)
    # 5 SHADOW structurels + 4 rétrogradés DIVERSIFY + VELOCITY + VOLUME
    for shadow_id in ("ANTAGONIST_NODE_ADAPTIVE", "GRAMMAR_EXHAUSTION_ADAPTIVE",
                      "GRAMMAR_LOCK_ADAPTIVE", "GRAMMAR_RESPIRATION_ADAPTIVE",
                      "SIGNAL_OPEN_ADAPTIVE",
                      "ANTAGONIST_NODE", "GRAMMAR_LOCK", "GRAMMAR_RESPIRATION",
                      "ADAPTIVE_VOL_GATE", "VELOCITY_CLIMAX_GUARD",
                      "VOLUME_CONFIRMATION"):
        assert shadow_id in names, f"{shadow_id} devrait être SHADOW"


def test_p3_consume_summary() -> None:
    """p3_consume_summary() : état global P3-CONSUME 2026-07-14."""
    res = _call_mcp("p3_consume_server", "p3_consume_summary", {})
    assert "ADAPTIVE_VOL_GATE" in res["premier_consommateur"]
    assert res["p3_consume_commit"].startswith("5e1b9df")
    assert "value_field" in res["pattern"]


def test_meta_agent_proposals() -> None:
    res = _call_mcp("meta_agent_server", "proposals", {"limit": 3})
    assert res.get("exit_code") == 0