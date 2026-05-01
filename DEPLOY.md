# Deploy — Eytan's Newsletter

The build is fully automated. You only need to do 3 GitHub-account-level
things; everything else (scraping, summarizing, building, deploying) runs
in the GitHub Action cron.

## Step 1 — Create the GitHub repo

1. Open https://github.com/new
2. Name: `eytans-newsletter`
3. Visibility: **Public** (the workflow uses `noindex` so it won't be
   indexed by Google, but the source is visible). Public is required for
   free GitHub Pages on a personal account. If you want it private,
   you'll need GitHub Pro for Pages on private repos.
4. Don't initialise with a README (we'll push our own files).
5. Click **Create repository**.

## Step 2 — Push the project

In your terminal, from `p-projects/eytans-newsletter/`:

```bash
cd p-projects/eytans-newsletter
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/baritzy/eytans-newsletter.git
git push -u origin main
```

Adam will run these for you when you say "push the newsletter to GitHub".

## Step 3 — Add GEMINI_API_KEY secret + enable Pages

1. In the new repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**.
3. Name: `GEMINI_API_KEY`. Value: paste from `.env`. Click Add.
4. Go to **Settings → Pages**.
5. Source: **GitHub Actions**. Save.

## Step 4 — Trigger the first run

1. Go to **Actions** tab.
2. Click **Daily Newsletter** in the sidebar.
3. Click **Run workflow → Run workflow**.
4. Wait ~3-5 minutes.
5. Open https://baritzy.github.io/eytans-newsletter/ — should be live.

## What happens after that

- 06:00 UTC daily (09:00 Israel time), the cron runs automatically.
- New summaries land in `posts/`, costs update in `data/costs.json`.
- The workflow commits them back to the repo and redeploys Pages.
- You don't need to touch anything.

## If something breaks

- Check **Actions** tab for the failed run's logs.
- Most likely fixes: GEMINI_API_KEY missing/expired, or YouTube rate-limited.
- Tell Adam: "the newsletter run failed, check Actions" and he'll diagnose.