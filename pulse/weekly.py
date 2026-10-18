"""Weekly Product Pulse (internal, <=250 words).

The code writes the parts that must be exact (theme stats, the 3 verbatim quotes);
the LLM writes only the key observation and 3 action ideas. Then the code checks:
  - total length <= 250 words
  - exactly 3 action ideas
  - every number in the LLM text exists in the insights (no invented stats)
  - no advice to users, no blame language
One retry with the failures listed; otherwise a deterministic template is used.

  python -m pulse.weekly          # reads data/insights.json, writes outputs/weekly_pulse.md
"""
import json
import re
from pathlib import Path

from pulse.llm import call_llm, llm_available, parse_json

ROOT = Path(__file__).resolve().parent.parent
WORD_LIMIT = 250
NUM = re.compile(r"\d+(?:\.\d+)?")

PULSE_SYSTEM = """You write the internal weekly product pulse for the Groww app's product team.
You get review statistics, the top themes, verbatim user quotes and one fee the users find confusing.
Write:
- "observation": 2 sentences on what is going wrong or trending (mention the fee confusion if it is relevant).
- "actions": exactly 3 concrete action ideas for the product team, each one sentence, under 22 words,
  starting with a verb. At least one must address the fee confusion.
Rules: use only the facts given; any number you write must appear in the input; no investment advice;
no blaming teams or users; do not repeat the quotes. Return ONLY JSON:
{"observation": "<text>", "actions": ["<idea>", "<idea>", "<idea>"]}"""


def count_words(md: str) -> int:
    text = re.sub(r"[#>*_`|-]+", " ", md)
    return len(re.findall(r"[\w₹%.,'’]+", text))


def _allowed_numbers(ins: dict) -> set[str]:
    blob = json.dumps(ins, ensure_ascii=False)
    nums = set(NUM.findall(blob))
    nums |= {"1", "2", "3"}  # ordinals like "top 3", "2 weeks"
    return nums


def _theme_line(s: dict) -> str:
    trend = {"rising": "↑ rising", "falling": "↓ falling"}.get(s["trend"], "→ steady")
    return f"- **{s['theme']}**: {s['reviews']} reviews ({s['share_pct']}%), avg {s['avg_rating']}★, {trend}"


def render(ins: dict, observation: str, actions: list[str]) -> str:
    top = [s for s in ins["themes"] if s["theme"] in ins["top_themes"]]
    w = ins["window"]
    lines = [
        f"# Groww Weekly Product Pulse, week ending {w['end']}",
        f"_{ins['reviews_analysed']} public app reviews, {w['start']} to {w['end']}_",
        "",
        "## Top themes",
        *[_theme_line(s) for s in top],
        "",
        "## What users are saying",
        *[f"> \"{q['quote']}\" ({q['rating']}★, {q['theme']})" for q in ins["quotes"]],
        "",
        "## Key observation",
        observation.strip(),
        "",
        "## Action ideas",
        *[f"{i}. {a.strip()}" for i, a in enumerate(actions, 1)],
    ]
    return "\n".join(lines) + "\n"


def validate(ins: dict, observation: str, actions: list[str]) -> list[str]:
    problems = []
    if len(actions) != 3:
        problems.append(f"need exactly 3 actions, got {len(actions)}")
    allowed = _allowed_numbers(ins)
    bad = [n for n in NUM.findall(observation + " " + " ".join(actions)) if n not in allowed]
    if bad:
        problems.append(f"numbers not in the data: {sorted(set(bad))}")
    if re.search(r"\b(?:you should invest|buy|sell now|guaranteed|incompetent|lazy)\b",
                 observation + " " + " ".join(actions), re.I):
        problems.append("contains advice or blame language")
    words = count_words(render(ins, observation, actions))
    if words > WORD_LIMIT:
        problems.append(f"pulse is {words} words, limit is {WORD_LIMIT}")
    return problems


