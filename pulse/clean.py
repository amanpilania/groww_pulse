"""Cleaning and PII masking for review text. Pure functions, no network."""
import re

import pandas as pd

MASKS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I), "[pan]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[id-number]"),
    (re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"), "[phone]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card-number]"),
    (re.compile(r"\b(?:client\s*id|ucc|folio|account|a/c|acct|demat)\b(?:\s*(?:no|number|#))?\W{0,5}[A-Z0-9]{6,}", re.I),
     "[account]"),
    (re.compile(r"\b(?:order|ticket|complaint|ref(?:erence)?)\s*(?:id|no|number|#)\W{0,5}[A-Z0-9-]{6,}", re.I),
     "[reference]"),
]


def mask_pii(text: str) -> str:
    for pat, repl in MASKS:
        text = pat.sub(repl, text)
    return text


def _mostly_latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) >= 0.8


def clean_reviews(df: pd.DataFrame, min_words: int = 4) -> pd.DataFrame:
    """Normalise whitespace, mask PII, drop empty/very short/non-Latin/duplicate reviews."""
    df = df.copy()
    df["review_text"] = (df["review_text"].fillna("").astype(str)
                         .str.replace(r"\s+", " ", regex=True).str.strip()
                         .map(mask_pii))
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df[df["review_text"].str.split().str.len() >= min_words]
    df = df[df["review_text"].map(_mostly_latin)]
    df = df[df["rating"].between(1, 5)]
    df = df.drop_duplicates(subset=["review_text"])
    return df.sort_values("date", ascending=False).reset_index(drop=True)
