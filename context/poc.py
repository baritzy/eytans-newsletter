"""
PoC: YouTube -> Hebrew newsletter summary
Pipeline: URL -> transcript (yt_scraper via Eytans Chrome on port 9222)
        -> Claude Haiku 4.5 -> JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

# Sibling module - the Playwright/CDP scraper.
import yt_scraper

# --- Constants ---------------------------------------------------------------

MODEL = "claude-haiku-4-5-20251001"
INPUT_PRICE_PER_MTOK = 1.0   # USD per million input tokens
OUTPUT_PRICE_PER_MTOK = 5.0  # USD per million output tokens

# Rough char->token estimate for truncation budget. ~4 chars/token for English.
MAX_TRANSCRIPT_CHARS = 48_000  # ~12K tokens

# Default test channels - handle and channel name (channel_id resolved at runtime)
DEFAULT_CHANNELS = [
    {"handle": "@TomNashTV", "name": "Tom Nash"},
    {"handle": "@DrKnowitallKnows", "name": "Dr Know-it-all Knows it all"},
    {"handle": "@SolvingTheMoneyProblem", "name": "Solving The Money Problem"},
]

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "poc-results"

# --- Env / API key -----------------------------------------------------------

def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from .env (project folder), then OS env."""
    try:
        from dotenv import load_dotenv
        project_env = SCRIPT_DIR.parent / ".env"
        if project_env.exists():
            load_dotenv(project_env)
        else:
            load_dotenv()
    except ImportError:
        pass

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit(
            "ERROR: ANTHROPIC_API_KEY not found.\n"
            f"  Add it to {SCRIPT_DIR.parent / '.env'} as:\n"
            "    ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Or set it in your environment."
        )
    return key


# --- YouTube helpers ---------------------------------------------------------

YT_ID_PATTERNS = [
    re.compile(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]

def extract_video_id(url_or_id: str) -> Optional[str]:
    s = url_or_id.strip()
    for pat in YT_ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return None


def resolve_channel_id_from_handle(handle: str) -> Optional[str]:
    """Scrape channel page for canonical channel_id. Read-only HTML fetch."""
    handle = handle.lstrip("@")
    url = f"https://www.youtube.com/@{handle}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (newsletter-poc)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"channelId":"(UC[A-Za-z0-9_-]{22})"', html)
        if m:
            return m.group(1)
        m = re.search(r'channel/(UC[A-Za-z0-9_-]{22})', html)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"  ! Failed to resolve channel for {handle}: {e}")
    return None


