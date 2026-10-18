"""MCP server exposing the two approval-gated actions.

Tools
  append_to_doc(approval_id, entry)                 -> append the weekly entry to the notes doc
  create_email_draft(approval_id, subject, body, to) -> create an email draft (never sends)

Both tools refuse to run unless approval_id matches an approved decision for
exactly these arguments (see approvals.py).

Run standalone:   python -m mcp_server.server        (stdio transport)
Use from Claude Desktop or any MCP client by pointing it at that command.
"""
from mcp.server.fastmcp import FastMCP

from mcp_server import backends
from mcp_server.approvals import check_and_consume, record_execution

mcp = FastMCP("groww-pulse-tools")

ENTRY_KEYS = {"date", "top_themes", "weekly_pulse", "identified_fee_issue",
              "explanation_bullets", "source_links"}


@mcp.tool()
def append_to_doc(approval_id: str, entry: dict) -> dict:
    """Append this week's entry {date, top_themes, weekly_pulse, identified_fee_issue,
    explanation_bullets, source_links} to the internal notes doc. Requires an approval id."""
    args = {"entry": entry}
    ok, why = check_and_consume(approval_id, "append_to_doc", args)
    if not ok:
        record_execution(approval_id, "append_to_doc", False, {"error": why})
        return {"ok": False, "error": f"Not approved: {why}"}
    missing = ENTRY_KEYS - set(entry)
    if missing:
        return {"ok": False, "error": f"entry is missing fields: {sorted(missing)}"}
    try:
        result = backends.append(entry)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
        record_execution(approval_id, "append_to_doc", False, result)
        return {"ok": False, **result}
    record_execution(approval_id, "append_to_doc", True, result)
    return {"ok": True, **result}


@mcp.tool()
def create_email_draft(approval_id: str, subject: str, body: str, to: str = "") -> dict:
    """Create an email DRAFT with the weekly pulse and the fee explainer snippet.
    Never sends. Requires an approval id."""
    args = {"subject": subject, "body": body, "to": to}
    ok, why = check_and_consume(approval_id, "create_email_draft", args)
    if not ok:
        record_execution(approval_id, "create_email_draft", False, {"error": why})
        return {"ok": False, "error": f"Not approved: {why}"}
    try:
        result = backends.draft(subject, body, to or None)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
        record_execution(approval_id, "create_email_draft", False, result)
        return {"ok": False, **result}
    record_execution(approval_id, "create_email_draft", True, result)
    return {"ok": True, **result}


if __name__ == "__main__":
    mcp.run()
