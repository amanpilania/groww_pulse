"""Collect public Groww reviews from the last N weeks and clean them.

Sources (both public):
  - Google Play: package com.nextbillion.groww (via the google-play-scraper package)
  - Apple App Store (India): app id 1404871703 (via Apple's public customer-reviews feed)

Output:
  data/reviews.csv  columns: review_id, date, source, rating, review_text, app_version

Privacy: reviewer names, avatars and profile links are never kept. Phone numbers,
emails, PAN, Aadhaar-like and long account-like numbers inside the text are masked.

Usage:
  python scripts/collect_reviews.py                  # last 12 weeks, both stores
  python scripts/collect_reviews.py --weeks 8 --max-play 3000
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pulse.clean import clean_reviews  # noqa: E402

PLAY_PACKAGE = "com.nextbillion.groww"
APPSTORE_ID = "1404871703"
APPSTORE_FEED = ("https://itunes.apple.com/in/rss/customerreviews/page={page}"
                 "/id={app_id}/sortby=mostrecent/json")


def collect_play(cutoff: datetime, max_reviews: int) -> list[dict]:
    from google_play_scraper import Sort, reviews

    rows, token = [], None
    while len(rows) < max_reviews:
        batch, token = reviews(PLAY_PACKAGE, lang="en", country="in", sort=Sort.NEWEST,
                               count=200, continuation_token=token)
        if not batch:
            break
        for r in batch:
            when = r["at"].replace(tzinfo=timezone.utc)
            if when < cutoff:
                return rows
            rows.append({
                "date": when.date().isoformat(), "source": "google_play",
                "rating": r.get("score"), "review_text": r.get("content") or "",
                "app_version": r.get("reviewCreatedVersion") or "",
            })
        if token is None:
            break
        time.sleep(1)  # be polite
    return rows


def collect_appstore(cutoff: datetime, pages: int = 10) -> list[dict]:
    rows = []
    for page in range(1, pages + 1):
        resp = requests.get(APPSTORE_FEED.format(page=page, app_id=APPSTORE_ID), timeout=30)
        if resp.status_code != 200:
            break
        entries = resp.json().get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        reviews_only = [e for e in entries if "im:rating" in e]
        if not reviews_only:
            break
        for e in reviews_only:
            when = datetime.fromisoformat(e["updated"]["label"]).astimezone(timezone.utc)
            if when < cutoff:
                continue
            title = e.get("title", {}).get("label", "")
            body = e.get("content", {}).get("label", "")
            rows.append({
                "date": when.date().isoformat(), "source": "app_store",
                "rating": int(e["im:rating"]["label"]),
                "review_text": f"{title}. {body}".strip(". ") if title else body,
                "app_version": e.get("im:version", {}).get("label", ""),
            })
        time.sleep(1)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--max-play", type=int, default=4000)
    ap.add_argument("--skip-appstore", action="store_true")
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(weeks=args.weeks)
    print(f"Collecting reviews since {cutoff.date()} ...")

    raw = []
    try:
        play = collect_play(cutoff, args.max_play)
        print(f"Google Play: {len(play)} reviews")
        raw += play
    except Exception as e:
        print(f"Google Play failed: {type(e).__name__}: {e}")
    if not args.skip_appstore:
        try:
            ios = collect_appstore(cutoff)
            print(f"App Store: {len(ios)} reviews")
            raw += ios
        except Exception as e:
            print(f"App Store failed: {type(e).__name__}: {e}")

    if not raw:
        sys.exit("No reviews collected. Check your internet connection and try again.")

    df = clean_reviews(pd.DataFrame(raw))
    df["review_id"] = [
        "R" + hashlib.sha1(f"{d}|{s}|{t}".encode()).hexdigest()[:8]
        for d, s, t in zip(df["date"], df["source"], df["review_text"])
    ]
    df = df[["review_id", "date", "source", "rating", "review_text", "app_version"]]
    out = ROOT / "data" / "reviews.csv"
    df.to_csv(out, index=False)
    meta = {"collected_on": datetime.now(timezone.utc).date().isoformat(),
            "window_start": cutoff.date().isoformat(), "rows": len(df),
            "by_source": df["source"].value_counts().to_dict()}
    (ROOT / "data" / "reviews_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Saved {len(df)} cleaned reviews to {out}")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
