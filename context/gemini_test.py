"""
A/B test: Gemini 2.5 Flash vs Claude Haiku 4.5 on the same 3 PoC videos.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import yt_scraper

MODEL = "models/gemini-2.5-flash"
INPUT_PRICE_PER_MTOK = 0.075
OUTPUT_PRICE_PER_MTOK = 0.30
MAX_TRANSCRIPT_CHARS = 48_000

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "poc-results-gemini"

DEFAULT_VIDEOS = [
    {"video_id": "ag589INxdDk", "channel": "Tom Nash"},
    {"video_id": "VyDeaRin-hw", "channel": "Dr Know-it-all Knows it all"},
    {"video_id": "Y0j-7a88BHk", "channel": "Solving The Money Problem"},
]

PROMPT_TEMPLATE = (
    "You are a financial/tech newsletter editor writing in NATURAL Hebrew for an Israeli scriptwriter who has read content for 20+ years. He will immediately spot translated-feeling Hebrew or stilted phrasing.\n\n"
    "Read the YouTube transcript below and produce JSON with these fields:\n\n"
    "{{\n"
    '  "title_he": "כותרת בעברית טבעית, 6-10 מילים, לא תרגום מילולי",\n'
    '  "summary_he": "2-3 פסקאות בעברית רהוטה. הימנע מקאלקים מאנגלית. שמור על שמות מותגים באנגלית (Tesla, Palantir, ARK). אל תתחיל ב\'הוידאו עוסק ב\' - תיכנס ישר לתוכן. כתוב כמו עיתונאי כלכלי ישראלי, לא כמו מתרגם.",\n'
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


def load_api_key():
    try:
        from dotenv import load_dotenv
        project_env = SCRIPT_DIR.parent / ".env"
        if project_env.exists():
            load_dotenv(project_env)
        else:
            load_dotenv()
    except ImportError:
        pass
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("ERROR: GEMINI_API_KEY not found in .env or env.")
    return key


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


def fetch_transcript(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    return yt_scraper.get_transcript(url)


def summarize_with_gemini(model, channel_name, original_title, transcript):
    client, types = model
    prompt = PROMPT_TEMPLATE.format(
        channel_name=channel_name,
        original_title=original_title or "(unknown)",
        transcript=transcript,
    )
    t0 = time.time()
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        ),
    )
    elapsed = round(time.time() - t0, 2)
    raw = ""
    try:
        raw = resp.text or ""
    except Exception:
        try:
            for cand in resp.candidates or []:
                for part in cand.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        raw += part.text
        except Exception:
            pass
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
    try:
        parsed = parse_model_json(raw)
    except Exception as e:
        parsed = {"_parse_error": str(e), "_raw": raw}
    return {
        "model_output": parsed,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": round(cost_usd, 6),
        "api_time_sec": elapsed,
    }


def process_video(model, video_id, channel_name):
    print(f"\n-> {video_id} ({channel_name})", flush=True)
    t0 = time.time()
    scrape = fetch_transcript(video_id)
    scrape_secs = round(time.time() - t0, 2)
    transcript = (scrape.get("transcript") or "").strip()
    title = scrape.get("title") or ""
    duration_sec = scrape.get("duration_sec")
    source = scrape.get("source")
    err = scrape.get("error")
    print(f"  scrape: {scrape_secs}s  source={source}  err={err}  chars={len(transcript)}", flush=True)
    if not transcript:
        result = {
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "channel": channel_name,
            "original_title": title,
            "duration_sec": duration_sec,
            "transcript_source": source,
            "scrape_time_sec": scrape_secs,
            "status": f"skipped_{err or 'no_transcript'}",
        }
        save_result(video_id, result)
        return result
    truncated, was_truncated = truncate_transcript(transcript)
    summary = summarize_with_gemini(model, channel_name, title, truncated)
    print(f"  cost: ${summary['cost_usd']:.6f}  in={summary['input_tokens']} out={summary['output_tokens']}  api={summary['api_time_sec']}s", flush=True)
    result = {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel_name,
        "original_title": title,
        "duration_sec": duration_sec,
        "transcript_source": source,
        "transcript_chars": len(transcript),
        "was_truncated": was_truncated,
        "scrape_time_sec": scrape_secs,
        "model": MODEL,
        "status": "ok",
        **summary,
    }
    save_result(video_id, result)
    return result


def save_result(video_id, result):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{video_id}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  saved -> {out}", flush=True)


def main():
    api_key = load_api_key()
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("ERROR: pip install google-genai")
    client = genai.Client(api_key=api_key)
    model = (client, types)
    results = []
    for v in DEFAULT_VIDEOS:
        try:
            results.append(process_video(model, v["video_id"], v["channel"]))
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}", flush=True)
            results.append({"video_id": v["video_id"], "channel": v["channel"], "status": f"error_{type(e).__name__}"})
    print("\n=== Summary ===")
    total = 0.0
    ok = 0
    for r in results:
        if r.get("status") == "ok":
            ok += 1
            total += r.get("cost_usd", 0.0)
            print(f"  OK   {r['video_id']}  ${r['cost_usd']:.6f}  {r.get('channel','')}")
        else:
            print(f"  FAIL {r['video_id']}  {r.get('status')}")
    print(f"Done. {ok}/{len(results)} videos. Total: ${total:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())