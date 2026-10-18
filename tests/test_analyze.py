"""Tests for review analysis. Run offline with the LLM mocked."""
import json
import pandas as pd
import pytest
import pulse.themes as themes
from pulse.analyze import run_analysis
from pulse.fees import fee_signals, tag_fees
from pulse.themes import verify_quote

DF = pd.read_csv("tests/fixtures/sample_reviews.csv", dtype={"review_id": str})


def test_fee_tagging():
    assert tag_fees("DP charges were deducted") == ["dp_charges"]
    assert tag_fees("exit load on redemption") == ["exit_load"]
    assert tag_fees("great app") == []


def test_fee_ranking_picks_most_confused_fee():
    top = fee_signals(DF)["ranked"][0]
    assert top["fee"] == "dp_charges" and top["mentions"] == 5 and top["confused_mentions"] >= 3


def test_keyword_pipeline():
    ins, labeled = run_analysis(DF, use_llm=False)
    assert ins["theme_method"] == "keyword"
    assert 1 <= len(ins["themes"]) <= 5 and len(ins["top_themes"]) == 3
    assert len(ins["quotes"]) == 3
    for q in ins["quotes"]:  # every quote copied verbatim from its review
        text = labeled.set_index("review_id").loc[q["review_id"], "review_text"]
        assert verify_quote(q["quote"], text)
        assert "[phone]" not in q["quote"]
    assert ins["fee_issue"]["fee"] == "dp_charges"
    assert ins["fee_issue"]["quote"] is not None


def test_verify_quote_rejects_paraphrase_and_masks():
    real = "Why were DP charges deducted when I sold my shares? Nobody told me about this charge before selling."
    assert verify_quote("Why were DP charges deducted when I sold my shares?", real)
    assert not verify_quote("Why were DP fees deducted after I sold my shares?", real)
    assert not verify_quote("Call me on [phone] to fix my withdrawal now please", "Call me on [phone] to fix my withdrawal now please")


def test_llm_pipeline_with_stub(monkeypatch):
    calls = {"quote": 0}

    def mock_llm(system, user, **k):
        if "Propose AT MOST" in system:
            return json.dumps({"themes": [
                {"name": "Unclear charges", "description": "fees"},
                {"name": "Withdrawal delays", "description": "money"},
                {"name": "App glitches", "description": "crashes"},
                {"name": "Slow support", "description": "support"},
                {"name": "Order issues", "description": "orders"},
                {"name": "Extra sixth theme", "description": "should be cut"}]})
        if "Assign each review" in system:
            ids = [ln.split(":")[0] for ln in user.split("REVIEWS:\n")[1].splitlines()]
            m = {}
            for rid in ids:
                t = DF.set_index("review_id").loc[rid, "review_text"].lower()
                m[rid] = (1 if "charge" in t or "brokerage" in t or "exit load" in t else
                          2 if "withdraw" in t or "upi" in t or "credited" in t else
                          3 if "app" in t and ("crash" in t or "slow" in t or "hang" in t or "logged" in t) else
                          4 if "support" in t or "customer" in t else
                          5 if "order" in t or "option" in t else 0)
            m[ids[0]] = 99  # invalid label must be ignored
            return json.dumps({"labels": m})
        if "Pick ONE short" in system:
            calls["quote"] += 1
            if calls["quote"] == 1:  # first attempt paraphrases -> must be rejected and retried
                return json.dumps({"review_id": "T000", "quote": "DP fees were taken when I sold, no one warned me"})
            rid = [ln.split(" ")[0] for ln in user.split("REVIEWS:\n")[1].splitlines()][0]
            text = DF.set_index("review_id").loc[rid, "review_text"]
            return json.dumps({"review_id": rid, "quote": " ".join(text.split()[:12])})
        if "mention one specific fee" in system:
            return json.dumps({"confusion": "Users don't expect a charge when selling shares.",
                               "typical_misunderstanding": "Zero brokerage means selling is free.",
                               "review_ids": ["T000", "T002", "R99999999"]})
        raise AssertionError(system[:40])

    monkeypatch.setattr(themes, "call_llm", mock_llm)
    ins, labeled = run_analysis(DF, use_llm=True)
    assert ins["theme_method"] == "llm"
    assert len(ins["themes"]) <= 5 and "Extra sixth theme" not in ins["top_themes"]
    assert ins["top_themes"][0] == "Unclear charges"
    assert len(ins["quotes"]) == 3
    for q in ins["quotes"]:
        assert verify_quote(q["quote"], labeled.set_index("review_id").loc[q["review_id"], "review_text"])
    assert ins["fee_issue"]["example_review_ids"] == ["T000", "T002"]  # unknown id dropped
    assert ins["fee_issue"]["typical_misunderstanding"].startswith("Zero brokerage")
