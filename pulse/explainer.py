"""Fee explainer (customer-facing, <=6 bullets, 2 official links, "Last checked").

The fee comes from Step 2 (data/insights.json -> fee_issue), so the explainer always
answers what reviews are actually confused about.

Facts come only from data/fee_facts.json: short statements restated from official
pages, each tagged with its source. The explainer uses exactly the 2 sources listed
for that fee, and only facts from those 2 sources, so every bullet is backed by a link.

LLM path: writes neutral bullets that each cite fact numbers; the code checks
bullet count, citations, numbers, length and tone. One retry, then a template
that uses the facts directly.

  python -m pulse.explainer      # writes outputs/fee_explainer.md and data/explainer.json
"""
import json
import re
from datetime import date
from pathlib import Path

from pulse.llm import call_llm, llm_available, parse_json

ROOT = Path(__file__).resolve().parent.parent
MAX_BULLETS = 6
MAX_BULLET_WORDS = 40
NUM = re.compile(r"\d+(?:[.,]\d+)*")
BANNED = re.compile(
    r"\b(?:you should|we recommend|recommend|avoid selling|don'?t sell|better to|best way|cheaper than|"
    r"unfair|sorry|unfortunately|rip[- ]?off|scam|guarantee)\b|https?://|www\.", re.I)

EXPLAINER_SYSTEM = """You write a short, neutral, facts-only explainer about one Groww fee for customers.
It will be reused by the support team as a ready reply.
Use ONLY the numbered FACTS. Do not add facts, numbers, opinions or advice. Do not apologise or judge.
Write 4 to 6 bullets, each one plain sentence of at most 35 words. Start with what the fee is and when it
applies, and make sure one bullet directly clears up the users' misunderstanding using the facts.
Each bullet must list the fact numbers it is based on. Never write URLs.
Return ONLY JSON: {"bullets": [{"text": "<sentence>", "facts": [<numbers>]}]}"""


def _n(x: str) -> str:
    x = x.replace(",", "")
    try:
        return str(float(x))
    except ValueError:
        return x


def load_bank(path: Path | None = None) -> dict:
    return json.loads((path or ROOT / "data" / "fee_facts.json").read_text(encoding="utf-8"))


def usable_facts(bank: dict, fee: str) -> tuple[list[dict], list[dict]]:
    spec = bank["fees"][fee]
    links = [dict(bank["sources"][s], id=s) for s in spec["primary_links"][:2]]
    ids = {l["id"] for l in links}
    return [f for f in spec["facts"] if f["source"] in ids], links


def validate(bullets: list[dict], facts: list[dict]) -> list[str]:
    problems = []
    if not 3 <= len(bullets) <= MAX_BULLETS:
        problems.append(f"need 3-{MAX_BULLETS} bullets, got {len(bullets)}")
    for i, b in enumerate(bullets, 1):
        text, cited = str(b.get("text", "")), b.get("facts") or []
        if not cited or not all(isinstance(c, int) and 1 <= c <= len(facts) for c in cited):
            problems.append(f"bullet {i}: missing or invalid fact numbers")
            continue
        if len(text.split()) > MAX_BULLET_WORDS:
            problems.append(f"bullet {i}: too long")
        if BANNED.search(text):
            problems.append(f"bullet {i}: advice, opinion or URL")
        allowed = {_n(x) for c in cited for x in NUM.findall(facts[c - 1]["text"])}
        bad = [x for x in NUM.findall(text) if _n(x) not in allowed]
        if bad:
            problems.append(f"bullet {i}: numbers not in its cited facts: {bad}")
    return problems


def render(fee_name: str, bullets: list[str], links: list[dict], checked: str) -> str:
    checked_h = date.fromisoformat(checked).strftime("%d %B %Y").lstrip("0")
    lines = [f"### {fee_name} on Groww: what it is and when it applies", ""]
    lines += [f"- {b}" for b in bullets]
    lines += ["", "**Official sources**"]
    lines += [f"{i}. [{l['title']}]({l['url']})" for i, l in enumerate(links, 1)]
    lines += ["", f"_Last checked: {checked_h}_"]
    return "\n".join(lines) + "\n"


def generate(fee_issue: dict | None, bank: dict | None = None, use_llm: bool | None = None) -> dict:
    bank = bank or load_bank()
    if not fee_issue:
        return {"status": "no_fee_issue", "markdown": "", "message": "No fee or charge was found in the reviews."}
    fee = fee_issue["fee"]
    if fee not in bank["fees"]:
        return {"status": "needs_sources", "fee": fee, "markdown": "",
                "message": (f"Reviews point to '{fee_issue['label']}', but data/fee_facts.json has no verified "
                            "facts for it yet. Add 2 official sources and their facts, then re-run.")}
    facts, links = usable_facts(bank, fee)
    name = bank["fees"][fee]["name"]
    use_llm = llm_available() if use_llm is None else use_llm

    bullets, source, problems, attempts = None, "template", [], 0
    if use_llm:
        fact_list = "\n".join(f"{i}. {f['text']}" for i, f in enumerate(facts, 1))
        prompt = (f"FEE: {name}\nWHAT USERS MISUNDERSTAND (from reviews): "
                  f"{fee_issue.get('typical_misunderstanding') or fee_issue.get('confusion')}\n\nFACTS:\n{fact_list}")
        for attempts in (1, 2):
            p = prompt if attempts == 1 else prompt + "\n\nFix these problems: " + "; ".join(problems)
            try:
                out = parse_json(call_llm(EXPLAINER_SYSTEM, p, json_mode=True, max_tokens=700))
                cand = out.get("bullets", [])
                problems = validate(cand, facts)
                if not problems:
                    bullets, source = [b["text"].strip() for b in cand], "llm"
                    break
            except Exception as e:
                problems = [f"bad model output: {type(e).__name__}"]
    if bullets is None:
        bullets = [f["text"] for f in facts[:MAX_BULLETS]]

    md = render(name, bullets, links, bank["last_checked"])
    return {"status": "ok", "fee": fee, "fee_name": name, "bullets": bullets,
            "source_links": [{"title": l["title"], "url": l["url"]} for l in links],
            "last_checked": bank["last_checked"], "markdown": md, "written_by": source,
            "attempts": attempts, "last_problems": problems if source == "template" else []}


def main() -> None:
    ins = json.loads((ROOT / "data" / "insights.json").read_text())
    res = generate(ins.get("fee_issue"))
    (ROOT / "data" / "explainer.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    if res["status"] != "ok":
        print(res["message"])
        return
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    (out / "fee_explainer.md").write_text(res["markdown"], encoding="utf-8")
    print(res["markdown"])
    print(f"[{len(res['bullets'])} bullets, written by {res['written_by']}] saved outputs/fee_explainer.md")


if __name__ == "__main__":
    main()
