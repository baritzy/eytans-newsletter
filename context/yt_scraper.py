"""
YouTube Transcript Scraper - Headless Chromium via Playwright.

Launches its OWN headless Chromium instance (separate profile, no audio,
no visible windows). Does NOT attach to Eytan's daily Chrome - this means
the daily summarizer can run in the background without interrupting his
work, and the same code runs unchanged in GitHub Actions CI.

Note: Etsy driver (T-tools/etsy-driver/) still uses port 9222 + Eytan's
Chrome because it needs his Etsy login. This scraper is independent.

Usage:
  python yt_scraper.py <video_url>             # scrape transcript -> JSON
  python yt_scraper.py --channel @TomNashTV    # latest video URL on channel
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
LAUNCH_ARGS = [
    "--mute-audio",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
]

YT_ID_RE = re.compile(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")
JUNK_RE = re.compile(r"\[(Music|Applause|Laughter|Background\s+\w+)\]", re.I)
ARROW_RE = re.compile(r">>+\s*")
WS_RE = re.compile(r"\s+")
ISO_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def extract_video_id(url_or_id: str) -> Optional[str]:
    s = (url_or_id or "").strip()
    m = YT_ID_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    return None


def parse_iso_duration(iso: str) -> Optional[int]:
    if not iso:
        return None
    m = ISO_DUR_RE.fullmatch(iso.strip())
    if not m:
        return None
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def launch_browser_and_context(playwright):
    """Launch a fresh headless Chromium with our own context. Returns (browser, context)."""
    browser = playwright.chromium.launch(
        headless=True,
        args=LAUNCH_ARGS,
    )
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    return browser, context


def _try_click(page, selectors, label, timeout=2500):
    """Try a list of selectors; click the first that resolves. Return success."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
                loc.click(timeout=timeout)
                log(f"  clicked: {label} ({sel})")
                return True
        except Exception:
            continue
    return False


def _dismiss_consent(page):
    """Best-effort: handle YouTube/Google consent walls."""
    selectors = [
        'button[aria-label="Accept all"]',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'tp-yt-paper-button:has-text("Accept all")',
    ]
    if _try_click(page, selectors, "consent accept", timeout=1500):
        page.wait_for_timeout(800)


