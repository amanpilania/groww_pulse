# Groww Review Pulse (Milestone 2)

An AI workflow that turns public Groww app reviews into:

1. a **weekly internal product pulse** (≤250 words: top themes, 3 real quotes, key observation, 3 action ideas), and
2. a **customer-facing fee explainer** (≤6 neutral bullets, 2 official links, "Last checked") for the fee users misunderstand most,

then, **only after a human approves**, uses **MCP tools** to append the entry to a notes doc and create an email draft (never sent).

Product: **Groww** (same as Milestone 1). Fee examples reuse the ICICI Prudential schemes from Milestone 1 when the fee is exit load.

| Deliverable | Where |
|---|---|
| Working prototype | https://claude.ai/artifact/KpessaMEepa8vM8JtM6xjX (hosted, see below) · Streamlit app: _add link if deployed_ |
| GitHub repository | https://github.com/amanpilania/groww_pulse |
| Weekly product pulse | `outputs/weekly_pulse.md` |
| Notes doc snippet (appended entry) | `outputs/notes_doc.md` or your Google Doc (screenshot) |
| Email draft | `outputs/email_draft.txt` / `.eml`, or Gmail Drafts (screenshot) |
| Reviews CSV sample | `outputs/reviews_sample.csv` |
| Source list | `sources.md` |
| Fee issue identified | `outputs/RESULTS.md` (and the section below) |

## Hosted prototype

`web/index.html` is a single-page version of the workflow, published at the prototype link above (also deployable to Netlify: publish directory `web`).
It runs the same steps in the browser: upload `data/reviews.csv` (or load the demo data), keyword themes, top 3, 3 verbatim quotes, fee chosen by counting confused mentions, the ≤250-word pulse and the ≤6-bullet explainer with 2 official links.
Stage 4 is the approval gate: the exact doc entry and email draft are shown, Approve stays disabled until "I have reviewed both actions" is ticked, and Reject writes nothing.
After approval the entry is appended to the page's shared notes log (the artifact's database; on Netlify, the browser) and the email draft is created as copyable text and a `.eml` file. "Improve wording with Claude" optionally rewrites the observation, actions and bullets, and the same checks (word limit, numbers, advice words, fact citations) run before anything is accepted.
The full MCP server version (Google Docs + Gmail drafts) is the Python app in this repo.

## How it works

```
Google Play + App Store reviews (last 12 weeks)
   │  scripts/collect_reviews.py      names dropped, phone/email/PAN/IDs masked
   ▼
Step 1  pulse/analyze.py              ≤5 themes (Gemini) → top 3 by volume → 3 quotes verified word-for-word
                                      fee chosen by COUNTING confused mentions per fee (not by the AI)
Step 2  pulse/weekly.py               ≤250-word pulse; code checks words, 3 actions, no invented numbers
Step 3  pulse/explainer.py            ≤6 bullets from verified official facts (data/fee_facts.json), 2 links, Last checked
   ▼
APPROVAL  streamlit_app.py (section 4) or pulse/workflow.py (terminal)
   │  shows the exact doc entry + email draft → Approve / Reject → logged in data/approvals.jsonl
   ▼
MCP     mcp_server/server.py          append_to_doc · create_email_draft (draft only, no send tool)
                                      server re-checks the approval id + payload hash before acting
```

Without a Gemini key the pipeline still runs: keyword themes and deterministic templates replace the AI parts.

## Where MCP approval happens

- **UI:** `streamlit_app.py`, section **4. Approval before any action**. It shows the exact `append_to_doc` entry and the exact email draft. The Approve button is disabled until "I have reviewed both actions" is ticked. Reject writes nothing.
- **Terminal:** `python -m pulse.workflow` prints the proposed actions and only continues if you type `approve`.
- **Enforced in the MCP server too:** every decision is written to `data/approvals.jsonl` with a SHA-256 hash of the exact arguments. The server refuses a call if the approval id is unknown, was rejected, was already used, or the payload differs from what was approved. So the gate can't be skipped by calling the tools directly.
- The email tool only creates drafts. The Google scope is `gmail.compose` and there is no send tool.

