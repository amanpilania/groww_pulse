"""Groww Review Pulse - Streamlit UI.   Run: streamlit run streamlit_app.py

1. Load reviews (data/reviews.csv or upload a CSV)
2. Analyse -> themes, top 3, quotes, fee issue
3. Outputs  -> weekly pulse + fee explainer
4. APPROVAL -> see the exact doc entry and email draft, then Approve or Reject.
   Only after Approve does the app call the MCP tools.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

try:  # Streamlit Cloud secrets -> env
    for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "BACKEND", "GOOGLE_DOC_ID"):
        if k in st.secrets and k not in os.environ:
            os.environ[k] = str(st.secrets[k])
except Exception:
    pass

from mcp_server.backends import backend_name, format_doc_entry  # noqa: E402
from pulse import explainer, weekly  # noqa: E402
from pulse.analyze import REQUIRED, run_analysis  # noqa: E402
from pulse.llm import llm_available  # noqa: E402
from pulse.workflow import build_actions, execute  # noqa: E402

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Groww review pulse", page_icon="📈", layout="wide")
ss = st.session_state

st.title("Groww review pulse")
st.caption("Public app reviews → themes and fee confusion → weekly pulse + support explainer → "
           "approval → notes doc + email draft (never sent).")
c1, c2 = st.columns(2)
c1.markdown(f"**AI:** {'Gemini' if llm_available() else 'off (keyword themes and templates)'}")
c2.markdown(f"**MCP backend:** {'Google Docs + Gmail draft' if backend_name() == 'google' else 'local notes doc + .eml draft'}")

# ---------- 1. reviews ----------
st.header("1. Reviews")
up = st.file_uploader("Upload a reviews CSV, or leave empty to use data/reviews.csv", type="csv")
df = None
if up is not None:
    df = pd.read_csv(up, dtype={"review_id": str})
elif (ROOT / "data" / "reviews.csv").exists():
    df = pd.read_csv(ROOT / "data" / "reviews.csv", dtype={"review_id": str})
if df is None:
    st.info("No reviews yet. Run `python scripts/collect_reviews.py` or upload a CSV.")
    st.stop()
missing = REQUIRED - set(df.columns)
if missing:
    st.error(f"CSV is missing columns: {sorted(missing)}")
    st.stop()
st.write(f"{len(df)} reviews, {df['date'].min()} to {df['date'].max()}")
st.dataframe(df.head(8), width="stretch", hide_index=True)

if st.button("Analyse reviews", type="primary"):
    with st.spinner("Clustering themes and checking fees…"):
        ins, _ = run_analysis(df)
        ss.ins, ss.pulse = ins, weekly.generate(ins)
        ss.exp = explainer.generate(ins.get("fee_issue"))
        ss.pop("result", None)

if "ins" not in ss:
    st.stop()
ins, pulse, exp = ss.ins, ss.pulse, ss.exp

# ---------- 2. insights ----------
st.header("2. Review intelligence")
st.dataframe(pd.DataFrame(ins["themes"])[["theme", "reviews", "share_pct", "avg_rating", "trend"]],
             width="stretch", hide_index=True)
st.markdown("**Top 3 themes:** " + ", ".join(ins["top_themes"]))
for q in ins["quotes"]:
    st.markdown(f"> “{q['quote']}”  \n> {q['rating']}★ review, {q['source'].replace('_', ' ')}, {q['date']} · *{q['theme']}*")
f = ins.get("fee_issue")
if f:
    st.warning(f"**Fee confusion: {f['label']}**. {f['mentions']} reviews mention it, "
               f"{f['confused_mentions']} with confusion cues.  \n{f['confusion']}")
    with st.expander("How the fee was chosen (all fee mentions)"):
        st.dataframe(pd.DataFrame(ins["fee_signals"]), hide_index=True, width="stretch")

# ---------- 3. outputs ----------
st.header("3. Outputs")
a, b = st.columns(2)
with a:
    st.subheader("Weekly product pulse")
    st.caption(f"{pulse['words']} words · written by {pulse['source']}")
    st.markdown(pulse["markdown"])
    st.download_button("Download pulse (.md)", pulse["markdown"], "weekly_pulse.md")
with b:
    st.subheader("Fee explainer")
    if exp["status"] == "ok":
        st.caption(f"{len(exp['bullets'])} bullets · written by {exp['written_by']}")
        st.markdown(exp["markdown"])
        st.download_button("Download explainer (.md)", exp["markdown"], "fee_explainer.md")
    else:
        st.error(exp["message"])
        st.stop()

# ---------- 4. approval ----------
st.header("4. Approval before any action")
to = st.text_input("Draft recipient (optional, the email is never sent)", "")
actions = build_actions(ins, pulse, exp, to)
st.markdown("Nothing has been written yet. These are the **exact** tool calls that will run after approval:")
d, e = st.columns(2)
with d:
    st.markdown("**MCP tool 1: `append_to_doc`**")
    st.code(format_doc_entry(actions[0]["args"]["entry"])[:4000], language="text")
with e:
    st.markdown("**MCP tool 2: `create_email_draft`** (draft only)")
    st.code(f"Subject: {actions[1]['args']['subject']}\nTo: {to or '(blank)'}\n\n{actions[1]['args']['body']}"[:4000],
            language="text")

if "result" not in ss:
    ok = st.checkbox("I have reviewed both actions")
    x, y = st.columns(2)
    if x.button("✅ Approve and run", disabled=not ok, type="primary", width="stretch"):
        with st.spinner("Calling MCP tools…"):
            ss.result = execute(actions, approved=True, reviewer="streamlit-user")
        st.rerun()
    if y.button("❌ Reject", width="stretch"):
        ss.result = execute(actions, approved=False, reviewer="streamlit-user")
        st.rerun()
else:
    r = ss.result
    if r["decision"] == "rejected":
        st.info(f"Rejected. Nothing was written. (Logged as {r['approval_id']})")
    else:
        st.success(f"Approved as {r['approval_id']}. MCP results:")
        for res in r["results"]:
            st.json(res)
        for name in ("notes_doc.md", "email_draft.eml"):
            p = ROOT / "outputs" / name
            if p.exists():
                st.download_button(f"Download {name}", p.read_bytes(), name)
    if st.button("Start a new approval"):
        ss.pop("result")
        st.rerun()
