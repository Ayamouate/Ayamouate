#!/usr/bin/env python3
"""Generate assets/metrics.languages.svg - "Most Used Languages" card.

Self-contained replacement for the lowlighter/metrics languages plugin: it needs no
secret, only the public GitHub API (standard library only, nothing to pip install).

    python scripts/languages.py                       # uses user from --user or git remote
    python scripts/languages.py --user Ayamouate
    python scripts/languages.py --demo                # fake data, offline preview

Optional: set GITHUB_TOKEN to lift the 60 requests/hour anonymous rate limit.
Counts bytes of code per language across your own, non-fork repositories.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "metrics.languages.svg"

COLORS = {
    "C": "#7d8590", "C++": "#f34b7d", "Java": "#e8a13a", "Python": "#3572A5",
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "PHP": "#8892bf",
    "HTML": "#e34c26", "CSS": "#8c52ff", "SCSS": "#c6538c", "Shell": "#89e051",
    "PowerShell": "#2d7bd6", "Batchfile": "#C1F12E", "TeX": "#7aa83a",
    "Makefile": "#6aa84f", "Dockerfile": "#4f8aa3", "Jupyter Notebook": "#DA5B0B",
    "SQL": "#e38c00", "PLpgSQL": "#336790", "Go": "#00ADD8", "Rust": "#dea584",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Vue": "#41b883", "C#": "#9b4f96",
}
FALLBACK = ["#ffb6d9", "#d98eff", "#8c52ff", "#7ee7c7", "#ffd27d", "#7fb7ff", "#ff9d7d", "#b5e48c"]


def api(url: str, token: str | None):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-languages-card",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_totals(user: str, token: str | None, include_forks: bool) -> dict[str, int]:
    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner&page={page}", token)
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    totals: dict[str, int] = {}
    used = 0
    for repo in repos:
        if repo.get("fork") and not include_forks:
            continue
        if repo["name"].lower() == user.lower():      # skip the profile repo itself
            continue
        langs = api(repo["languages_url"], token)
        used += 1
        for name, size in langs.items():
            totals[name] = totals.get(name, 0) + int(size)
    print(f"read {used} repositories, {len(totals)} languages")
    return totals


def render(totals: dict[str, int], limit: int = 8) -> str:
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1
    top = items[:limit]
    rest = sum(v for _, v in items[limit:])
    if rest:
        top.append(("Other", rest))

    W, H, PAD = 480, 215, 28
    bar_w, bar_y, bar_h = W - 2 * PAD, 62, 12
    rows = []

    # stacked bar (clipped to a rounded rectangle)
    x = float(PAD)
    segs = []
    for i, (name, size) in enumerate(top):
        w = bar_w * size / total
        color = COLORS.get(name, FALLBACK[i % len(FALLBACK)]) if name != "Other" else "#6e7681"
        segs.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{max(w, 1.5):.2f}" height="{bar_h}" fill="{color}"/>')
        x += w

    # legend: two columns
    legend = []
    col_w = (W - 2 * PAD) / 2
    for i, (name, size) in enumerate(top):
        col, row = divmod(i, 5) if len(top) > 5 else (0, i)
        if len(top) > 5:
            col, row = (0, i) if i < 5 else (1, i - 5)
        cx = PAD + col * col_w
        cy = 104 + row * 21
        color = COLORS.get(name, FALLBACK[i % len(FALLBACK)]) if name != "Other" else "#6e7681"
        pct = 100 * size / total
        legend.append(
            f'<circle cx="{cx + 5:.1f}" cy="{cy - 4}" r="5" fill="{color}"/>'
            f'<text x="{cx + 17:.1f}" y="{cy}" class="lang">{name}</text>'
            f'<text x="{cx + col_w - 18:.1f}" y="{cy}" class="pct" text-anchor="end">{pct:.1f}%</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t">
<title id="t">Most used languages</title>
<style>
  .bg    {{ fill:#0d1117; stroke:#30363d; }}
  .title {{ font-size:15px; font-weight:700; fill:#d98eff; letter-spacing:.5px; }}
  .sub   {{ font-size:11px; fill:#8b949e; }}
  .lang  {{ font-size:12px; fill:#e6edf3; }}
  .pct   {{ font-size:12px; fill:#8b949e; }}
  text   {{ font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace; }}
  @media (prefers-color-scheme: light) {{
    .bg    {{ fill:#ffffff; stroke:#d0d7de; }}
    .title {{ fill:#8c52ff; }}
    .sub, .pct {{ fill:#656d76; }}
    .lang  {{ fill:#1f2328; }}
  }}
</style>
<defs><clipPath id="bar"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6"/></clipPath></defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" class="bg"/>
<text x="{PAD}" y="34" class="title">MOST USED LANGUAGES</text>
<text x="{PAD}" y="50" class="sub">by bytes of code across public repositories</text>
<g clip-path="url(#bar)">
{chr(10).join(segs)}
</g>
{chr(10).join(legend)}
</svg>
'''


def guess_user() -> str | None:
    import re, subprocess
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                             capture_output=True, text=True).stdout
        m = re.search(r"github\.com[:/]([^/]+)/", url)
        return m.group(1) if m else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="GitHub username (default: from git remote, else Ayamouate)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=8, help="languages to show before 'Other'")
    ap.add_argument("--include-forks", action="store_true")
    ap.add_argument("--demo", action="store_true", help="use fake data (offline preview)")
    args = ap.parse_args()

    if args.demo:
        totals = {"C": 52000, "C++": 21000, "Python": 16000, "JavaScript": 9000, "HTML": 7000,
                  "CSS": 4000, "PHP": 3000, "Java": 2500, "Shell": 1500}
    else:
        user = args.user or guess_user() or "Ayamouate"
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        try:
            totals = fetch_totals(user, token, args.include_forks)
        except urllib.error.HTTPError as e:
            msg = "rate limit reached - set GITHUB_TOKEN and retry" if e.code in (403, 429) else f"HTTP {e.code}"
            print(f"GitHub API error: {msg}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"Network error: {e.reason}", file=sys.stderr)
            return 1
        if not totals:
            print("No language data found (no public non-fork repos with code yet).", file=sys.stderr)
            return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(totals, args.limit), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())