"""Tests for the weekly pulse. Run offline with the LLM mocked."""
import json
import pandas as pd
import pulse.weekly as weekly
from pulse.analyze import run_analysis
from pulse.weekly import count_words, generate

DF = pd.read_csv("tests/fixtures/sample_reviews.csv", dtype={"review_id": str})
INS, _ = run_analysis(DF, use_llm=False)


def stub(responses):
    it = iter(responses)
    return lambda system, user, **k: next(it)


def check_structure(md):
    for h in ("## Top themes", "## What users are saying", "## Key observation", "## Action ideas"):
        assert h in md
    for q in INS["quotes"]:
        assert q["quote"] in md  # quotes inserted verbatim by code
    assert count_words(md) <= 250


def test_template_path():
    res = generate(INS, use_llm=False)
    check_structure(res["markdown"])
    assert res["source"] == "template" and len(res["actions"]) == 3


GOOD = {"observation": "Charges and fees lead with 7 reviews and an average of 1.71★. DP charges on selling are the main confusion.",
        "actions": ["Show DP charges on the sell confirmation screen.",
                    "Add a withdrawal status tracker with expected credit time.",
                    "Fix the crash on the portfolio page reported after the latest update."]}


def test_llm_path(monkeypatch):
    monkeypatch.setattr(weekly, "call_llm", stub([json.dumps(GOOD)]))
    res = generate(INS, use_llm=True)
    check_structure(res["markdown"])
    assert res["source"] == "llm" and res["attempts"] == 1


def test_invented_number_retried(monkeypatch):
    bad = dict(GOOD, observation="Charges complaints rose 340% this week.")
    monkeypatch.setattr(weekly, "call_llm", stub([json.dumps(bad), json.dumps(GOOD)]))
    res = generate(INS, use_llm=True)
    assert res["source"] == "llm" and res["attempts"] == 2 and "340" not in res["markdown"]


def test_too_long_falls_back_to_template(monkeypatch):
    long = dict(GOOD, observation="word " * 300)
    monkeypatch.setattr(weekly, "call_llm", stub([json.dumps(long), json.dumps(long)]))
    res = generate(INS, use_llm=True)
    assert res["source"] == "template"
    check_structure(res["markdown"])


def test_wrong_action_count_rejected(monkeypatch):
    two = dict(GOOD, actions=GOOD["actions"][:2])
    monkeypatch.setattr(weekly, "call_llm", stub([json.dumps(two), json.dumps(GOOD)]))
    assert generate(INS, use_llm=True)["attempts"] == 2
