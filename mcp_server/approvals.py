"""Approval ledger shared by the client (writes decisions) and the MCP server (enforces them).

A tool call is only executed by the server if data/approvals.jsonl contains an
"approved" record whose payload hash matches the exact arguments, and that
approval has not been used before for the same tool. So even a caller that
skips the UI cannot write to the doc or create a draft without approval.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "data" / "approvals.jsonl"


def _ledger() -> Path:
    return Path(os.environ.get("APPROVALS_LEDGER", LEDGER))


def payload_hash(tool: str, args: dict) -> str:
    body = json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(rec: dict) -> None:
    led = _ledger()
    led.parent.mkdir(parents=True, exist_ok=True)
    with open(led, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _records() -> list[dict]:
    led = _ledger()
    if not led.exists():
        return []
    return [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()]


def record_decision(actions: list[dict], approved: bool, reviewer: str = "local-user") -> str:
    """Store one decision covering all proposed actions. Returns the approval id."""
    approval_id = "APR-" + uuid.uuid4().hex[:10]
    _append({
        "type": "decision", "approval_id": approval_id, "at": _now(), "reviewer": reviewer,
        "decision": "approved" if approved else "rejected",
        "actions": [{"tool": a["tool"], "hash": payload_hash(a["tool"], a["args"])} for a in actions],
    })
    return approval_id


def check_and_consume(approval_id: str, tool: str, args: dict) -> tuple[bool, str]:
    recs = _records()
    decision = next((r for r in recs if r.get("type") == "decision" and r["approval_id"] == approval_id), None)
    if decision is None:
        return False, "unknown approval id"
    if decision["decision"] != "approved":
        return False, "this request was rejected by the reviewer"
    h = payload_hash(tool, args)
    if not any(a["tool"] == tool and a["hash"] == h for a in decision["actions"]):
        return False, "payload differs from what was approved"
    if any(r.get("type") == "execution" and r["approval_id"] == approval_id and r["tool"] == tool
           and r.get("ok") for r in recs):
        return False, "this approval was already used for this tool"
    return True, "ok"


def record_execution(approval_id: str, tool: str, ok: bool, result: dict) -> None:
    _append({"type": "execution", "approval_id": approval_id, "tool": tool, "at": _now(),
             "ok": ok, "result": result})
