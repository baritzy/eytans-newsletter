"""
Eytan's Newsletter — Daily summarizer.

Daily flow:
  1. Read channels.yaml (6 YouTube handles)
  2. For each channel, find the newest video via yt_scraper
  3. Skip if video older than 26h, or already summarized (posts/{vid}.md exists)
  4. Fetch transcript, truncate to MAX_TRANSCRIPT_CHARS, summarize via Gemini 2.5 Flash
  5. Write posts/{vid}.md with frontmatter + Hebrew body
  6. Update data/costs.json

Concurrency-safe: uses processed.json + per-video try/except. Designed to run
inside GitHub Actions on a daily cron, but works locally too.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Path bootstrap so we can import yt_scraper from ../context regardless of cwd
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
CONTEXT_DIR = PROJECT_DIR / "context"
POSTS_DIR = PROJECT_DIR / "posts"
DATA_DIR = PROJECT_DIR / "data"
COSTS_PATH = DATA_DIR / "costs.json"
PROCESSED_PATH = DATA_DIR / "processed.json"

sys.path.insert(0, str(CONTEXT_DIR))
import yt_scraper  # noqa: E402

# --- Config ---------------------------------------------------------------

MODEL = "gemini-2.5-flash"
INPUT_PRICE_PER_MTOK = 0.075
OUTPUT_PRICE_PER_MTOK = 0.30
MAX_TRANSCRIPT_CHARS = 48_000  # ~12K tokens
MAX_AGE_HOURS = 26  # rolling 24h + 2h buffer per DA risk #2

PROMPT_TEMPLATE = (
    "You are a financial/tech newsletter editor writing in NATURAL Hebrew for an Israeli scriptwriter who has read content for 20+ years. He will immediately spot translated-feeling Hebrew or stilted phrasing.\n\n"
    "Read the YouTube transcript below and produce JSON with these fields:\n\n"
    "{{\n"
    '  "title_he": "כותרת בעברית טבעית, 6-10 מילים, לא תרגום מילולי",\n'
    '  "summary_he": "2-3 פסקאות בעברית רהוטה. הימנע מקאלקים מאנגלית. שמור על שמות מותגים באנגלית (Tesla, Palantir, ARK). אל תתחיל בהוידאו עוסק ב - תיכנס ישר לתוכן. כתוב כמו עיתונאי כלכלי ישראלי, לא כמו מתרגם.",\n'
    '  "category": "אחת מ: Tesla, Palantir, AI, Markets, Innovation, General",\n'
    '  "category_reason": "משפט קצר למה הקטגוריה הזו. בחר General רק אם אף אחת מהאחרות לא מתאימה.",\n'
    '  "key_points": ["3-5 נקודות תובנה עיקריות, כל אחת משפט קצר בעברית"]\n'
    "}}\n\n"
    "Important:\n"
    "- Categorize by CONTENT, not channel.\n"
    "- Hebrew should sound like a native Israeli wrote it.\n"
    "- Brand/company names stay in English in body (Tesla, Palantir).\n"
    "- Output VALID JSON only. No markdown fences. No commentary.\n\n"
    "Channel: {channel_name}\n"
    "Original video title: {original_title}\n\n"
    "Transcript:\n"
    "{transcript}\n"
)

# --- Helpers --------------------------------------------------------------

def log(msg):
    print(msg, flush=True)


def load_env():
    try:
        from dotenv import load_dotenv
        env_path = PROJECT_DIR / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def load_channels():
    try:
        import yaml
    except ImportError:
        sys.exit("ERROR: pip install pyyaml")
    cfg_path = PROJECT_DIR / "channels.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return [c["handle"] for c in cfg.get("channels", [])]


def truncate_transcript(text):
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text, False
    head_n = int(MAX_TRANSCRIPT_CHARS * 0.60)
    tail_n = int(MAX_TRANSCRIPT_CHARS * 0.30)
    return f"{text[:head_n]}\n\n... [middle truncated] ...\n\n{text[-tail_n:]}", True


def parse_model_json(text):
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return json.loads(s)


def load_processed():
    if PROCESSED_PATH.exists():
        try:
            return json.loads(PROCESSED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"video_ids": []}
    return {"video_ids": []}


def save_processed(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_costs():
    if COSTS_PATH.exists():
        try:
            return json.loads(COSTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"entries": [], "monthly": {}}
    return {"entries": [], "monthly": {}}


def save_costs(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COSTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_cost(video_id, in_tokens, out_tokens, cost_usd):
    data = load_costs()
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_key = today_iso[:7]
    data["entries"].append({
        "date": today_iso,
        "video_id": video_id,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": round(cost_usd, 6),
    })
    monthly = data.setdefault("monthly", {})
    monthly[month_key] = round(monthly.get(month_key, 0.0) + cost_usd, 6)
    save_costs(data)


# --- Gemini call ----------------------------------------------------------

def get_gemini_client():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("ERROR: GEMINI_API_KEY not set")
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("ERROR: pip install google-genai")
    return genai.Client(api_key=key), types


def summarize_with_gemini(client, types, channel_name, original_title, transcript):
    prompt = PROMPT_TEMPLATE.format(
        channel_name=channel_name,
        original_title=original_title or "(unknown)",
        transcript=transcript,
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        ),
    )
    raw = ""
    try:
        raw = resp.text or ""
    except Exception:
        for cand in resp.candidates or []:
            for part in cand.content.parts or []:
                if hasattr(part, "text") and part.text:
                    raw += part.text
    in_tokens = 0
    out_tokens = 0
    try:
        um = resp.usage_metadata
        in_tokens = getattr(um, "prompt_token_count", 0) or 0
        out_tokens = getattr(um, "candidates_token_count", 0) or 0
    except Exception:
        pass
    cost_usd = (
        in_tokens / 1_000_000 * INPUT_PRICE_PER_MTOK
        + out_tokens / 1_000_000 * OUTPUT_PRICE_PER_MTOK
    )
    parsed = parse_model_json(raw)
    return parsed, in_tokens, out_tokens, round(cost_usd, 6)


# --- Markdown writer ------------------------------------------------------

def md_escape_yaml(s):
    if s is None:
        return ""
    s = str(s).replace('"', '\\"').replace("\n", " ").strip()
    return s


def write_post(video_id, frontmatter, body):
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    out = POSTS_DIR / f"{video_id}.md"
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, bool):
            fm_lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            fm_lines.append(f"{k}: {v}")
        elif isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f'  - "{md_escape_yaml(item)}"')
        else:
            fm_lines.append(f'{k}: "{md_escape_yaml(v)}"')
    fm_lines.append("---")
    out.write_text("\n".join(fm_lines) + "\n\n" + body + "\n", encoding="utf-8")
    return out


def write_placeholder(video_id, channel, original_title, status):
    fm = {
        "date": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "original_title": original_title or "",
        "hebrew_title": original_title or "(ללא תמלול)",
        "category": "General",
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "duration_sec": 0,
        "transcript_source": status,
        "was_truncated": False,
        "cost_usd": 0,
        "status": status,
    }
    body = f"_וידאו זה לא סוכם — סטטוס: `{status}`._"
    return write_post(video_id, fm, body)


# --- Main per-channel ----------------------------------------------------

def is_too_old(video_published_iso):
    if not video_published_iso:
        return False
    try:
        dt = datetime.fromisoformat(video_published_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    return (now - dt) > timedelta(hours=MAX_AGE_HOURS)


def process_channel(client, types, handle, processed):
    log(f"\n=== {handle} ===")
    try:
        vid = yt_scraper.get_latest_video_id(handle)
    except Exception as e:
        log(f"  channel scrape failed: {type(e).__name__}: {e}")
        return None
    if not vid:
        log("  no latest video found")
        return None
    if vid in processed.get("video_ids", []):
        log(f"  {vid}: already processed, skipping")
        return None
    if (POSTS_DIR / f"{vid}.md").exists():
        log(f"  {vid}: post exists on disk, skipping")
        processed.setdefault("video_ids", []).append(vid)
        return None

    log(f"  {vid}: fetching transcript...")
    try:
        scrape = yt_scraper.get_transcript(f"https://www.youtube.com/watch?v={vid}")
    except Exception as e:
        log(f"  transcript fetch failed: {type(e).__name__}: {e}")
        return None

    err = scrape.get("error")
    transcript = (scrape.get("transcript") or "").strip()
    title = scrape.get("title") or ""
    duration = scrape.get("duration_sec")
    source = scrape.get("source")

    if err in ("no_transcript", "members_only", "empty_transcript", "segments_not_loaded"):
        log(f"  {vid}: no transcript ({err}) — placeholder")
        write_placeholder(vid, handle, title, err)
        processed.setdefault("video_ids", []).append(vid)
        return vid
    if err or not transcript:
        log(f"  {vid}: scrape error: {err}")
        return None

    truncated, was_truncated = truncate_transcript(transcript)
    log(f"  {vid}: transcript {len(transcript)} chars (truncated={was_truncated}) -> Gemini")
    try:
        parsed, in_tok, out_tok, cost = summarize_with_gemini(client, types, handle, title, truncated)
    except Exception as e:
        log(f"  Gemini call failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

    fm = {
        "date": datetime.now(timezone.utc).isoformat(),
        "channel": handle,
        "original_title": title,
        "hebrew_title": parsed.get("title_he", title),
        "category": parsed.get("category", "General"),
        "video_id": vid,
        "video_url": f"https://www.youtube.com/watch?v={vid}",
        "duration_sec": duration or 0,
        "transcript_source": source or "manual",
        "was_truncated": was_truncated,
        "cost_usd": cost,
        "status": "ok",
        "key_points": parsed.get("key_points", []),
    }
    body_parts = [parsed.get("summary_he", "")]
    kp = parsed.get("key_points") or []
    if kp:
        body_parts.append("\n## נקודות עיקריות\n")
        for p in kp:
            body_parts.append(f"- {p}")
    write_post(vid, fm, "\n".join(body_parts))
    append_cost(vid, in_tok, out_tok, cost)
    processed.setdefault("video_ids", []).append(vid)
    log(f"  {vid}: OK  cost ${cost:.6f}  cat={fm['category']}")
    return vid


# --- Entry point ---------------------------------------------------------

def main():
    load_env()
    handles = load_channels()
    log(f"channels: {len(handles)}")
    client, types = get_gemini_client()
    processed = load_processed()
    new_posts = []
    t0 = time.time()
    for handle in handles:
        try:
            r = process_channel(client, types, handle, processed)
            if r:
                new_posts.append(r)
        except Exception as e:
            log(f"  channel {handle} unexpected error: {type(e).__name__}: {e}")
            traceback.print_exc()
    save_processed(processed)
    elapsed = round(time.time() - t0, 1)
    log(f"\nDone in {elapsed}s. New posts: {len(new_posts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())