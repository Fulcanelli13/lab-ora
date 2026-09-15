#!/usr/bin/env python3
"""Lab-ora Today feed collector (v1.1 prototype).

Small scheduled JSON generator / server-side collector.
- Retrieves metadata only (title, URL, time, source, lane, language).
- EN and FR are independent editorial feeds; cross-language fallback is forbidden.
- 0–4 days is the normal window; 4–7 days remains eligible with a ranking penalty; 7 days is the hard expiry.
- Keeps source adapters isolated.
- Does not download article images or expose article bodies to Lab-ora.

Usage:
    python labora_today_collector.py --language en --output labora-today-en.json
    python labora_today_collector.py --language fr --output labora-today-fr.json

Designed for a scheduled job or serverless wrapper. Standard library only.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import difflib
import email.utils
import html
from html.parser import HTMLParser
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

UA = "Lab-ora-Today/1.1 (+metadata-only Catholic feed collector)"
TIMEOUT = 14
TARGET_TOTAL = 14
HARD_MAX = 15
NORMAL_WINDOW_HOURS = 96
HARD_EXPIRY_HOURS = 168

# Feed policy: language is exclusive. There is no cross-language fallback.
SOURCE_PRIORITY = {
    "Holy See Press Office": 24,
    "Vatican News": 22,
    "Ad Vaticanum": 21,
    "New Liturgical Movement": 21,
    "Paix Liturgique": 22,
    "Riposte Catholique": 20,
}
LANE_PRIORITY = {"official": 5, "vatican": 4, "tradition": 3, "outside_walls": 2}

LANE_ORDER = ("vatican", "outside_walls", "official", "tradition")
ALLOWED_LANES = set(LANE_ORDER)

@dataclasses.dataclass
class Item:
    source: str
    lane: str
    language: str
    title: str
    publishedAt: Optional[str]
    url: str

    def as_dict(self):
        return dataclasses.asdict(self)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_bytes(url: str, *, timeout: int = TIMEOUT) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/atom+xml,application/rss+xml;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        ctype = r.headers.get_content_type() or ""
        charset = r.headers.get_content_charset() or ""
        return body, ctype, charset


def decode_html(body: bytes, charset: str = "") -> str:
    candidates = [charset, "utf-8", "windows-1252", "iso-8859-1"]
    for enc in candidates:
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return body.decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return clean_text(html.unescape(value))


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_url(url: str, base: Optional[str] = None) -> Optional[str]:
    if not url:
        return None
    url = urllib.parse.urljoin(base or "", url.strip())
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if p.scheme.lower() not in {"http", "https"} or not p.netloc:
        return None
    # Strip fragments and common tracking params while preserving publisher URLs.
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    path = re.sub(r"/{2,}", "/", p.path or "/")
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urllib.parse.urlencode(q), ""))


def normalize_title(value: str) -> str:
    s = clean_text(value).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s']+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def parse_iso(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    v = value.strip()
    try:
        if v.endswith("Z"):
            return dt.datetime.fromisoformat(v[:-1] + "+00:00")
        out = dt.datetime.fromisoformat(v)
        if out.tzinfo is None:
            out = out.replace(tzinfo=dt.timezone.utc)
        return out.astimezone(dt.timezone.utc)
    except ValueError:
        try:
            out = email.utils.parsedate_to_datetime(v)
            if out.tzinfo is None:
                out = out.replace(tzinfo=dt.timezone.utc)
            return out.astimezone(dt.timezone.utc)
        except Exception:
            return None


def date_to_iso(year: int, month: int, day: int, hour: int = 12) -> str:
    return dt.datetime(year, month, day, hour, tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")


MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}


def parse_english_date(text: str, default_year: Optional[int] = None) -> Optional[str]:
    m = re.search(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2}),\s*(\d{4})\b", text, re.I)
    if not m:
        return None
    month = MONTHS.get(m.group(1)[:3].lower())
    return date_to_iso(int(m.group(3)), month, int(m.group(2))) if month else None


def parse_french_date(text: str) -> Optional[str]:
    months = {"janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12,"decembre":12}
    m = re.search(r"\b(\d{1,2})\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})\b", text, re.I)
    if not m:
        return None
    key = m.group(2).lower()
    key = key.replace("û", "u")
    return date_to_iso(int(m.group(3)), months.get(key, months.get(m.group(2).lower())), int(m.group(1)))


def parse_slash_date(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
    if not m:
        return None
    return date_to_iso(int(m.group(3)), int(m.group(2)), int(m.group(1)))


class BasicMetaParser(HTMLParser):
    """Extract h1/title/time/meta description without retaining article body."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_h1 = self.in_title = self.in_time = False
        self.h1_parts, self.title_parts, self.time_parts = [], [], []
        self.description = ""
        self.og_title = ""
        self.canonical = ""
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1": self.in_h1 = True
        elif tag == "title": self.in_title = True
        elif tag == "time": self.in_time = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {"description", "og:description"} and not self.description:
                self.description = a.get("content", "")
            if key == "og:title" and not self.og_title:
                self.og_title = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href", "")
    def handle_endtag(self, tag):
        if tag == "h1": self.in_h1 = False
        elif tag == "title": self.in_title = False
        elif tag == "time": self.in_time = False
    def handle_data(self, data):
        if self.in_h1: self.h1_parts.append(data)
        if self.in_title: self.title_parts.append(data)
        if self.in_time: self.time_parts.append(data)


