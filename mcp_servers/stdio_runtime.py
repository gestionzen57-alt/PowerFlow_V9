#!/usr/bin/env python3
"""Compatibilité stdio MCP standard + protocole legacy Hermes pour V9.

Les serveurs V9 passent leurs HANDLERS et descriptions à ``serve``. Le runtime
accepte le MCP JSON-RPC standard utilisé par Claude Code/ZCode et conserve le
format legacy ``{"tool": ..., "args": ...}`` utilisé par les tests/outils Hermes.
Zéro dépendance runtime : protocole implémenté avec la stdlib uniquement.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

Handler = Callable[[dict], dict]


def _object_schema(
    properties: dict[str, dict] | None = None,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    return schema


DEFAULT_TOOL_SCHEMAS: dict[str, dict] = {
    "read_file": _object_schema({"path": {"type": "string"}}, ["path"]),
    "write_file": _object_schema(
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    "list_dir": _object_schema({"path": {"type": "string", "default": "."}}),
    "search_files": _object_schema(
        {
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
        },
        ["pattern"],
    ),
    "query": _object_schema(
        {
            "sql": {"type": "string"},
            "db": {"type": "string", "enum": ["forces", "agent_bus"], "default": "forces"},
            "params": {"type": "array", "default": []},
        },
        ["sql"],
    ),
    "table_info": _object_schema(
        {
            "table": {"type": "string"},
            "db": {"type": "string", "enum": ["forces", "agent_bus"], "default": "forces"},
        },
        ["table"],
    ),
    "list_tables": _object_schema(
        {"db": {"type": "string", "enum": ["forces", "agent_bus"], "default": "forces"}}
    ),
    "snapshot_stats": _object_schema(),
    "principle_scores_top": _object_schema(
        {"limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20}}
    ),
    "paper_trades_audit": _object_schema(),
    "send_message": _object_schema(
        {"text": {"type": "string"}, "chat_id": {"type": "string"}}, ["text"]
    ),
    "send_alert": _object_schema(
        {
            "level": {
                "type": "string",
                "enum": ["INFO", "WARN", "ERROR", "CRITICAL"],
                "default": "INFO",
            },
            "text": {"type": "string"},
        },
        ["text"],
    ),
    "get_chat_id": _object_schema(),
    "start": _object_schema(),
    "stop": _object_schema(),
    "status": _object_schema(),
    "health": _object_schema(),
    "run_script": _object_schema(
        {"name": {"type": "string"}, "args": {"type": "string", "default": ""}},
        ["name"],
    ),
    "scan": _object_schema({"hours": {"type": "integer", "minimum": 1, "default": 24}}),
    "learn": _object_schema({"hours": {"type": "integer", "minimum": 1, "default": 24}}),
    "proposals": _object_schema(
        {"limit": {"type": "integer", "minimum": 1, "default": 5}}
    ),
    "emit": _object_schema(
        {"lookback_hours": {"type": "integer", "minimum": 1, "default": 24}}
    ),
    "stats": _object_schema(),
    "rules": _object_schema(),
    "get_rule": _object_schema({"n": {"type": ["integer", "string"]}}, ["n"]),
    "motion_log": _object_schema(
        {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}
    ),
    "assouplissement_summary": _object_schema(),
    "principle": _object_schema({"name": {"type": "string"}}, ["name"]),
    "adaptive_thresholds": _object_schema(),
    "principle_stats": _object_schema(),
    "shadow_principles": _object_schema(),
    "p3_consume_summary": _object_schema(),
}


DEFAULT_TOOL_DESCRIPTIONS: dict[str, str] = {
    "read_file": "Lire un fichier UTF-8 relatif au dépôt PowerFlow V9.",
    "write_file": "Écrire un fichier UTF-8 dans le dépôt PowerFlow V9.",
    "list_dir": "Lister un répertoire du dépôt PowerFlow V9.",
    "search_files": "Rechercher des noms de fichiers par expression régulière.",
    "query": "Exécuter une requête SQL en lecture seule sur une base V9.",
    "table_info": "Lire le schéma et le nombre de lignes d'une table V9 autorisée.",
    "list_tables": "Lister les tables V9 autorisées pour une base.",
    "snapshot_stats": "Retourner les compteurs et la fraîcheur du dernier snapshot V9.",
    "principle_scores_top": "Lister les meilleures combinaisons de principes par win rate.",
    "paper_trades_audit": "Auditer l'état de la table paper_trades.",
    "send_message": "Envoyer un message Telegram via la configuration locale V9.",
    "send_alert": "Envoyer une alerte Telegram avec anti-spam.",
    "get_chat_id": "Lire l'identifiant de chat Telegram configuré sans exposer le token.",
    "start": "Démarrer le pipeline de capture PowerFlow V9.",
    "stop": "Arrêter le pipeline de capture PowerFlow V9.",
    "status": "Lire le statut compact du pipeline et de la base V9.",
    "health": "Exécuter le diagnostic de santé complet du pipeline V9.",
    "run_script": "Exécuter un script V9 explicitement autorisé.",
    "scan": "Scanner les patterns du meta-agent sur une fenêtre horaire.",
    "learn": "Lancer un cycle d'apprentissage du meta-agent V9.",
    "proposals": "Lister les propositions récentes du meta-agent.",
    "emit": "Émettre les événements calculés par le meta-agent.",
    "stats": "Lire les compteurs du bus d'agents V9.",
    "rules": "Lister les règles de doctrine PowerFlow V9.",
    "get_rule": "Lire une règle précise de doctrine V9.",
    "motion_log": "Lister les motions CEO d'assouplissement doctrinal.",
    "assouplissement_summary": "Résumer les assouplissements doctrinaux actifs.",
    "principle": "Lire un principe du catalogue YAML V9.",
    "adaptive_thresholds": "Lire la configuration des seuils adaptatifs V9.",
    "principle_stats": "Compter les principes ACTIVE et SHADOW.",
    "shadow_principles": "Lister les principes encore en statut SHADOW.",
    "p3_consume_summary": "Résumer l'état du chantier P3-CONSUME.",
}


def _response(request_id: Any, *, result: Any = None, error: dict | None = None) -> dict:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    return message


def _tool_list(
    handlers: dict[str, Handler],
    descriptions: dict[str, str],
    schemas: dict[str, dict],
) -> list[dict]:
    return [
        {
            "name": name,
            "description": descriptions.get(name, DEFAULT_TOOL_DESCRIPTIONS.get(name, name)),
            "inputSchema": schemas.get(name, DEFAULT_TOOL_SCHEMAS.get(name, _object_schema())),
        }
        for name in handlers
    ]


def _handle_standard_mcp(
    req: dict,
    handlers: dict[str, Handler],
    server_name: str,
    descriptions: dict[str, str],
    schemas: dict[str, dict],
) -> dict | None:
    method = req.get("method")
    request_id = req.get("id")

    if method == "initialize":
        requested = req.get("params", {}).get("protocolVersion")
        protocol_version = requested if isinstance(requested, str) else "2025-06-18"
        return _response(
            request_id,
            result={
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": server_name, "version": "1.0.0"},
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _response(request_id, result={})
    if method == "tools/list":
        return _response(request_id, result={"tools": _tool_list(handlers, descriptions, schemas)})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = handlers.get(name)
        if handler is None:
            return _response(
                request_id,
                error={"code": -32602, "message": f"unknown tool: {name}"},
            )
        try:
            payload = handler(arguments)
            is_error = isinstance(payload, dict) and "error" in payload
            return _response(
                request_id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, default=str, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": payload,
                    "isError": is_error,
                },
            )
        except Exception as exc:
            return _response(
                request_id,
                result={
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
    if "id" not in req:
        return None
    return _response(
        request_id,
        error={"code": -32601, "message": f"method not found: {method}"},
    )


def serve(
    handlers: dict[str, Handler],
    server_name: str,
    descriptions: dict[str, str] | None = None,
    schemas: dict[str, dict] | None = None,
) -> None:
    """Servir MCP standard et protocole legacy sur stdin/stdout, une ligne JSON à la fois."""
    descriptions = descriptions or {}
    schemas = schemas or {}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request must be a JSON object")
            if "method" in req:
                response = _handle_standard_mcp(
                    req, handlers, server_name, descriptions, schemas
                )
                if response is not None:
                    print(json.dumps(response, default=str, ensure_ascii=False), flush=True)
                continue

            tool = req.get("tool")
            args = req.get("args", {})
            handler = handlers.get(tool)
            result = handler(args) if handler else {"error": f"unknown tool: {tool}"}
            print(
                json.dumps(
                    {"id": req.get("id"), "result": result},
                    default=str,
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"parse/handle error: {exc}"},
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
