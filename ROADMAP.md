# Roadmap — Eytan's Newsletter

## Wave 1 — Research + PoC ✅ DONE
- [x] Design research: Stratechery / Axios / Platformer style; Heebo+Inter; 680px max-width; warm off-white #FAFAF7
- [x] Transcript availability research: 6 channels, two transcript-panel formats handled (classic + modern)
- [x] PoC dev: Gemini 2.5 Flash confirmed quality 8/10 on 3 videos, ~$0.0006 each
- [x] Devil's Advocate review of the plan (12+ risks identified)

## Wave 2 — Full Build ✅ DONE (this run)
- [x] `yt_scraper.py` refactored to headless Chromium (no Chrome window, no audio, no interruption to Eytan's work)
- [x] `scripts/summarize.py` — full pipeline: 6 channels, dedup by video_id, 26h-rolling-window age cutoff, 12K token transcript truncation, Gemini 2.5 Flash, JSON parsing, markdown writer, costs.json updater, per-video try/except, processed.json lockfile
- [x] `channels.yaml` — 6 channels configured
- [x] Astro site (`site/`) — RTL, single feed, topic-pill JS filter, monthly cost widget, 680px container, Heebo+Inter, noindex
- [x] GitHub Action `.github/workflows/daily-newsletter.yml` — 06:00 UTC cron, concurrency guard, retries on push
- [x] `DEPLOY.md` — 4-step deploy guide

## Wave 3 — QA + Deploy (pending — Eytan-account-level work)
- [ ] Eytan creates GitHub repo `eytans-newsletter`
- [ ] Push project (`git init && git push`)
- [ ] Add `GEMINI_API_KEY` to repo secrets
- [ ] Enable GitHub Pages (Source: GitHub Actions)
- [ ] Manual workflow_dispatch trigger
- [ ] Devil's Advocate review of live deploy
- [ ] 5-layer QA (auto coverage, data integrity, code audit, browser test + click every link, edge fuzz)
- [ ] Verify mobile + desktop on the live URL

## Wave 4 — Iterate (pending — after 1 week of operation)
- [ ] Measure: actual cost, transcript hit rate, categorization accuracy
- [ ] Re-evaluate LLM choice (target check: 2026-05-30)
- [ ] Iterate on design / categories / pipeline