def fetch_opus_dei_meditation(language: str, date: dt.date) -> dict:
    # STRICT LANGUAGE: one locale only. An unavailable meditation stays unavailable;
    # it is never replaced by a meditation in the other language.
    # Opus Dei exposes the two languages differently. French has a dated route;
    # English exposes an official /en/meditation/ daily alias whose canonical URL
    # resolves to the meditation currently featured. Stay within the selected
    # language in either case; never fall through to the opposite-language site.
    if language == "fr":
        url = f"https://opusdei.org/fr-fr/meditation/{date.isoformat()}/"
    else:
        url = "https://opusdei.org/en/meditation/"
    body, _, charset = fetch_bytes(url)
    text = decode_html(body, charset)
    parser = BasicMetaParser(); parser.feed(text)
    title = clean_text("".join(parser.h1_parts) or parser.og_title or "".join(parser.title_parts))
    if not title or "404" in title.lower():
        raise ValueError("meditation title not found")
    canonical = safe_url(parser.canonical, url) or url
    subtitle = clean_text(parser.description)
    if len(subtitle) > 260:
        subtitle = ""
    return {
        "source": "Opus Dei", "lane": "meditation", "language": language,
        "title": title, "date": date.isoformat(), "url": canonical,
        **({"subtitle": subtitle} if subtitle else {})
    }


def fetch_advaticanum(lane: str, max_items: int = 4) -> list[Item]:
    assert lane in {"vatican", "outside_walls"}
    slug = "vatican" if lane == "vatican" else "outside"
    listing = f"https://advaticanum.com/category/{slug}/page/1/"
    body, _, charset = fetch_bytes(listing)
    text = decode_html(body, charset)
    out, seen = [], set()
    # Category HTML is stable enough to expose canonical /article/ anchors. We only keep anchor text + nearby date.
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*/article/[^"\']+)["\'][^>]*>(.*?)</a>', text):
        url = safe_url(m.group(1), listing)
        anchor_html = m.group(2)
        # Category cards may wrap both heading and excerpt in one anchor. Prefer a heading child,
        # then text before the first paragraph; never send the excerpt to the client.
        hm = re.search(r"(?is)<h[1-6]\b[^>]*>(.*?)</h[1-6]>", anchor_html)
        if hm:
            title = strip_tags(hm.group(1))
        else:
            before_p = re.split(r"(?is)<p\b", anchor_html, maxsplit=1)[0]
            title = strip_tags(before_p)
            if not title:
                title = strip_tags(anchor_html)
        if not url or not title or url in seen or len(title) < 12:
            continue
        title = clean_text(title)
        if len(title) > 220:
            continue
        nearby = strip_tags(text[m.end():m.end()+1800])
        published = parse_english_date(nearby)
        out.append(Item("Ad Vaticanum", lane, "en", title, published, url))
        seen.add(url)
        if len(out) >= max_items:
            break
    if not out:
        raise RuntimeError("no article anchors parsed")
    return out


