# Newsletter PoC — YouTube → Hebrew Summary

`poc.py` takes a YouTube URL (or runs against 3 default test channels), pulls the English transcript via `youtube-transcript-api`, sends it to Claude Haiku 4.5 with a Hebrew summarization prompt tuned for an Israeli audience, and saves a structured JSON result per video. This is the first slice of the newsletter pipeline — proving the transcript→Hebrew-summary core works before wiring up scheduling, email, or any UI.

## How to run

1. Create `p-projects/eytans-newsletter/.env` with one line:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   # Default — latest video from each of the 3 test channels
   python poc.py

   # Or specify a single video
   python poc.py https://www.youtube.com/watch?v=VIDEO_ID
   ```

## Output

Per-video JSON files land in `poc-results/{video_id}.json`. Each contains the model's Hebrew title, summary, category, key points, plus metadata (channel, original title, was_truncated, token usage, cost in USD).

`poc-results/` is gitignored — it's throwaway test output.

## Cost expectation

Haiku 4.5 pricing: $1/MTok input, $5/MTok output. A typical 30-minute video transcript runs ~10K input tokens + ~500 output tokens → roughly **$0.013 per video** (~1.3 cents). The 3-channel default run costs about 4 cents.

## Default test channels

- `@TomNashTV`
- `@DrKnowitallKnows`
- `@SolvingTheMoneyProblem`

Latest video IDs are auto-detected from each channel's RSS feed at runtime.
