"""Convert the 3 PoC Gemini results into sample posts so we can build the site."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parents[1]
POC_DIR = PROJECT_DIR / "context" / "poc-results-gemini"
POSTS_DIR = PROJECT_DIR / "posts"
POSTS_DIR.mkdir(parents=True, exist_ok=True)

CHANNEL_MAP = {
    "ag589INxdDk": "@TomNashTV",
    "VyDeaRin-hw": "@DrKnowitallKnows",
    "Y0j-7a88BHk": "@SolvingTheMoneyProblem",
}

def yaml_str(s):
    if s is None:
        return ""
    return str(s).replace('"', '\\"').replace("\n", " ").strip()

base_date = datetime.now(timezone.utc) - timedelta(hours=2)
for i, vid in enumerate(["ag589INxdDk", "VyDeaRin-hw", "Y0j-7a88BHk"]):
    src = POC_DIR / f"{vid}.json"
    if not src.exists():
        print(f"missing {src}")
        continue
    d = json.load(open(src, encoding="utf-8"))
    mo = d.get("model_output", {})
    fm = {
        "date": (base_date - timedelta(hours=i)).isoformat(),
        "channel": CHANNEL_MAP[vid],
        "original_title": d.get("original_title", ""),
        "hebrew_title": mo.get("title_he", d.get("original_title", "")),
        "category": mo.get("category", "General"),
        "video_id": vid,
        "video_url": f"https://www.youtube.com/watch?v={vid}",
        "duration_sec": d.get("duration_sec") or 0,
        "transcript_source": d.get("transcript_source") or "manual",
        "was_truncated": bool(d.get("was_truncated")),
        "cost_usd": float(d.get("cost_usd") or 0),
        "status": "ok",
    }
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f'{k}: "{yaml_str(v)}"')
    kp = mo.get("key_points") or []
    if kp:
        lines.append("key_points:")
        for p in kp:
            lines.append(f'  - "{yaml_str(p)}"')
    lines.append("---")
    body = mo.get("summary_he", "")
    if kp:
        body += "\n\n## נקודות עיקריות\n\n"
        for p in kp:
            body += f"- {p}\n"
    out = POSTS_DIR / f"{vid}.md"
    out.write_text("\n".join(lines) + "\n\n" + body + "\n", encoding="utf-8")
    print(f"wrote {out.name} ({len(body)} chars body)")

# Seed costs.json with the PoC totals so the site has a number to display
import json as _j
total = 0.0
for vid in CHANNEL_MAP:
    src = POC_DIR / f"{vid}.json"
    if src.exists():
        d = json.load(open(src, encoding="utf-8"))
        total += float(d.get("cost_usd") or 0)
costs = {
    "entries": [],
    "monthly": {datetime.now(timezone.utc).strftime("%Y-%m"): round(total, 6)},
    "_seed_note": "seeded from PoC; will be overwritten by first real run",
}
costs_path = PROJECT_DIR / "data" / "costs.json"
costs_path.parent.mkdir(parents=True, exist_ok=True)
costs_path.write_text(_j.dumps(costs, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"seeded costs.json total ${total:.6f}")