def latest_video_from_channel_rss(channel_id: str) -> Optional[dict]:
    """Return {video_id, title} of newest video on channel via RSS."""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        req = urllib.request.Request(
            rss_url, headers={"User-Agent": "Mozilla/5.0 (newsletter-poc)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        vid = entry.find("yt:videoId", ns)
        title = entry.find("atom:title", ns)
        if vid is None:
            return None
        return {
            "video_id": vid.text,
            "title": (title.text if title is not None else "").strip(),
        }
    except Exception as e:
        print(f"  ! RSS fetch failed for {channel_id}: {e}")
        return None


def get_video_title(video_id: str) -> str:
    """Best-effort title fetch via oEmbed (no API key required)."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (newsletter-poc)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("title") or "").strip()
    except Exception:
        return ""


# --- Transcript --------------------------------------------------------------

def fetch_transcript(video_id: str) -> dict:
    """
    Scrape the transcript via Eytans real Chrome (port 9222).
    Returns the dict from yt_scraper.get_transcript(): keys
      transcript, source, duration_sec, title, error, video_id.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    return yt_scraper.get_transcript(url)


def truncate_transcript(text: str) -> tuple[str, bool]:
    """Keep first 60% + last 30% if over budget. Return (text, was_truncated)."""
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text, False
    head_n = int(MAX_TRANSCRIPT_CHARS * 0.60)
    tail_n = int(MAX_TRANSCRIPT_CHARS * 0.30)
    head = text[:head_n]
    tail = text[-tail_n:]
    return f"{head}\n\n... [middle truncated] ...\n\n{tail}", True


# --- Claude call -------------------------------------------------------------

PROMPT_TEMPLATE = """You are a financial/tech newsletter editor writing in NATURAL Hebrew for an Israeli scriptwriter who has read content for 20+ years. He will immediately spot translated-feeling Hebrew or stilted phrasing.

Read the YouTube transcript below and produce JSON with these fields:

{{
  "title_he": "כותרת בעברית טבעית, 6-10 מילים, לא תרגום מילולי",
  "summary_he": "2-3 פסקאות בעברית רהוטה. הימנע מקאלקים מאנגלית. שמור על שמות מותגים באנגלית (Tesla, Palantir, ARK). אל תתחיל ב'הוידאו עוסק ב' - תיכנס ישר לתוכן. כתוב כמו עיתונאי כלכלי ישראלי, לא כמו מתרגם.",
  "category": "אחת מ: Tesla, Palantir, AI, Markets, Innovation, General",
  "category_reason": "משפט קצר למה הקטגוריה הזו. בחר General רק אם אף אחת מהאחרות לא מתאימה.",
  "key_points": ["3-5 נקודות תובנה עיקריות, כל אחת משפט קצר בעברית"]
}}

Important:
- Categorize by CONTENT, not channel.
- Hebrew should sound like a native Israeli wrote it.
- Brand/company names stay in English in body (Tesla, Palantir).
- Output VALID JSON only. No markdown fences. No commentary.

Channel: {channel_name}
Original video title: {original_title}

Transcript:
{transcript}
"""


def parse_model_json(text: str) -> dict:
    """Strip markdown fences if any, then json.loads."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return json.loads(s)


def summarize(client, channel_name: str, original_title: str, transcript: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        channel_name=channel_name,
        original_title=original_title or "(unknown)",
        transcript=transcript,
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    in_tokens = msg.usage.input_tokens
    out_tokens = msg.usage.output_tokens
    cost_usd = (
        in_tokens / 1_000_000 * INPUT_PRICE_PER_MTOK
        + out_tokens / 1_000_000 * OUTPUT_PRICE_PER_MTOK
    )
    try:
        parsed = parse_model_json(raw)
    except Exception as e:
        parsed = {"_parse_error": str(e), "_raw": raw}
    return {
        "model_output": parsed,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": round(cost_usd, 6),
    }


# --- Per-video orchestrator --------------------------------------------------

def process_video(client, video_id: str, channel_name: str = "") -> dict:
    print(f"\n-> {video_id} ({channel_name or 'manual'})")

    t0 = time.time()
    scrape = fetch_transcript(video_id)
    scrape_secs = round(time.time() - t0, 2)

    transcript = (scrape.get("transcript") or "").strip()
    scraped_title = scrape.get("title") or ""
    duration_sec = scrape.get("duration_sec")
    transcript_source = scrape.get("source")
    scrape_error = scrape.get("error")

    # Fall back to oEmbed if scraper didnt grab the title.
    original_title = scraped_title or get_video_title(video_id)
    if original_title:
        print(f"  title: {original_title}")
    if duration_sec:
        print(f"  duration: {duration_sec}s")
    print(f"  scrape time: {scrape_secs}s  source: {transcript_source}  error: {scrape_error}")

    if not transcript:
        result = {
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "channel": channel_name,
            "original_title": original_title,
            "duration_sec": duration_sec,
            "transcript_source": transcript_source,
            "scrape_time_sec": scrape_secs,
            "status": f"skipped_{scrape_error or 'no_transcript'}",
        }
        save_result(video_id, result)
        return result

    truncated_text, was_truncated = truncate_transcript(transcript)
    print(f"  transcript: {len(transcript)} chars (truncated={was_truncated})")

    summary = summarize(client, channel_name or "(unknown)", original_title, truncated_text)
    print(f"  cost: ${summary['cost_usd']:.4f}  in={summary['input_tokens']} out={summary['output_tokens']}")

    result = {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel_name,
        "original_title": original_title,
        "duration_sec": duration_sec,
        "transcript_source": transcript_source,
        "transcript_chars": len(transcript),
        "was_truncated": was_truncated,
        "scrape_time_sec": scrape_secs,
        "status": "ok",
        **summary,
    }
    save_result(video_id, result)
    return result


def save_result(video_id: str, result: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{video_id}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved -> {out_path}")


# --- CLI ---------------------------------------------------------------------

# 3 fixed default videos for the PoC run (per Adams brief).
DEFAULT_VIDEOS = [
    {"video_id": "ag589INxdDk", "channel": "Tom Nash"},
    {"video_id": "VyDeaRin-hw", "channel": "Dr Know-it-all Knows it all"},
    {"video_id": "Y0j-7a88BHk", "channel": "Solving The Money Problem"},
]


def run_default_set(client) -> list[dict]:
    print("Running on 3 fixed PoC videos...")
    results = []
    for v in DEFAULT_VIDEOS:
        results.append(process_video(client, v["video_id"], v["channel"]))
    return results


def run_latest_per_channel(client) -> list[dict]:
    """Optional: resolve the latest video per default channel via RSS."""
    print("Resolving latest videos from default channels...")
    targets = []
    for ch in DEFAULT_CHANNELS:
        cid = resolve_channel_id_from_handle(ch["handle"])
        if not cid:
            print(f"  ! Skipping {ch['handle']} - could not resolve channel_id")
            continue
        latest = latest_video_from_channel_rss(cid)
        if not latest:
            print(f"  ! No RSS entry for {ch['handle']}")
            continue
        print(f"  {ch['handle']} -> {latest['video_id']}: {latest['title']}")
        targets.append((latest["video_id"], ch["name"]))

    results = []
    for vid, name in targets:
        results.append(process_video(client, vid, name))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="YouTube -> Hebrew newsletter summary PoC (Claude Haiku 4.5)."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube video URL or 11-char video ID. Omit to run on 3 default videos.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve newest video per default channel via RSS instead of fixed set.",
    )
    args = parser.parse_args()

    api_key = load_api_key()
    try:
        from anthropic import Anthropic
    except ImportError:
        sys.exit("ERROR: anthropic package not installed. Run: pip install -r requirements.txt")
    client = Anthropic(api_key=api_key)

    if args.url:
        vid = extract_video_id(args.url)
        if not vid:
            sys.exit(f"ERROR: could not extract video ID from: {args.url}")
        results = [process_video(client, vid, "")]
    elif args.latest:
        results = run_latest_per_channel(client)
    else:
        results = run_default_set(client)

    print("\n=== Summary ===")
    total_cost = 0.0
    ok = 0
    for r in results:
        if r.get("status") == "ok":
            ok += 1
            total_cost += r.get("cost_usd", 0.0)
            print(f"  OK   {r['video_id']}  ${r['cost_usd']:.4f}  {r.get('channel','')}")
        else:
            print(f"  SKIP {r['video_id']}  ({r.get('status')})  {r.get('channel','')}")
    print(f"Done. {ok}/{len(results)} videos. Total cost: ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())