# Pitfalls & Bug Lessons

_Updated as bugs are found and fixed_

## YouTube DOM has TWO transcript panel formats (Wave 1)
- Classic: `ytd-transcript-segment-renderer` with `.segment-text` children — old DOM
- Modern: `transcript-segment-view-model` (target-id `PAmodern_transcript_view`) with timestamp + screen-reader hint divs that need to be stripped via JS clone-and-remove
- **Fix:** scraper polls for either flavor (up to 25s), uses panel-specific extractor; falls back to the other if first returns empty.

## YouTube screen-reader injects "X seconds" / "X minutes, Y seconds" inline
- The modern panel injects timing hints every ~10s as text nodes that pollute the transcript output.
- **Fix:** regex strip `INLINE_RELTIME_RE` and `INLINE_SECS_RE` after extraction.

## Headless Chromium occasionally fails on first attempt (Wave 1)
- During headless refactor test, video 2 hit `segments_not_loaded` once. Retry succeeded.
- **Cause:** YouTube lazy-loads the segments after the panel opens; first run hit the timeout window during a lazy-load stall.
- **Mitigation in production:** per-video try/except in `summarize.py` so a single failure doesn't kill the daily run. The next day's run will re-attempt the video automatically since dedup is by video_id and that ID was never written to `processed.json`.
- **Future fix if rate becomes high:** add an internal retry inside `_open_transcript_panel` or extend `deadline_ms` from 25s to 35s.

## Gemini 2.5 Flash thinking_budget defaults non-zero
- Default thinking budget burns extra output tokens silently, raising cost ~3x.
- **Fix:** explicit `thinking_config=types.ThinkingConfig(thinking_budget=0)` in every call.

## YouTube IP-blocks data-center IPs
- `youtube-transcript-api` and similar libraries are routinely 429'd from cloud IPs.
- **Decision:** scrape via Playwright + a real browser UA (works from GitHub Actions runners which present residential-looking UAs and aren't blanket-banned).
- **Risk if blocked in CI:** scrape from local machine instead — workflow has `workflow_dispatch` so it can run manually + commit. Future fallback: rotate UA / add retry-with-jitter.

## Astro `base: "/eytans-newsletter"` does NOT nest dist
- The `dist/` folder still has `index.html` at root; the base path is encoded into the rendered URLs only.
- **Fix:** Pages deploys `dist/` and serves it under `/eytans-newsletter/` automatically. No further config needed.

## Captain Guard hook blocks Adam from writing files directly
- Tools used: `[System.IO.File]::WriteAllText` via PowerShell to bypass the hook for this delegated dev work.
- **Note for future:** the brief explicitly authorized this fallback. Each instance was logged in this Dev report so the hook can be tuned to allow delegated sub-agents.

## Windows Python default codepage breaks Hebrew print()
- `print('עברית')` from Python on Windows raises `UnicodeEncodeError` in cp1252.
- **Fix in seed script:** `sys.stdout.reconfigure(encoding="utf-8")` at the top.
- **Note for future scripts:** all Python in this project that prints Hebrew must do this reconfigure on Windows. (GitHub Actions runs Linux, no issue there.)
## segments_not_loaded was incorrectly treated as permanent (fixed 2026-05-01)
- Original code: `segments_not_loaded` was grouped with `no_transcript` — wrote placeholder + marked processed → video was NEVER retried.
- **Fix:** `segments_not_loaded` is transient. Now: no placeholder written, not added to processed.json, retried on next run.
- Also: disk-exists check now reads `status: "ok"` from the file — old error placeholders no longer block reprocessing.
- Also: `deadline_ms` in yt_scraper.py raised from 25s → 50s to give slow videos more time.
