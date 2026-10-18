"""The only place the project calls an LLM. Default: Google Gemini (free tier).

Set GEMINI_API_KEY (env var or Streamlit secret). Optional GEMINI_MODEL.
Swap providers by editing call_llm() only.
"""
import json
import os
import re

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def llm_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def call_llm(system: str, user: str, json_mode: bool = False, max_tokens: int = 800) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else "text/plain",
        ),
    )
    return (resp.text or "").strip()


def parse_json(text: str):
    clean = re.sub(r"```(?:json)?", "", text).strip()
    return json.loads(clean)
