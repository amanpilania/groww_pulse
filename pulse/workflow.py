"""Approval-gated MCP actions.

1. Build the two proposed tool calls with their exact arguments.
2. Show them to a human and ask for approval
3. Record the decision in data/approvals.jsonl.
4. Only if approved: start the MCP server over stdio, list its tools, and call
   append_to_doc and create_email_draft with the approval id.
   (The server re-checks the approval and the payload hash itself.)

  python -m pulse.workflow          # interactive approval in the terminal
  python -m pulse.workflow --yes    # approve without prompting (for scripted demos)
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from mcp_server.approvals import record_decision

ROOT = Path(__file__).resolve().parent.parent


def md_to_text(md: str) -> str:
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", md)   # links -> "title: url"
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = t.replace("**", "")
    t = re.sub(r"(?<![\w/])_([^_\n]+)_(?![\w/])", r"\1", t)  # italics only, keeps URLs intact
    t = re.sub(r"^>\s?", "  ", t, flags=re.M)
    return t.strip()


def build_actions(insights: dict, pulse: dict, explainer: dict, to: str = "") -> list[dict]:
    day = insights["window"]["end"]
    fee = insights.get("fee_issue") or {}
    fee_line = (f"{fee.get('label')}: {fee.get('confusion')} "
                f"({fee.get('mentions')} reviews mention it, {fee.get('confused_mentions')} with confusion cues)")
    entry = {
        "date": day,
        "top_themes": insights["top_themes"],
        "weekly_pulse": pulse["markdown"],
        "identified_fee_issue": fee_line,
        "explanation_bullets": explainer["bullets"],
        "source_links": [s["url"] for s in explainer["source_links"]],
    }
    subject = f"Weekly Product Pulse + Customer Clarification — {day}"
    body = "\n".join([
        "Hi team,", "",
        "Here is this week's product pulse from public Groww app reviews, followed by a reusable "
        "support snippet for the most misunderstood charge.", "",
        "WEEKLY PRODUCT PULSE", "--------------------",
        md_to_text(pulse["markdown"]), "",
        "SUPPORT SNIPPET (copy-paste ready)", "----------------------------------",
        md_to_text(explainer["markdown"]), "",
        "This is a draft prepared by the review-pulse workflow. Please review before sending.",
    ])
    return [
        {"tool": "append_to_doc", "args": {"entry": entry}},
        {"tool": "create_email_draft", "args": {"subject": subject, "body": body, "to": to}},
    ]


def preview(actions: list[dict]) -> str:
    a, e = actions[0]["args"]["entry"], actions[1]["args"]
    return "\n".join([
        "=" * 70, "PROPOSED ACTIONS (nothing has been written yet)", "=" * 70,
        "1) append_to_doc  -> notes doc",
        f"   date: {a['date']}",
        f"   top_themes: {', '.join(a['top_themes'])}",
        f"   identified_fee_issue: {a['identified_fee_issue'][:160]}",
        f"   explanation_bullets: {len(a['explanation_bullets'])} bullets",
        f"   source_links: {', '.join(a['source_links'])}",
        f"   weekly_pulse: {len(a['weekly_pulse'].split())} words (full text in outputs/weekly_pulse.md)",
        "",
        "2) create_email_draft  -> draft only, will NOT be sent",
        f"   to: {e['to'] or '(left blank)'}",
        f"   subject: {e['subject']}",
        f"   body: {len(e['body'].split())} words (pulse + support snippet)",
        "=" * 70,
    ])


async def _call_tools(approval_id: str, actions: list[dict]) -> list[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import os
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"],
                                   cwd=str(ROOT), env=dict(os.environ))
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            for a in actions:
                if a["tool"] not in tools:
                    results.append({"tool": a["tool"], "ok": False, "error": "tool not offered by server"})
                    continue
                res = await session.call_tool(a["tool"], {"approval_id": approval_id, **a["args"]})
                payload = res.structuredContent or {}
                if not payload and res.content:
                    try:
                        payload = json.loads(res.content[0].text)
                    except Exception:
                        payload = {"raw": res.content[0].text}
                if isinstance(payload, dict) and "result" in payload and len(payload) == 1:
                    payload = payload["result"]
                results.append({"tool": a["tool"], **payload})
    return results


def execute(actions: list[dict], approved: bool, reviewer: str = "local-user") -> dict:
    approval_id = record_decision(actions, approved, reviewer)
    if not approved:
        return {"approval_id": approval_id, "decision": "rejected", "results": []}
    results = asyncio.run(_call_tools(approval_id, actions))
    return {"approval_id": approval_id, "decision": "approved", "results": results}


def load_outputs() -> tuple[dict, dict, dict]:
    d = ROOT / "data"
    return (json.loads((d / "insights.json").read_text()),
            json.loads((d / "pulse.json").read_text()),
            json.loads((d / "explainer.json").read_text()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="approve without prompting")
    ap.add_argument("--to", default="", help="optional recipient for the draft")
    args = ap.parse_args()

    insights, pulse, explainer = load_outputs()
    if explainer.get("status") != "ok":
        sys.exit("The fee explainer is not ready: " + explainer.get("message", "run python -m pulse.explainer"))
    actions = build_actions(insights, pulse, explainer, args.to)
    print(preview(actions))
    approved = args.yes or input("Approve these 2 actions? Type 'approve' to continue: ").strip().lower() == "approve"
    out = execute(actions, approved)
    print(f"\nDecision: {out['decision']} (approval id {out['approval_id']}, logged in data/approvals.jsonl)")
    for r in out["results"]:
        print(" ", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
