# Features

_Updated as features ship_

## Shipped — Wave 1 + 2 (2026-04-30)

### Scraper
- Headless Chromium via Playwright — own browser instance, no audio, no visible window, doesn't touch Eytan's daily Chrome
- Two transcript panel formats supported (classic `ytd-transcript-segment-renderer` + modern `transcript-segment-view-model`)
- Auto-vs-manual transcript source detection
- Channel handle → latest video ID resolver (`@TomNashTV` → newest watch URL)
- Always returns a dict, never raises — error states: `invalid_url`, `player_not_loaded`, `no_transcript`, `segments_not_loaded`, `empty_transcript`

### Summarizer
- 6 channels read from `channels.yaml`
- Dedup by video ID (skips if `posts/{vid}.md` already exists)
- 26h rolling window age cutoff (24h + 2h transcript-generation buffer)
- Transcript truncation: head 60% + tail 30% if > 48K chars (~12K tokens)
- Gemini 2.5 Flash with `thinking_budget=0` (cheapest mode), JSON mode
- Per-video try/except — single failure doesn't kill the run
- `processed.json` lockfile + per-channel error isolation
- `data/costs.json` writer — appends entry + maintains monthly aggregate
- Placeholder MD for videos with no transcript / members-only

### Site (Astro)
- RTL Hebrew (`dir="rtl" lang="he"`)
- `noindex,nofollow` meta — public repo but not search-indexed
- Single chronological feed, newest first
- 7 topic-pill filters (כל הקטגוריות / Tesla / Palantir / AI / Markets / Innovation / General), JS-only filter no page reload
- Per-post: Hebrew title, channel-date-duration meta line, category pill, summary paragraphs, key-points list, "צפה במקור ←" link
- Monthly cost widget in header (reads `costs.json` at build time)
- Warm off-white #FAFAF7 bg, #1A1A1A text, 18px Heebo body, 1.75 line-height, 680px max-width
- Heebo + Inter from Google Fonts
- Mobile responsive: horizontal-scroll pill strip on narrow screens
- Empty state when no posts

### Automation
- GitHub Action cron 06:00 UTC daily
- `concurrency: { group: newsletter, cancel-in-progress: false }`
- Auto-commits new posts + costs.json back to repo with retry-on-conflict
- Deploys to GitHub Pages via `actions/deploy-pages@v4`