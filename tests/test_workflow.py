"""Tests for approval gating in the MCP server (local backend)."""
import json
import pandas as pd
import pytest
import mcp_server.approvals as appr
from mcp_server import server
from pulse import explainer, weekly
from pulse.analyze import run_analysis
from pulse.workflow import build_actions, execute, md_to_text


@pytest.fixture
def actions(tmp_path, monkeypatch):
    monkeypatch.setenv("APPROVALS_LEDGER", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("BACKEND", "local")
    ins, _ = run_analysis(pd.read_csv("tests/fixtures/sample_reviews.csv", dtype={"review_id": str}), use_llm=False)
    return build_actions(ins, weekly.generate(ins, use_llm=False), explainer.generate(ins["fee_issue"], use_llm=False))


def call(action, approval_id):
    fn = getattr(server, action["tool"])
    return fn(approval_id=approval_id, **action["args"])


def test_entry_has_required_fields(actions):
    assert set(actions[0]["args"]["entry"]) == {"date", "top_themes", "weekly_pulse", "identified_fee_issue",
                                                 "explanation_bullets", "source_links"}
    assert actions[1]["args"]["subject"].startswith("Weekly Product Pulse + Customer Clarification — ")


def test_approved_actions_run_once(actions, tmp_path):
    aid = appr.record_decision(actions, approved=True)
    assert call(actions[0], aid)["ok"] and call(actions[1], aid)["ok"]
    assert (tmp_path / "outputs" / "notes_doc.md").exists()
    assert (tmp_path / "outputs" / "email_draft.eml").exists()
    again = call(actions[0], aid)  # an approval can't be reused
    assert not again["ok"] and "already used" in again["error"]


def test_rejected_means_nothing_written(actions, tmp_path):
    aid = appr.record_decision(actions, approved=False)
    assert not call(actions[0], aid)["ok"] and not call(actions[1], aid)["ok"]
    assert not (tmp_path / "outputs").exists()


def test_tampered_payload_refused(actions, tmp_path):
    aid = appr.record_decision(actions, approved=True)
    tampered = {"tool": "create_email_draft", "args": dict(actions[1]["args"], body="something else")}
    res = call(tampered, aid)
    assert not res["ok"] and "differs" in res["error"]


def test_unknown_approval_refused(actions):
    assert not call(actions[0], "APR-0000000000")["ok"]


def test_end_to_end_over_mcp_stdio(actions, tmp_path):
    out = execute(actions, approved=True)
    assert out["decision"] == "approved"
    assert [r["ok"] for r in out["results"]] == [True, True], out


def test_md_to_text_keeps_urls():
    t = md_to_text("1. [Groww](https://groww.in/help/x_y_z)\n_Last checked: 18 October 2026_")
    assert "https://groww.in/help/x_y_z" in t and "Last checked: 18 October 2026" in t and "_Last" not in t
