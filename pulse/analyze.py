"""Review intelligence layer.

Input : data/reviews.csv (from scripts/collect_reviews.py)
Output: data/insights.json and data/reviews_labeled.csv

  python -m pulse.analyze                 # LLM themes if GEMINI_API_KEY is set, else keyword themes
  python -m pulse.analyze --keywords      # force the offline keyword taxonomy
  python -m pulse.analyze --csv path.csv  # analyse another CSV
"""
import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from pulse.fees import fee_signals
from pulse.llm import llm_available
from pulse.themes import (MAX_THEMES, _fallback_quote, classify, describe_fee_confusion,
                          discover_themes, keyword_assign, pick_quote, theme_stats)

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"review_id", "date", "source", "rating", "review_text"}


def run_analysis(df: pd.DataFrame, use_llm: bool | None = None) -> tuple[dict, pd.DataFrame]:
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")
    use_llm = llm_available() if use_llm is None else use_llm
    df = df.copy()

    method = "keyword"
    if use_llm:
        try:
            themes = discover_themes(df)
            df["theme"] = classify(df, themes)
            method = "llm"
        except Exception:
            themes, df["theme"] = keyword_assign(df)
    else:
        themes, df["theme"] = keyword_assign(df)
    themes = themes[:MAX_THEMES]

    stats = theme_stats(df, themes)
    top3 = stats[:3]

    # 3 real quotes: one per top theme, each verified word-for-word against its review
    quotes, used = [], set()
    for s in top3:
        q = pick_quote(df, s["theme"], method == "llm", used)
        if q:
            q["theme"] = s["theme"]
            quotes.append(q)
            used.add(q["review_id"])

    # fee confusion: winner chosen by counts; LLM only describes it
    fees = fee_signals(df)
    fee_issue = None
    if fees["ranked"]:
        top_fee = fees["ranked"][0]
        fee_issue = describe_fee_confusion(df, top_fee, method == "llm")
        fq = _fallback_quote(df[df["review_id"].isin(fee_issue["example_review_ids"] or top_fee["review_ids"])])
        fee_issue["quote"] = fq

    dates = pd.to_datetime(df["date"])
    insights = {
        "generated_on": date.today().isoformat(),
        "window": {"start": dates.min().date().isoformat(), "end": dates.max().date().isoformat(),
                   "weeks": round((dates.max() - dates.min()).days / 7, 1)},
        "reviews_analysed": int(len(df)),
        "unassigned_reviews": int(df["theme"].isna().sum()),
        "theme_method": method,
        "themes": stats,
        "top_themes": [s["theme"] for s in top3],
        "quotes": quotes,
        "fee_signals": [{k: v for k, v in r.items() if k != "review_ids"} for r in fees["ranked"]],
        "generic_charge_mentions": fees["generic_charge_mentions"],
        "fee_issue": fee_issue,
    }
    return insights, df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "reviews.csv"))
    ap.add_argument("--keywords", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype={"review_id": str})
    insights, labeled = run_analysis(df, use_llm=False if args.keywords else None)
    (ROOT / "data" / "insights.json").write_text(json.dumps(insights, indent=2, ensure_ascii=False))
    labeled.to_csv(ROOT / "data" / "reviews_labeled.csv", index=False)

    print(f"{insights['reviews_analysed']} reviews, {insights['window']['start']} to {insights['window']['end']} "
          f"(themes: {insights['theme_method']})\n")
    for s in insights["themes"]:
        print(f"  {s['theme']:<36} {s['reviews']:>4} reviews  {s['avg_rating']}★  {s['trend']}")
    print("\nTop 3:", ", ".join(insights["top_themes"]))
    for q in insights["quotes"]:
        print(f'  "{q["quote"]}" ({q["rating"]}★, {q["theme"]})')
    f = insights["fee_issue"]
    if f:
        print(f"\nFee issue: {f['label']} ({f['mentions']} mentions, {f['confused_mentions']} confused)")
        print(" ", f["confusion"])
    else:
        print("\nNo fee or charge mentions found.")
    print("\nSaved data/insights.json and data/reviews_labeled.csv")


if __name__ == "__main__":
    main()
