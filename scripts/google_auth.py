"""One-time Google sign-in for the MCP server (Docs append + Gmail drafts).

1. Put your OAuth client file at ./credentials.json (Desktop app type).
2. Run: python scripts/google_auth.py   -> a browser opens, sign in, allow.
3. token.json is saved next to credentials.json. Both are git-ignored.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mcp_server.backends import _google_creds  # noqa: E402

_google_creds()
print("Signed in. token.json saved. Set GOOGLE_DOC_ID and run: python -m pulse.workflow")
