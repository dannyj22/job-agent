"""Shared helpers: text cleaning, URL normalisation, date parsing."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Query params commonly used for tracking. Dropping them lets us dedupe the
# same job even when it is linked with different tracking tokens.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "refid", "refid", "trackingid", "trk", "tracking", "position",
    "pagenum", "gh_src", "source", "src", "fbclid", "gclid", "mc_cid",
    "mc_eid", "igshid", "lever-source", "lever-origin", "candidate_id",
}

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: Any) -> str:
    """Collapse whitespace and decode HTML entities."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def strip_html(value: Any) -> str:
    """Turn an HTML fragment into readable plain text."""
    if not value:
        return ""
    raw = str(value)
    if "<" in raw and ">" in raw:
        try:
            raw = BeautifulSoup(raw, "html.parser").get_text(" ")
        except Exception:  # pragma: no cover - defensive
            raw = _TAG_RE.sub(" ", raw)
    return clean_text(raw)


def truncate(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()


def normalize_url(url: str) -> str:
    """Return a canonical URL with tracking parameters and fragments removed."""
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, urlencode(query), ""))


def parse_date(value: Any) -> datetime | None:
    """Best-effort parser for ISO strings, RSS structs and epoch numbers."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    # feedparser returns time.struct_time
    if hasattr(value, "tm_year"):
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except Exception:
            return None
    try:
        parsed = date_parser.parse(str(value), fuzzy=True)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def is_remote(location: str, *, remote_flag: bool = False) -> bool:
    if remote_flag:
        return True
    loc = (location or "").lower()
    return any(word in loc for word in ("remote", "anywhere", "worldwide", "distributed"))
