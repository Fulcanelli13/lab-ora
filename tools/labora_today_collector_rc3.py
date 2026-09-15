#!/usr/bin/env python3
"""Lab-ora Today collector RC3 compatibility/hardening layer.

Keeps the source adapters and editorial policy in RC2, while correcting two
publisher-markup edge cases observed in the first live scheduled run:
- Opus Dei page chrome can be repeated at the start of the extracted h1.
- French Vatican News can expose slash dates in either DD/MM/YYYY or MM/DD/YYYY.
"""
from __future__ import annotations

import datetime as dt
import re

import labora_today_collector_rc2 as base


def parse_slash_date(text: str):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
    if not m:
        return None
    a, b, year = map(int, m.groups())
    if a > 12 and b <= 12:      # DD/MM/YYYY
        day, month = a, b
    elif b > 12 and a <= 12:    # MM/DD/YYYY
        month, day = a, b
    else:                       # ambiguous on French-language sources: prefer DD/MM
        day, month = a, b
    try:
        return base.date_to_iso(year, month, day)
    except ValueError:
        return None


base.parse_slash_date = parse_slash_date
_original_meditation = base.fetch_opus_dei_meditation


def fetch_opus_dei_meditation(language: str, date: dt.date) -> dict:
    item = _original_meditation(language, date)
    title = base.clean_text(item.get("title", ""))
    title = re.sub(r"^(?:Opus\s*Dei\s*)+", "", title, flags=re.I).strip(" ·:-")
    if title:
        item["title"] = title
    return item


base.fetch_opus_dei_meditation = fetch_opus_dei_meditation

if __name__ == "__main__":
    raise SystemExit(base.main())
