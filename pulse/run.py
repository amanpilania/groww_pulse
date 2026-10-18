"""Run the whole pipeline in one go (steps 2-4), then the approval-gated MCP step.

  python -m pulse.run                 # analyse data/reviews.csv, write outputs, ask for approval
  python -m pulse.run --no-actions    # stop before the approval step

Writes:
  outputs/weekly_pulse.md       weekly product pulse (<=250 words)
  outputs/fee_explainer.md      fee explainer (<=6 bullets, 2 links, Last checked)
  outputs/reviews_sample.csv    first 50 cleaned reviews (deliverable sample)
  outputs/RESULTS.md            one-page summary incl. the fee issue found
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from pulse import explainer, weekly
from pulse.analyze import run_analysis
from pulse.llm import llm_available

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"


def results_md(ins: dict, pulse: dict, exp: dict) -> str:
    f = ins.get("fee_issue") or {}
    rows = "\n".join(f"| {s['theme']} | {s['reviews']} | {s['avg_rating']} | {s['trend']} |" for s in ins["themes"])
    fees = "\n".join(f"| {r['label']} | {r['mentions']} | {r['confused_mentions']} |" for r in ins["fee_signals"]) or "| none | 0 | 0 |"
    return f"""# Run results

- Reviews analysed: {ins['reviews_analysed']} ({ins['window']['start']} to {ins['window']['end']})
- Theme method: {ins['theme_method']} · pulse written by: {pulse['source']} ({pulse['words']} words) · explainer written by: {exp.get('written_by', 'n/a')}

## Themes (max 5)
| Theme | Reviews | Avg ★ | Trend |
|---|---|---|---|
{rows}

Top 3: {', '.join(ins['top_themes'])}

## Fee issue identified from reviews
**{f.get('label', 'none found')}**: {f.get('mentions', 0)} reviews mention it, {f.get('confused_mentions', 0)} with confusion cues.

{f.get('confusion') or ''}

What users seem to believe: {f.get('typical_misunderstanding') or 'n/a'}

### All fee signals (how the fee was chosen)
| Fee | Mentions | With confusion cues |
|---|---|---|
{fees}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DATA / "reviews.csv"))
    ap.add_argument("--no-actions", action="store_true")
    args = ap.parse_args()

    print(f"AI: {'Gemini' if llm_available() else 'off (keyword themes + templates)'}")
    df = pd.read_csv(args.csv, dtype={"review_id": str})
    ins, labeled = run_analysis(df)
    pulse = weekly.generate(ins)
    exp = explainer.generate(ins.get("fee_issue"))

    OUT.mkdir(exist_ok=True)
    (DATA / "insights.json").write_text(json.dumps(ins, indent=2, ensure_ascii=False))
    (DATA / "pulse.json").write_text(json.dumps(pulse, indent=2, ensure_ascii=False))
    (DATA / "explainer.json").write_text(json.dumps(exp, indent=2, ensure_ascii=False))
    labeled.to_csv(DATA / "reviews_labeled.csv", index=False)
    df.head(50).to_csv(OUT / "reviews_sample.csv", index=False)
    (OUT / "weekly_pulse.md").write_text(pulse["markdown"], encoding="utf-8")
    if exp["status"] == "ok":
        (OUT / "fee_explainer.md").write_text(exp["markdown"], encoding="utf-8")
    (OUT / "RESULTS.md").write_text(results_md(ins, pulse, exp), encoding="utf-8")

    print("\n" + pulse["markdown"])
    print(exp["markdown"] if exp["status"] == "ok" else exp["message"])
    print("Saved outputs/weekly_pulse.md, outputs/fee_explainer.md, outputs/RESULTS.md, outputs/reviews_sample.csv\n")

    if not args.no_actions and exp["status"] == "ok":
        subprocess.run([sys.executable, "-m", "pulse.workflow"], cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