def _read_duration(page):
    """Try meta itemprop duration first, then visible player time."""
    try:
        iso = page.locator('meta[itemprop="duration"]').first.get_attribute("content", timeout=1500)
        secs = parse_iso_duration(iso or "")
        if secs:
            return secs
    except Exception:
        pass
    try:
        text = page.locator(".ytp-time-duration").first.inner_text(timeout=1500)
        if text and re.fullmatch(r"[\d:]+", text.strip()):
            parts = [int(x) for x in text.strip().split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
    except Exception:
        pass
    return None


def _read_title(page):
    selectors = [
        "h1.style-scope.ytd-watch-metadata yt-formatted-string",
        "h1.ytd-watch-metadata",
        "h1 yt-formatted-string",
    ]
    for sel in selectors:
        try:
            t = page.locator(sel).first.inner_text(timeout=1500)
            if t and t.strip():
                return t.strip()
        except Exception:
            continue
    try:
        t = page.title()
        return re.sub(r"\s*-\s*YouTube\s*$", "", t).strip() or None
    except Exception:
        return None


def _detect_source(page):
    """Inspect transcript-panel language dropdown text. 'auto-generated' => auto."""
    selectors = [
        "ytd-transcript-search-panel-renderer .dropdown-trigger-text",
        "ytd-transcript-search-panel-renderer tp-yt-paper-dropdown-menu",
        "ytd-transcript-footer-renderer",
        "ytd-transcript-footer-renderer yt-dropdown-menu",
    ]
    for sel in selectors:
        try:
            txt = page.locator(sel).first.inner_text(timeout=1500)
            if not txt:
                continue
            low = txt.lower()
            if "auto-generated" in low or "auto generated" in low or "automatic" in low:
                return "auto"
            if "english" in low or "translate" in low or any(c.isalpha() for c in txt):
                return "manual"
        except Exception:
            continue
    return None


def _open_transcript_panel(page):
    """Expand description, then click 'Show transcript'. Return True on success."""
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(400)
    expand_selectors = [
        "tp-yt-paper-button#expand",
        "#expand",
        'ytd-text-inline-expander tp-yt-paper-button#expand',
        'button[aria-label*="more" i]',
    ]
    _try_click(page, expand_selectors, "expand description", timeout=2500)
    page.wait_for_timeout(600)

    show_selectors = [
        'button[aria-label="Show transcript"]',
        'ytd-button-renderer:has-text("Show transcript") button',
        'button:has-text("Show transcript")',
        'yt-button-shape:has-text("Show transcript") button',
        '#primary-button ytd-button-renderer:has-text("transcript") button',
    ]
    if _try_click(page, show_selectors, "show transcript", timeout=4000):
        return True

    log("  no top-level Show transcript - trying actions menu")
    try:
        page.locator('ytd-menu-renderer button[aria-label="More actions"]').first.click(timeout=2500)
        page.wait_for_timeout(500)
        if _try_click(
            page,
            [
                'tp-yt-paper-item:has-text("Show transcript")',
                'ytd-menu-service-item-renderer:has-text("transcript")',
            ],
            "menu -> show transcript",
            timeout=2500,
        ):
            return True
    except Exception:
        pass
    return False


TIMESTAMP_LINE_RE = re.compile(r"^\d+:\d+(?::\d+)?$")
RELATIVE_LINE_RE = re.compile(
    r"^(?:\d+\s+minutes?(?:,\s*\d+\s+seconds?)?|\d+\s+seconds?)$",
    re.I,
)
HEADER_LINES = {"transcript", "search transcript"}

INLINE_RELTIME_RE = re.compile(
    r"\s*\b\d+\s+minutes?(?:,\s*\d+\s+seconds?)?\s*(?=[A-Z]|$)",
    re.I,
)
INLINE_SECS_RE = re.compile(r"\s*\b\d+\s+seconds?\s*(?=[A-Z]|$)", re.I)


def _extract_transcript_classic(page):
    """Old DOM: ytd-transcript-segment-renderer with .segment-text children."""
    selectors = [
        "ytd-transcript-segment-renderer .segment-text",
        "ytd-transcript-segment-renderer yt-formatted-string.segment-text",
        "#segments-container .segment-text",
        "ytd-transcript-search-panel-renderer .segment-text",
    ]
    for sel in selectors:
        try:
            handles = page.locator(sel)
            count = handles.count()
            if count == 0:
                continue
            parts = []
            for i in range(count):
                try:
                    t = handles.nth(i).inner_text(timeout=500)
                    if t:
                        parts.append(t.strip())
                except Exception:
                    continue
            if parts:
                joined = " ".join(parts)
                return joined or None
        except Exception:
            continue
    return None


def _extract_transcript_modern(page):
    """
    New DOM (target-id='PAmodern_transcript_view'): each caption line is a
    <transcript-segment-view-model> with the timestamp + screen-reader 'N
    seconds' marker as separate child divs. Use JavaScript to extract just
    the spoken text from each segment, ignoring the time/sr-hint nodes.
    """
    js = """() => {
      const segs = document.querySelectorAll("transcript-segment-view-model");
      if (!segs.length) return null;
      const parts = [];
      for (const seg of segs) {
        const clones = seg.cloneNode(true);
        clones.querySelectorAll(
          ".ytwTranscriptSegmentViewModelTimestamp, .yt-spec-inline-text-ellipsis-renderer__sr-only"
        ).forEach(n => n.remove());
        clones.querySelectorAll("*").forEach(n => {
          const t = (n.innerText || "").trim();
          if (/^\d+:\d+(:\d+)?$/.test(t)) n.remove();
          else if (/^\d+\s+seconds?$/i.test(t)) n.remove();
          else if (/^\d+\s+minutes?(?:,\s*\d+\s+seconds?)?$/i.test(t)) n.remove();
        });
        const txt = (clones.innerText || "").replace(/\s+/g, " ").trim();
        if (txt) parts.push(txt);
      }
      return parts.join(" ");
    }"""
    try:
        text = page.evaluate(js)
    except Exception:
        return None
    if not text:
        return None
    return text


def _extract_transcript_text(page, panel_kind=None):
    """Try the requested kind first, then fall back to the other."""
    text = None
    if panel_kind == "modern":
        text = _extract_transcript_modern(page)
        if not text:
            text = _extract_transcript_classic(page)
    else:
        text = _extract_transcript_classic(page)
        if not text:
            text = _extract_transcript_modern(page)
    if not text:
        return None
    text = JUNK_RE.sub(" ", text)
    text = ARROW_RE.sub(" ", text)
    text = INLINE_RELTIME_RE.sub(" ", text)
    text = INLINE_SECS_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    return text or None


def _get_transcript_ytdlp(video_url):
    """Fetch transcript via yt-dlp Python API. Returns cleaned text or None."""
    try:
        import yt_dlp
    except ImportError:
        return None

    vid = extract_video_id(video_url) or ""
    if not vid:
        return None

    import tempfile, glob, os

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "writeautomaticsub": True,
                "writesubtitles": True,
                "subtitleslangs": ["en"],
                "subtitlesformat": "vtt",
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={vid}"])
            vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
            if not vtt_files:
                log("  yt-dlp: no VTT subtitle file found")
                return None
            with open(vtt_files[0], encoding="utf-8") as f:
                raw = f.read()
            return _parse_vtt(raw)
    except Exception as e:
        log(f"  yt-dlp transcript error: {e}")
        return None


def _parse_vtt(vtt_text):
    """Extract spoken text from a WebVTT subtitle file, deduplicated."""
    lines = vtt_text.splitlines()
    seen = set()
    parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        # strip VTT tags like <00:00:00.000><c>
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        parts.append(line)
    text = " ".join(parts)
    text = JUNK_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    return text or None


def get_transcript(video_url):
    """Scrape transcript via headless Chromium. Always returns a dict, never raises."""
    vid = extract_video_id(video_url) or ""
    out = {
        "video_id": vid,
        "transcript": "",
        "source": None,
        "duration_sec": None,
        "title": None,
        "error": None,
    }

    if not vid:
        out["error"] = "invalid_url"
        return out

    canonical_url = f"https://www.youtube.com/watch?v={vid}"

    with sync_playwright() as pw:
        browser = None
        context = None
        try:
            browser, context = launch_browser_and_context(pw)
        except Exception as e:
            out["error"] = f"launch_failed: {e}"
            return out

        page = None
        try:
            log(f"-> Opening tab for {vid}")
            page = context.new_page()
            try:
                page.goto(canonical_url, wait_until="domcontentloaded", timeout=30000)
            except PWTimeout:
                log("  goto timed out at domcontentloaded - continuing anyway")

            _dismiss_consent(page)

            log("  waiting for player...")
            try:
                page.wait_for_selector("#movie_player, video", timeout=15000)
            except PWTimeout:
                out["error"] = "player_not_loaded"
                return out

            out["title"] = _read_title(page)
            out["duration_sec"] = _read_duration(page)
            log(f"  title: {out['title']!r}  duration: {out['duration_sec']}s")

            log("  opening transcript panel...")
            if not _open_transcript_panel(page):
                out["error"] = "no_transcript"
                return out

            log("  waiting for segments...")
            segments_ok = False
            panel_kind = None
            deadline_ms = 50000
            step_ms = 800
            elapsed = 0
            while elapsed < deadline_ms:
                try:
                    if page.locator("ytd-transcript-segment-renderer").count() > 0:
                        segments_ok = True
                        panel_kind = "classic"
                        break
                    if page.locator("transcript-segment-view-model").count() > 0:
                        segments_ok = True
                        panel_kind = "modern"
                        break
                except Exception:
                    pass
                page.wait_for_timeout(step_ms)
                elapsed += step_ms

            if not segments_ok:
                try:
                    panel_text = page.locator(
                        "ytd-engagement-panel-section-list-renderer"
                    ).first.inner_text(timeout=1500)
                    if panel_text and re.search(
                        r"transcript\s+(is\s+)?(not\s+available|unavailable|disabled)",
                        panel_text,
                        re.I,
                    ):
                        out["error"] = "no_transcript"
                        return out
                except Exception:
                    pass
                # Playwright failed to load segments — try yt-dlp before giving up
                log(f"  Playwright segments_not_loaded — trying yt-dlp fallback")
                ytdlp_text = _get_transcript_ytdlp(canonical_url)
                if ytdlp_text:
                    out["transcript"] = ytdlp_text
                    out["source"] = "auto"
                    out["error"] = None
                    log(f"  yt-dlp fallback ok: {len(ytdlp_text)} chars")
                    return out
                out["error"] = "segments_not_loaded"
                return out

            log(f"  panel kind: {panel_kind}")
            page.wait_for_timeout(800)

            text = _extract_transcript_text(page, panel_kind)
            if not text:
                out["error"] = "empty_transcript"
                return out
            out["transcript"] = text
            out["source"] = _detect_source(page) or "manual"
            log(f"  ok: {len(text)} chars, source={out['source']}")
        except Exception as e:
            out["error"] = f"scrape_error: {type(e).__name__}: {e}"
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    return out


def get_latest_video_id(channel_handle):
    """Return the newest video ID on a channel. Pass e.g. '@TomNashTV'.

    Primary: yt-dlp (fast, no browser needed, reliable against YouTube bot detection).
    Fallback: Playwright (kept as backup if yt-dlp unavailable).
    """
    handle = channel_handle.strip()
    if not handle.startswith("@"):
        handle = "@" + handle
    url = f"https://www.youtube.com/{handle}/videos"

    # Primary: yt-dlp
    vid = _get_latest_video_id_ytdlp(url)
    if vid:
        return vid

    log("  yt-dlp failed, falling back to Playwright for channel page")
    return _get_latest_video_id_playwright(url)


def _get_latest_video_id_ytdlp(url):
    """Use yt-dlp Python API to get latest video ID from a channel URL."""
    try:
        import yt_dlp
    except ImportError:
        log("  yt-dlp not installed, skipping")
        return None
    try:
        ydl_opts = {
            "playlist_items": "1",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            log("  yt-dlp: no info returned")
            return None
        entries = info.get("entries") or []
        if not entries:
            log("  yt-dlp: no entries in playlist")
            return None
        vid = (entries[0] or {}).get("id", "")
        if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(vid)):
            log(f"  yt-dlp: latest video = {vid}")
            return str(vid)
        log(f"  yt-dlp: unexpected id format: {vid!r}")
        return None
    except Exception as e:
        log(f"  yt-dlp channel lookup failed: {e}")
        return None


def _get_latest_video_id_playwright(url):
    """Playwright fallback for channel page. Original implementation."""
    with sync_playwright() as pw:
        browser = None
        context = None
        try:
            browser, context = launch_browser_and_context(pw)
        except Exception as e:
            log(f"launch_failed: {e}")
            return None

        page = None
        try:
            log(f"-> Loading channel videos: {url}")
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PWTimeout:
                pass
            _dismiss_consent(page)

            try:
                page.wait_for_selector(
                    "ytd-rich-grid-renderer, ytd-rich-item-renderer", timeout=15000
                )
            except PWTimeout:
                log("  channel grid did not load")
                return None

            href = None
            selectors = [
                "ytd-rich-item-renderer a#video-title-link",
                "ytd-rich-grid-media a#video-title-link",
                "ytd-rich-item-renderer a#thumbnail",
            ]
            for sel in selectors:
                try:
                    href = page.locator(sel).first.get_attribute("href", timeout=2500)
                    if href:
                        break
                except Exception:
                    continue
            if not href:
                log("  no video link found")
                return None
            return extract_video_id(href)
        except Exception as e:
            log(f"channel scrape error: {e}")
            return None
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    if args[0] == "--channel":
        if len(args) < 2:
            print("ERROR: --channel requires a handle (e.g. @TomNashTV)", file=sys.stderr)
            return 2
        vid = get_latest_video_id(args[1])
        if not vid:
            print("ERROR: could not resolve latest video for channel", file=sys.stderr)
            return 3
        print(f"https://www.youtube.com/watch?v={vid}")
        return 0

    result = get_transcript(args[0])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("error") else 4


if __name__ == "__main__":
    sys.exit(main())