def fetch_nlm(max_items: int = 5) -> list[Item]:
    url = "https://www.newliturgicalmovement.org/feeds/posts/default"
    body, _, _ = fetch_bytes(url)
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("a:entry", ns):
        title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
        published = clean_text(entry.findtext("a:published", default="", namespaces=ns) or entry.findtext("a:updated", default="", namespaces=ns))
        href = ""
        for link in entry.findall("a:link", ns):
            if link.attrib.get("rel") in {None, "alternate"} and link.attrib.get("href"):
                href = link.attrib["href"]; break
        href = safe_url(href)
        if title and href:
            d = parse_iso(published)
            out.append(Item("New Liturgical Movement", "tradition", "en", title, d.isoformat().replace("+00:00", "Z") if d else None, href))
        if len(out) >= max_items:
            break
    if not out:
        raise RuntimeError("Atom feed returned no entries")
    return out


def fetch_paix(max_items: int = 3) -> list[Item]:
    homepage = "https://www.paixliturgique.fr/"
    body, _, charset = fetch_bytes(homepage)
    # Site currently emits legacy Western bytes; decode cp1252 first so curly apostrophes/accents survive
    # even if an imprecise ISO-8859-1 header is supplied.
    try:
        text = body.decode("windows-1252")
    except UnicodeDecodeError:
        text = decode_html(body, charset)
    out, seen = [], set()
    page_date = parse_french_date(strip_tags(text))
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*aff_lettre\.asp\?LET_N_ID=\d+[^"\']*)["\'][^>]*>(.*?)</a>', text):
        title = strip_tags(m.group(2))
        url = safe_url(m.group(1), homepage)
        if not url or not title or url in seen or len(title) < 8:
            continue
        out.append(Item("Paix Liturgique", "tradition", "fr", title, page_date, url))
        seen.add(url)
        if len(out) >= max_items:
            break
    if not out:
        raise RuntimeError("no letter headline parsed")
    return out


def fetch_vatican_news_fr(section: str, lane: str, max_items: int = 5) -> list[Item]:
    """French Vatican News metadata adapter. section is 'pape' or 'vatican'."""
    if section not in {"pape", "vatican"}:
        raise ValueError("unsupported Vatican News section")
    if lane not in {"vatican", "official"}:
        raise ValueError("unsupported lane")
    listing = f"https://www.vaticannews.va/fr/{section}.html"
    body, _, charset = fetch_bytes(listing)
    text = decode_html(body, charset)
    out, seen = [], set()
    # Article URLs consistently contain /fr/.../news/YYYY-MM/...html.
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*/fr/[^"\']*/news/\d{4}-\d{2}/[^"\']+\.html[^"\']*)["\'][^>]*>(.*?)</a>', text):
        url = safe_url(m.group(1), listing)
        title = strip_tags(m.group(2))
        if not url or not title or url in seen or len(title) < 12 or len(title) > 260:
            continue
        around = strip_tags(text[max(0, m.start()-500):m.end()+500])
        published = parse_slash_date(around) or parse_french_date(around)
        out.append(Item("Vatican News", lane, "fr", clean_text(title), published, url))
        seen.add(url)
        if len(out) >= max_items:
            break
    if not out:
        raise RuntimeError(f"no French Vatican News items parsed from {section}")
    return out


def fetch_riposte(max_items: int = 5) -> list[Item]:
    homepage = "https://riposte-catholique.fr/"
    body, _, charset = fetch_bytes(homepage)
    text = decode_html(body, charset)
    out, seen = [], set()
    # Current site article permalinks use /archives/<id>. Prefer heading anchors.
    for hm in re.finditer(r'(?is)<h[2-6]\b[^>]*>\s*<a\b[^>]*href=["\']([^"\']*/archives/\d+[^"\']*)["\'][^>]*>(.*?)</a>\s*</h[2-6]>', text):
        url = safe_url(hm.group(1), homepage)
        title = strip_tags(hm.group(2))
        if not url or not title or url in seen or len(title) < 12 or len(title) > 260:
            continue
        around = strip_tags(text[max(0, hm.start()-500):hm.end()+700])
        published = parse_french_date(around) or parse_slash_date(around)
        out.append(Item("Riposte Catholique", "outside_walls", "fr", clean_text(title), published, url))
        seen.add(url)
        if len(out) >= max_items:
            break
    if not out:
        # Fallback for markup where the heading wraps the link differently.
        for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*/archives/\d+[^"\']*)["\'][^>]*>(.*?)</a>', text):
            url = safe_url(m.group(1), homepage); title = strip_tags(m.group(2))
            if not url or not title or url in seen or len(title) < 12 or len(title) > 220:
                continue
            around = strip_tags(text[max(0, m.start()-400):m.end()+500])
            out.append(Item("Riposte Catholique", "outside_walls", "fr", clean_text(title), parse_french_date(around) or parse_slash_date(around), url))
            seen.add(url)
            if len(out) >= max_items: break
    if not out:
        raise RuntimeError("no Riposte Catholique headlines parsed")
    return out