ACTION_HINTS = [
    (r"charge|fee|pricing|cost", "Add a charges breakdown on the order and redemption screens before users confirm."),
    (r"withdraw|payment|refund|upi|money", "Add a withdrawal status tracker showing the expected credit date."),
    (r"crash|glitch|perform|slow|bug|app", "Prioritise stability fixes for the screens named in the latest-version reviews."),
    (r"support|service|care", "Publish support response-time targets and add a ticket status view in the app."),
    (r"order|trad|f&o|execution", "Show the rejection reason on every rejected order, in plain language."),
    (r"kyc|onboard|account", "Simplify the KYC steps users drop off at and show progress clearly."),
]


def _action_hint(theme: str) -> str | None:
    for pat, text in ACTION_HINTS:
        if re.search(pat, theme, re.I):
            return text
    return None


def template(ins: dict) -> tuple[str, list[str]]:
    """Deterministic fallback when the LLM is unavailable or fails validation twice."""
    top = [s for s in ins["themes"] if s["theme"] in ins["top_themes"]]
    rising = [s["theme"] for s in top if s["trend"] == "rising"]
    lead = top[0]
    obs = (f"{lead['theme']} is the largest theme with {lead['reviews']} reviews and an average of "
           f"{lead['avg_rating']}★.")
    if rising:
        obs += f" Rising in the last 2 weeks: {', '.join(rising)}."
    fee = ins.get("fee_issue")
    actions = []
    if fee:
        obs += f" {fee['label']} is the most misunderstood charge ({fee['mentions']} mentions)."
        actions.append(f"Show the charge clearly before order or redemption confirmation: {fee['label']}, with a one-line explainer.")
    for s in top:
        if len(actions) == 3:
            break
        if fee and re.search(r"charge|fee|pricing|cost", s["theme"], re.I):
            continue  # already covered by the fee action
        hint = _action_hint(s["theme"])
        if hint and hint not in actions:
            actions.append(hint)
    while len(actions) < 3:
        actions.append("Share this week's top quotes with support so they can prepare ready replies.")
    return obs, actions[:3]


def generate(ins: dict, use_llm: bool | None = None) -> dict:
    use_llm = llm_available() if use_llm is None else use_llm
    payload = {
        "reviews_analysed": ins["reviews_analysed"], "window": ins["window"],
        "top_themes": [s for s in ins["themes"] if s["theme"] in ins["top_themes"]],
        "quotes": [q["quote"] for q in ins["quotes"]],
        "fee_issue": {k: ins["fee_issue"].get(k) for k in
                      ("label", "mentions", "confused_mentions", "confusion", "typical_misunderstanding")}
        if ins.get("fee_issue") else None,
    }
    problems, attempts, source = [], 0, "template"
    obs, actions = None, None
    if use_llm:
        prompt = json.dumps(payload, ensure_ascii=False, indent=1)
        for attempts in (1, 2):
            p = prompt if attempts == 1 else prompt + "\n\nFix these problems: " + "; ".join(problems)
            try:
                out = parse_json(call_llm(PULSE_SYSTEM, p, json_mode=True, max_tokens=500))
                o, a = str(out.get("observation", "")), [str(x) for x in out.get("actions", [])]
                problems = validate(ins, o, a)
                if not problems:
                    obs, actions, source = o, a, "llm"
                    break
            except Exception as e:
                problems = [f"bad model output: {type(e).__name__}"]
    if obs is None:
        obs, actions = template(ins)
    md = render(ins, obs, actions)
    return {"markdown": md, "words": count_words(md), "observation": obs, "actions": actions,
            "source": source, "attempts": attempts, "last_problems": problems if source == "template" else []}


def main() -> None:
    ins = json.loads((ROOT / "data" / "insights.json").read_text())
    res = generate(ins)
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "weekly_pulse.md").write_text(res["markdown"], encoding="utf-8")
    (ROOT / "data" / "pulse.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(res["markdown"])
    print(f"[{res['words']} words, written by {res['source']}] saved outputs/weekly_pulse.md")


if __name__ == "__main__":
    main()
