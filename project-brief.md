# Project Brief — Eytan's Newsletter

## Project Name
Eytan's Newsletter

## Owner
Eytan (personal use, not for clients)

## Goal
Daily-updated personal newsletter site that auto-summarizes new videos from 6 YouTube channels in Hebrew, categorized by content topic (Tesla / Palantir / AI / Markets / Innovation / General).

## Channels
- SolvingTheMoneyProblem
- TomNashTV
- FARZAD-FM
- BestInTESLA
- DrKnowitallKnows
- ARKInvest2015

## Stack
- **Summarization:** Python script
- **Site generator:** Astro or 11ty (static site)
- **Automation:** GitHub Actions cron — daily at 09:00 IST
- **Hosting:** GitHub Pages (NOT Netlify — preserves Netlify credits for other projects)

## LLM
- **Model:** Claude Haiku 4.5 via Anthropic API
- **Estimated cost:** $1.50 / month
- **Budget:** Eytan has $4 in API credit
- **Re-evaluation date:** 2026-05-30 (after 1 month of operation)
- **Fallback:** If cost exceeds $2 / month → switch to Gemini Flash (free)

## Constraints
- **Long videos:** Skip videos longer than 70 minutes. Mark them on the site with "video too long — not summarized" + link to the original video.
- **Categorization:** By CONTENT, not by channel (e.g., Tom Nash talking about Tesla → Tesla tag).
- **Transcripts:** Try in this order:
  1. Manual subtitles
  2. Auto-generated subtitles
  3. If neither exists → mark as "no transcript available"
- **Hosting:** GitHub Pages only. ZERO Netlify deploys (Netlify credits are limited and shared across projects).
- **Responsiveness:** Site must work on PC and mobile via the GitHub Pages URL.

## Design Direction
Minimalist but professional — like a high-quality newsletter (Stratechery / Every / Platformer style). Specific design decisions emerge from Wave 1 research.

## Cost Dashboard
The site must display a running monthly cost widget. The Python script writes `cost.json` daily; the site renders it.

## Browser Rule
Default — `playwright` (Chrome). Override here if needed for parallel sessions.
