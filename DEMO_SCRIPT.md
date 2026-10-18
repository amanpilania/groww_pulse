# Demo video script (≤3 minutes)

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Terminal: `python scripts/collect_reviews.py` output | "Public Groww reviews from Play Store and App Store, last 12 weeks. Names dropped, phone numbers and IDs masked." |
| 0:20–0:50 | App: section 1, click **Analyse reviews**; section 2 themes table | "Gemini groups reviews into at most 5 themes; code ranks the top 3 and picks 3 quotes copied word-for-word." |
| 0:50–1:10 | Fee warning + "How the fee was chosen" table | "The fee is chosen by counting confused mentions per fee, so the explainer answers what users actually struggle with." |
| 1:10–1:40 | Section 3: pulse and explainer | "The pulse is under 250 words with 3 action ideas; the explainer has at most 6 bullets, 2 official links and a last-checked date." |
| 1:40–2:10 | Section 4: exact doc entry + email draft; Approve disabled until ticked | "Nothing is written until a person approves these exact tool calls." |
| 2:10–2:40 | Tick, Approve; MCP results; open Google Doc and Gmail Drafts | "After approval the MCP server appends the entry to the doc and creates a draft. It can't send." |
| 2:40–2:55 | `data/approvals.jsonl` | "Every decision is logged, and the server refuses calls whose payload differs from what was approved." |
