"""Tests for the fee explainer. Run offline with the LLM mocked."""
import json
import re
import pulse.explainer as ex
from pulse.explainer import generate, load_bank

BANK = load_bank()
DP = {"fee": "dp_charges", "label": "DP (depository) charges on selling shares", "mentions": 5,
      "confused_mentions": 5, "typical_misunderstanding": "Zero brokerage or zero AMC means selling is free."}


def stub(responses):
    it = iter(responses)
    return lambda system, user, **k: next(it)


def check(md):
    bullets = [l for l in md.splitlines() if l.startswith("- ")]
    assert 3 <= len(bullets) <= 6
    assert len(re.findall(r"\]\(https://", md)) == 2  # exactly 2 official links
    assert "Last checked: 18 October 2026" in md


def test_every_fee_has_two_links_and_facts_from_them():
    for fee, spec in BANK["fees"].items():
        facts, links = ex.usable_facts(BANK, fee)
        assert len(links) == 2 and len(facts) >= 3, fee
        assert all(l["url"].startswith("https://") for l in links)


def test_template():
    res = generate(DP, BANK, use_llm=False)
    assert res["status"] == "ok" and res["written_by"] == "template"
    check(res["markdown"])


GOOD = {"bullets": [
    {"text": "DP charges apply each time you sell shares from your demat account; buying shares does not attract them.", "facts": [1]},
    {"text": "For a sale value of ₹100 or more, the charge is ₹20.00 for men and ₹19.75 for women, plus 18% GST.", "facts": [2, 4]},
    {"text": "Below ₹100 sale value, Groww waives its ₹16.50 share and only the depository charge applies.", "facts": [3]},
    {"text": "Zero account maintenance charges do not cover DP charges, which are separate and still apply on sells.", "facts": [5]},
]}


def test_llm(monkeypatch):
    monkeypatch.setattr(ex, "call_llm", stub([json.dumps(GOOD)]))
    res = generate(DP, BANK, use_llm=True)
    assert res["written_by"] == "llm" and res["attempts"] == 1
    check(res["markdown"])


def test_invented_number_and_advice_retried(monkeypatch):
    bad = {"bullets": GOOD["bullets"][:3] + [{"text": "We recommend selling once a month to save ₹50.", "facts": [1]}]}
    monkeypatch.setattr(ex, "call_llm", stub([json.dumps(bad), json.dumps(GOOD)]))
    res = generate(DP, BANK, use_llm=True)
    assert res["attempts"] == 2 and "₹50" not in res["markdown"]


def test_too_many_bullets_falls_back(monkeypatch):
    many = {"bullets": GOOD["bullets"] * 2}
    monkeypatch.setattr(ex, "call_llm", stub([json.dumps(many), json.dumps(many)]))
    res = generate(DP, BANK, use_llm=True)
    assert res["written_by"] == "template"
    check(res["markdown"])


def test_unknown_fee_asks_for_sources():
    res = generate({"fee": "mtf_interest", "label": "MTF interest"}, BANK, use_llm=False)
    assert res["status"] == "needs_sources"
