"""Where the MCP tools actually write.

BACKEND=google  -> Google Docs (append) + Gmail (create draft, never send)
BACKEND=local   -> outputs/notes_doc.md (append) + outputs/email_draft.eml
Default: google if credentials.json exists, otherwise local.

Google setup (one time): see README "Google setup". Scopes are minimal:
documents (edit the one doc) and gmail.compose (create drafts). There is no
send scope and no send tool.
"""
import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"


def _out() -> Path:
    return Path(os.environ.get("OUTPUT_DIR", OUT))
SCOPES = ["https://www.googleapis.com/auth/documents",
          "https://www.googleapis.com/auth/gmail.compose"]


def backend_name() -> str:
    b = os.getenv("BACKEND")
    if b in ("google", "local"):
        return b
    return "google" if (ROOT / "credentials.json").exists() else "local"


# ---------- formatting shared by both backends ----------

def format_doc_entry(entry: dict) -> str:
    lines = [
        f"===== Weekly entry: {entry['date']} =====",
        f"Top themes: {', '.join(entry['top_themes'])}",
        "",
        "Weekly pulse:",
        entry["weekly_pulse"].strip(),
        "",
        f"Identified fee issue: {entry['identified_fee_issue']}",
        "",
        "Explanation bullets:",
        *[f"- {b}" for b in entry["explanation_bullets"]],
        "",
        "Source links:",
        *[f"- {s}" for s in entry["source_links"]],
        "",
        "Raw entry (JSON):",
        json.dumps(entry, ensure_ascii=False),
        "",
        "",
    ]
    return "\n".join(lines)


# ---------- Google ----------

def _google_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = ROOT / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / "credentials.json"), SCOPES)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json())
    return creds


def google_append(entry: dict) -> dict:
    from googleapiclient.discovery import build

    doc_id = os.environ.get("GOOGLE_DOC_ID")
    if not doc_id:
        raise RuntimeError("Set GOOGLE_DOC_ID to the id of the Google Doc to append to.")
    docs = build("docs", "v1", credentials=_google_creds(), cache_discovery=False)
    doc = docs.documents().get(documentId=doc_id).execute()
    end = doc["body"]["content"][-1]["endIndex"] - 1
    text = format_doc_entry(entry)
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": [
        {"insertText": {"location": {"index": end}, "text": text}}]}).execute()
    return {"backend": "google_docs", "doc_url": f"https://docs.google.com/document/d/{doc_id}/edit",
            "chars_appended": len(text)}


def google_draft(subject: str, body: str, to: str | None) -> dict:
    from googleapiclient.discovery import build

    msg = EmailMessage()
    msg["Subject"] = subject
    if to:
        msg["To"] = to
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail = build("gmail", "v1", credentials=_google_creds(), cache_discovery=False)
    d = gmail.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"backend": "gmail", "draft_id": d["id"], "status": "draft (not sent)",
            "open_url": "https://mail.google.com/mail/u/0/#drafts"}


# ---------- Local fallback ----------

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def local_append(entry: dict) -> dict:
    out = _out()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "notes_doc.md"
    if not path.exists():
        path.write_text("# Groww Product Pulse: running notes\n\n", encoding="utf-8")
    text = format_doc_entry(entry)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)
    return {"backend": "local_doc", "path": _rel(path), "chars_appended": len(text)}


def local_draft(subject: str, body: str, to: str | None) -> dict:
    out = _out()
    out.mkdir(parents=True, exist_ok=True)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to or ""
    msg["X-Unsent"] = "1"  # opens as an editable draft in Outlook / Apple Mail
    msg.set_content(body)
    path = out / "email_draft.eml"
    path.write_bytes(msg.as_bytes())
    (out / "email_draft.txt").write_text(f"Subject: {subject}\n\n{body}", encoding="utf-8")
    return {"backend": "local_eml", "path": _rel(path), "status": "draft (not sent)"}


def append(entry: dict) -> dict:
    return google_append(entry) if backend_name() == "google" else local_append(entry)


def draft(subject: str, body: str, to: str | None) -> dict:
    return google_draft(subject, body, to) if backend_name() == "google" else local_draft(subject, body, to)