Doc entry fields (as required): `date, top_themes, weekly_pulse, identified_fee_issue, explanation_bullets, source_links`.
Email subject: `Weekly Product Pulse + Customer Clarification — <week ending date>`; body = pulse + fee explainer as a support snippet.

## Fee issue identified from reviews

_Fill in after your run (copy from `outputs/RESULTS.md`):_ **<fee name>**, mentioned in **N** reviews, **M** with confusion cues ("why", "hidden", "without informing", "didn't know"). Users seem to believe: _<typical misunderstanding>_.

Fees the explainer has verified official facts for: DP charges, brokerage, exit load, statutory charges (STT, stamp duty, exchange/SEBI fees, GST), account opening/maintenance. If reviews point elsewhere (e.g. MTF interest), the run stops and asks for 2 official sources to be added to `data/fee_facts.json`.

## How to run (laptop)

Python 3.10+.

```bash
pip install -r requirements.txt

# 1. Collect ~12 weeks of public reviews -> data/reviews.csv
python scripts/collect_reviews.py

# 2. (recommended) AI key - create a NEW key at https://aistudio.google.com
export GEMINI_API_KEY="your-key"          # Windows PowerShell: $env:GEMINI_API_KEY="your-key"

# 3a. Everything in the terminal: analysis -> pulse -> explainer -> approval -> MCP actions
python -m pulse.run

# 3b. Or the UI
streamlit run streamlit_app.py
```

By default the MCP tools write locally (`outputs/notes_doc.md`, `outputs/email_draft.eml`). To use **Google Docs + Gmail drafts**:

1. In Google Cloud Console create a project, enable the **Google Docs API** and **Gmail API**, configure the OAuth consent screen (add yourself as a test user), and create an **OAuth client ID → Desktop app**. Download it as `credentials.json` into this folder.
2. `python scripts/google_auth.py` → sign in once (creates `token.json`).
3. Create an empty Google Doc and copy its id from the URL (`docs.google.com/document/d/<ID>/edit`).
4. `export GOOGLE_DOC_ID="<ID>"` and `export BACKEND=google`, then run step 3a or 3b again.

Use the MCP server from any MCP client (e.g. Claude Desktop) with the command `python -m mcp_server.server` run from this folder.

Tests (offline, AI stubbed): `python -m pytest -q`

## Deploy (prototype link)

Push to GitHub (`credentials.json`, `token.json` and secrets are git-ignored), then on share.streamlit.io create an app with main file `streamlit_app.py` and add `GEMINI_API_KEY` under Secrets. Commit your `data/reviews.csv` so the hosted app has data, or upload a CSV in the app. The hosted app uses the local backend (files offered as downloads), because Google sign-in needs a browser on your own machine; record the Google Docs/Gmail run locally for the demo video.

## Project layout

```
scripts/collect_reviews.py   collect + clean reviews
scripts/google_auth.py       one-time Google sign-in
pulse/clean.py               PII masking, filtering
pulse/fees.py                fee keyword tagging and counting
pulse/themes.py              theme discovery/classification, stats, quote verification
pulse/analyze.py             Step 1 orchestration -> data/insights.json
pulse/weekly.py              Step 2 pulse
pulse/explainer.py           Step 3 fee explainer
pulse/workflow.py            approval + MCP client
pulse/run.py                 run everything
mcp_server/server.py         MCP tools
mcp_server/approvals.py      approval ledger and enforcement
mcp_server/backends.py       Google Docs/Gmail or local files
data/fee_facts.json          verified fee facts and official links
streamlit_app.py             UI
tests/                       26 offline tests with a small sample fixture
```

## Known limits

- Reviews are English-script only; very short reviews (<4 words) are dropped.
- Themes come from an LLM, so wording can change between runs; counts, quotes and the fee choice are deterministic and checked.
- The fee explainer only states facts stored in `data/fee_facts.json`; charges change, so re-check the sources each week and update `last_checked`.
- DP-charge facts come from Groww's own pages; no SEBI/CDSL investor page explaining DP charges was found.
- `tests/fixtures/sample_reviews.csv` is a small test fixture, not collected reviews; deliverables come from `data/reviews.csv`.
