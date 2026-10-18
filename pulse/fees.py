"""Deterministic fee/charge signal detection.

Counts how many reviews mention each specific fee, and how many of those also
show confusion ("why", "hidden", "without informing", "didn't know", ...).
The LLM later only *describes* the confusion for the winning fee; it never picks
the fee on its own, so the choice is traceable to review counts.
"""
import re

import pandas as pd

FEES = {
    "dp_charges": {
        "label": "DP (depository) charges on selling shares",
        "patterns": [r"\bdp\s*(?:charge|fee)s?\b", r"\bdepository\s+(?:charge|fee)", r"\bcdsl\s+(?:charge|fee)"],
    },
    "brokerage": {
        "label": "Brokerage per order",
        "patterns": [r"\bbrokerage\b", r"\b20\s*(?:rs|rupees|₹)\s*(?:per|each|/)?\s*(?:order|trade)\b"],
    },
    "exit_load": {
        "label": "Mutual fund exit load on redemption",
        "patterns": [r"\bexit\s*load\b", r"\bredemption\s+(?:charge|fee)"],
    },
    "stamp_duty": {
        "label": "Stamp duty on mutual fund purchases",
        "patterns": [r"\bstamp\s*duty\b"],
    },
    "account_maintenance": {
        "label": "Account maintenance / annual charges",
        "patterns": [r"\bamc\s+(?:charge|fee)", r"\baccount\s+maintenance\b", r"\bannual\s+(?:charge|fee)"],
    },
    "mtf_interest": {
        "label": "MTF / margin interest and pledge charges",
        "patterns": [r"\bmtf\b", r"\bmargin\s+(?:trading\s+)?interest\b", r"\bpledge\s+(?:charge|fee)", r"\binterest\s+charged\b"],
    },
    "statutory_charges": {
        "label": "Statutory charges (STT, GST, exchange and SEBI fees)",
        "patterns": [r"\bstt\b", r"\bgst\b", r"\bexchange\s+(?:transaction\s+)?(?:charge|fee)", r"\bsebi\s+(?:turnover\s+)?fee"],
    },
}

GENERIC = re.compile(r"\bhidden\s+(?:charge|fee|cost)s?\b|\bextra\s+(?:charge|fee)s?\b|\bcharges?\s+(?:deducted|cut)\b"
                     r"|\bdeducted\b|\bcut\s+from\b", re.I)
CONFUSION = re.compile(
    r"\bwhy\b|\bhidden\b|\bwithout\s+(?:informing|telling|notice|any\s+information)\b|\bdidn'?t\s+know\b|\bdid\s+not\s+know\b"
    r"|\bnot\s+(?:mentioned|informed|clear|transparent)\b|\bno\s+(?:clarity|information|explanation)\b|\bunexpected"
    r"|\bconfus|\bwhat\s+is\s+this\s+(?:charge|fee)|\bsuddenly\b|\bextra\b|\bsurprise", re.I)

_COMPILED = {k: [re.compile(p, re.I) for p in v["patterns"]] for k, v in FEES.items()}


def tag_fees(text: str) -> list[str]:
    return [k for k, pats in _COMPILED.items() if any(p.search(text) for p in pats)]


def fee_signals(df: pd.DataFrame) -> dict:
    """Return per-fee counts and the ranked list. Works on the cleaned reviews table."""
    tags = df["review_text"].map(tag_fees)
    confused = df["review_text"].str.contains(CONFUSION)
    generic = df["review_text"].str.contains(GENERIC)
    rows = []
    for fee, meta in FEES.items():
        mask = tags.map(lambda t, f=fee: f in t)
        n = int(mask.sum())
        if not n:
            continue
        nc = int((mask & confused).sum())
        sub = df[mask]
        rows.append({
            "fee": fee, "label": meta["label"], "mentions": n, "confused_mentions": nc,
            "avg_rating": round(float(sub["rating"].mean()), 2),
            "review_ids": sub["review_id"].tolist(),
        })
    # rank by confused mentions first, then all mentions
    rows.sort(key=lambda r: (r["confused_mentions"], r["mentions"]), reverse=True)
    return {
        "ranked": rows,
        "generic_charge_mentions": int((generic & tags.map(len).eq(0)).sum()),
        "total_reviews": int(len(df)),
    }
