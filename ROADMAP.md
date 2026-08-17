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

## Wave 3 — QA + Deploy ✅ DONE (אומת 17.8.2026)
- [x] Eytan creates GitHub repo `eytans-newsletter` (ציבורי)
- [x] Push project (`git init && git push`)
- [x] Add `GEMINI_API_KEY` to repo secrets (אומת: קיים, נוצר 1.5.26)
- [x] Enable GitHub Pages (Source: GitHub Actions) - שלב ה-deploy מצליח בכל הרצה יומית
- [x] Manual workflow_dispatch trigger
- [ ] Devil's Advocate review of live deploy - **לא אומת, לא ידוע אם בוצע**
- [ ] 5-layer QA - **לא אומת, לא ידוע אם בוצע**
- [ ] Verify mobile + desktop on the live URL - **לא אומת**

## Wave 4 — Iterate (pending — after 1 week of operation)
- [x] Measure: actual cost - **כ-₪1 לחודש**, אומת מול חיוב `Google Cloud` (17.8.26)
- [ ] Measure: transcript hit rate, categorization accuracy
- [ ] Re-evaluate LLM choice (target check: 2026-05-30 - עבר, לא בוצע)
- [ ] Iterate on design / categories / pipeline

## Wave 5 — Billing + Security ✅ DONE (14-17.8.2026)
- [x] מעבר מ-`Postpay` ל-`Prepay` ב-Gemini API (דרישת גוגל, דדליין היה 12.10.26). נטענו ₪50
- [x] אומת שהפייפליין ממשיך לרוץ אחרי המעבר: הרצות מוצלחות ב-15, 16, 17 באוגוסט
- [x] התראת התקציב תוקנה ממצטבר לחודשי (₪37, ספי 50/90/100%)
- [x] טוקן `GitHub` קלאסי הוסר מ-`.git/config` ומ-`.env`. ההזדהות עברה ל-`gh credential helper`
- [x] `lessons.md` + `PRODUCT.md` נוספו ל-gitignore (המאגר ציבורי, הם ישבו בו חשופים)

---

## NEXT UP — איפה הפסקנו

> **הקובץ הזה מקומט במאגר ציבורי.** פרטי הפעולות הפתוחות, כולל כל מה שנוגע להרשאות וחיוב, יושבים ב-`lessons.md` שהוא מקומי ומוחרג. לא להעתיק אותם לכאן.

- [x] הפעולה שדרשה את איתן בחשבון GitHub בוצעה ואומתה (17.8.26). פרטים ב-`lessons.md`
- [x] שתי ההחלטות שהמתינו הוכרעו (17.8.26). פרטים ב-`lessons.md`

**אין כרגע פעולות פתוחות מעבר לחוב הטכני למטה.**

**חוב טכני ידוע:**
- [ ] `data/costs.json` המקומי תקוע על נתוני seed מיוני. הגרסה האמיתית מתעדכנת בריפו בכל הרצה
- [ ] FARZAD-FM ו-ARKInvest2015 עדיין חסומים (ראה `lessons.md`)