def holy_see_score(title: str) -> int:
    t = title.lower()
    score = 0
    for key, val in [("resignations and appointments", 10), ("appointment", 8), ("audience of the holy father", 8),
                     ("communiqué", 8), ("communique", 8), ("decree", 8), ("journey", 7), ("audiences", 4)]:
        if key in t: score += val
    if "notice of press conference" in t: score -= 7
    elif "press conference" in t: score -= 3
    return score


def fetch_holy_see(date: dt.date, max_items: int = 4) -> list[Item]:
    candidates: list[Item] = []
    for delta in range(0, 4):
        day = date - dt.timedelta(days=delta)
        url = f"https://press.vatican.va/content/salastampa/en/bollettino/pubblico/{day:%Y/%m/%d}.html"
        try:
            body, _, charset = fetch_bytes(url)
        except urllib.error.HTTPError as e:
            if e.code == 404: continue
            raise
        text = decode_html(body, charset)
        for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*?/bollettino/pubblico/\d{4}/\d{2}/\d{2}/[^"\']+)["\'][^>]*>(.*?)</a>', text):
            title = strip_tags(m.group(2))
            href = safe_url(m.group(1), url)
            if not title or not href or title.upper() in {"IT", "EN", "ES"}: continue
            candidates.append(Item("Holy See Press Office", "official", "en", title, date_to_iso(day.year, day.month, day.day), href))
        if len(candidates) >= max_items * 2:
            break
    # Useful items first; then date. Deduplicate URLs.
    unique = {}
    for x in candidates: unique[x.url] = x
    out = list(unique.values())
    out.sort(key=lambda x: (holy_see_score(x.title), parse_iso(x.publishedAt) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    out = out[:max_items]
    if not out:
        raise RuntimeError("no bulletin items parsed")
    return out


def age_hours(item: Item, now: dt.datetime) -> Optional[float]:
    d = parse_iso(item.publishedAt)
    if not d:
        return None
    return max(0.0, (now - d).total_seconds() / 3600.0)


def eligible(item: Item, now: dt.datetime) -> bool:
    d = parse_iso(item.publishedAt)
    if not d:
        return True  # Latest-list items can survive parser date gaps, but score lower.
    return now - dt.timedelta(hours=HARD_EXPIRY_HOURS) <= d <= now + dt.timedelta(hours=24)


def editorial_score(item: Item, now: dt.datetime) -> float:
    age = age_hours(item, now)
    if age is None:
        freshness = 25
    elif age <= 48:
        freshness = 100 - age * 0.35
    elif age <= NORMAL_WINDOW_HOURS:
        freshness = 78 - (age - 48) * 0.25
    else:
        # 4–7 day material remains eligible, but naturally sinks unless a lane is sparse.
        freshness = 52 - (age - NORMAL_WINDOW_HOURS) * 0.18
    return freshness + SOURCE_PRIORITY.get(item.source, 10) + LANE_PRIORITY.get(item.lane, 0)


def dedupe(items: Iterable[Item]) -> tuple[list[Item], int, int]:
    kept: list[Item] = []
    urls = set(); dupes = malformed = 0
    for item in items:
        item.title = clean_text(item.title)
        item.url = safe_url(item.url) or ""
        if item.lane not in ALLOWED_LANES or item.language not in {"en", "fr"} or not item.title or not item.url or len(item.title) > 300:
            malformed += 1; continue
        if item.url in urls:
            dupes += 1; continue
        nt = normalize_title(item.title)
        if any(difflib.SequenceMatcher(None, nt, normalize_title(k.title)).ratio() >= 0.94 for k in kept):
            dupes += 1; continue
        urls.add(item.url); kept.append(item)
    return kept, dupes, malformed


def choose_diverse(items: list[Item], language: str, now: dt.datetime, limit: int = TARGET_TOTAL) -> list[Item]:
    # Defensive language gate even though collect() already runs language-specific adapters.
    items = [x for x in items if x.language == language]
    pools = {lane: [] for lane in LANE_ORDER}
    for x in items:
        pools[x.lane].append(x)
    for lane, pool in pools.items():
        pool.sort(key=lambda x: (editorial_score(x, now), parse_iso(x.publishedAt) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
        pools[lane] = pool[:5]

    # First establish a balanced 3-per-lane editorial core.
    out: list[Item] = []
    for _round in range(3):
        for lane in LANE_ORDER:
            if pools[lane] and len(out) < min(limit, HARD_MAX):
                out.append(pools[lane].pop(0))

    # Then use up to two flexible slots for the strongest remaining material.
    while len(out) < min(limit, HARD_MAX):
        candidates = [(editorial_score(pool[0], now), lane, pool[0]) for lane, pool in pools.items() if pool]
        if not candidates:
            break
        _, lane, item = max(candidates, key=lambda row: row[0])
        out.append(item); pools[lane].pop(0)
    return out


def collect(language: str = "en", date: Optional[dt.date] = None) -> dict:
    language = "fr" if language == "fr" else "en"
    date = date or dt.datetime.now(dt.timezone.utc).date()
    started = iso_now()
    diagnostics = {
        "language": language, "lastFetched": started, "lastSucceeded": None, "adapters": {},
        "itemCounts": {}, "discardedMalformed": 0, "duplicatesRemoved": 0,
        "policy": {"target": TARGET_TOTAL, "hardMax": HARD_MAX, "normalWindowHours": NORMAL_WINDOW_HOURS, "hardExpiryHours": HARD_EXPIRY_HOURS, "strictLanguage": True}
    }

    meditation = None
    try:
        meditation = fetch_opus_dei_meditation(language, date)
        diagnostics["adapters"]["opus_dei"] = {"ok": True, "count": 1}
    except Exception as e:
        diagnostics["adapters"]["opus_dei"] = {"ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"}

    # Separate editorial pipelines. No opposite-language source is even invoked.
    if language == "en":
        adapters = [
            ("ad_vaticanum_vatican", lambda: fetch_advaticanum("vatican", 5)),
            ("ad_vaticanum_outside", lambda: fetch_advaticanum("outside_walls", 5)),
            ("nlm_atom", lambda: fetch_nlm(5)),
            ("holy_see_en", lambda: fetch_holy_see(date, 5)),
        ]
    else:
        adapters = [
            ("vatican_news_pape_fr", lambda: fetch_vatican_news_fr("pape", "vatican", 5)),
            ("vatican_news_saint_siege_fr", lambda: fetch_vatican_news_fr("vatican", "official", 5)),
            ("riposte_catholique_fr", lambda: fetch_riposte(5)),
            ("paix_liturgique_fr", lambda: fetch_paix(5)),
        ]

    all_items: list[Item] = []
    for name, fn in adapters:
        try:
            vals = fn()
            # Adapter contract: collector rejects any accidental language mismatch immediately.
            vals = [x for x in vals if x.language == language]
            all_items.extend(vals)
            diagnostics["adapters"][name] = {"ok": True, "count": len(vals)}
        except Exception as e:
            diagnostics["adapters"][name] = {"ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"}

    now = dt.datetime.now(dt.timezone.utc)
    all_items = [x for x in all_items if x.language == language and eligible(x, now)]
    all_items, dupes, malformed = dedupe(all_items)
    diagnostics["duplicatesRemoved"] = dupes
    diagnostics["discardedMalformed"] = malformed
    chosen = choose_diverse(all_items, language, now)
    for lane in LANE_ORDER:
        diagnostics["itemCounts"][lane] = sum(1 for x in chosen if x.lane == lane)
    if meditation or chosen:
        diagnostics["lastSucceeded"] = iso_now()
    return {
        "generatedAt": iso_now(),
        "language": language,
        "meditation": meditation,
        "headlines": [x.as_dict() for x in chosen],
        "_diagnostics": diagnostics,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--language", choices=["en", "fr"], default="en")
    ap.add_argument("--date", help="YYYY-MM-DD override for deterministic runs")
    ap.add_argument("--output", "-o", help="write JSON file; default stdout")
    args = ap.parse_args(argv)
    date = dt.date.fromisoformat(args.date) if args.date else None
    payload = collect(args.language, date)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, args.output)
    else:
        sys.stdout.write(text)
    # A partial feed is still a successful collector run; all-adapter failure exits nonzero.
    ok = bool(payload.get("meditation") or payload.get("headlines"))
    return 0 if ok else 2

if __name__ == "__main__":
    raise SystemExit(main())
