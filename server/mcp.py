"""Minimal MCP (Model Context Protocol) server over HTTP/JSON-RPC.

Exposes the automation as MCP tools so a scheduled agent (e.g. Claude) can connect
to /claude-mcp and autonomously check the inbox and ingest the latest schedule.
Implements the core methods: initialize, tools/list, tools/call, ping. Auth is the
same bearer API token used elsewhere (must carry the `automate` capability).
"""

from __future__ import annotations

import json

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "list_spreadsheets",
        "description": "List spreadsheets in the inbox (newest first) with size, "
                       "modified time and a content hash.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_latest",
        "description": "Parse the newest inbox spreadsheet WITHOUT importing it, "
                       "returning each tab's name, people count, date range and "
                       "whether it looks like a draft, plus a suggested_sheet. Use "
                       "this to choose the right tab before ingest_latest.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ingest_latest",
        "description": "Ingest the newest spreadsheet from the inbox into the app. "
                       "Idempotent: reports 'unchanged', 'updated' (same period, new "
                       "content) or 'added' (a new month/period). Optionally pin a "
                       "sheet name; otherwise the best sheet is auto-picked.",
        "inputSchema": {
            "type": "object",
            "properties": {"sheet": {"type": "string",
                                     "description": "Optional exact sheet/tab name."}},
        },
    },
    {
        "name": "schedule_status",
        "description": "Summary of the currently active schedule and the automation "
                       "state (inbox path, periods ingested, last run).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _call_tool(name: str, args: dict, automation, store) -> dict:
    try:
        if name == "list_spreadsheets":
            payload = automation.list_spreadsheets()
        elif name == "inspect_latest":
            payload = automation.inspect_latest()
        elif name == "ingest_latest":
            payload = automation.ingest_latest(sheet=args.get("sheet"), actor="mcp")
        elif name == "schedule_status":
            sched = store.get_schedule() or {}
            payload = {
                "active_sheet": sched.get("parsed_sheet"),
                "date_range": sched.get("date_range"),
                "people": len([p for p in sched.get("people", []) if p.get("name")]),
                "automation": automation.status(),
            }
        else:
            return {"content": [{"type": "text", "text": f"unknown tool: {name}"}],
                    "isError": True}
        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)}]}
    except Exception as exc:  # noqa: BLE001 - surface tool errors to the agent
        return {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}


def handle(req: dict, automation, store, on_tool=None):
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "fastmodel-scheduler", "version": "1.0"},
        }
    elif method and method.startswith("notifications/"):
        return None  # notifications get no response
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if on_tool:
            on_tool(name, args)
        result = _call_tool(name, args, automation, store)
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}

    return {"jsonrpc": "2.0", "id": rid, "result": result}
