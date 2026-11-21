"""Builds assets/stats.svg from your real GitHub data (no third-party service).

Needs one environment variable:
  STATS_TOKEN  a classic personal access token with the read:user scope
Optional:
  GH_LOGIN     your username (default: BeniSpec)

ACTIVITY GRADE (my own scale, printed on the card so everyone can see it):
  based on your total contributions (commits, pull requests, issues, reviews)
  in the last 12 months. Edit the numbers below to change the scale.
"""
import datetime
import html
import json
import math
import os
import urllib.request

LOGIN = os.environ.get("GH_LOGIN", "BeniSpec")

# (grade, minimum contributions in the last 12 months), highest first
GRADES = [("A+", 1500), ("A", 1000), ("B+", 750), ("B", 500), ("C+", 300), ("C", 150), ("D", 0)]

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount primaryLanguage { name color } }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


def fetch(token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]["user"]


def grade_for(total):
    """Return (grade, progress 0..1 toward the next grade)."""
    for i, (g, minimum) in enumerate(GRADES):
        if total >= minimum:
            if i == 0:
                return g, 1.0
            nxt = GRADES[i - 1][1]
            return g, min(1.0, max(0.0, (total - minimum) / (nxt - minimum)))
    return GRADES[-1][0], 0.0


def summarise(u):
    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    active = sum(1 for d in days if d["contributionCount"] > 0)
    repos = u["repositories"]["nodes"]
    langs = {}
    for r in repos:
        pl = r["primaryLanguage"]
        if pl:
            name, color = pl["name"], pl["color"] or "#a855f7"
            langs.setdefault(name, [0, color])[0] += 1
    ranked = sorted(langs.items(), key=lambda kv: -kv[1][0])
    total_langs = sum(v[0] for _, v in ranked) or 1
    top = [(n, v[0], v[1]) for n, v in ranked[:4]]
    other = total_langs - sum(c for _, c, _ in top)
    if other > 0:
        top.append(("Other", other, "#6b5b95"))
    total = cc["contributionCalendar"]["totalContributions"]
    grade, progress = grade_for(total)
    return {
        "total": total,
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "active": active,
        "stars": sum(r["stargazerCount"] for r in repos),
        "langs": top,
        "lang_total": total_langs,
        "grade": grade,
        "progress": progress,
    }


def fmt(n):
    return f"{n:,}"


def build_svg(s, updated):
    esc = html.escape
    rows = [
        ("Total Stars Earned", s["stars"]),
        ("Contributions (12 mo)", s["total"]),
        ("Commits (12 mo)", s["commits"]),
        ("Pull Requests (12 mo)", s["prs"]),
        ("Issues (12 mo)", s["issues"]),
        ("Active Days (12 mo)", s["active"]),
    ]
    stat_rows = "\n  ".join(
        f'<text class="k" x="40" y="{96 + i * 27}">{k}</text>'
        f'<text class="v" x="290" y="{96 + i * 27}" text-anchor="end">{fmt(v)}</text>'
        for i, (k, v) in enumerate(rows)
    )

    r = 48
    circ = 2 * math.pi * r
    offset = circ * (1 - max(0.04, s["progress"]))

    scale = "  ·  ".join(
        f"{g} {fmt(m)}" for g, m in GRADES[:5]
    )

    # languages: stacked bar + legend
    bar_x, bar_w = 578, 284
    segs, legend, x = [], [], bar_x
    for i, (name, count, color) in enumerate(s["langs"]):
        w = bar_w * count / s["lang_total"]
        segs.append(f'<rect x="{x:.1f}" y="92" width="{w:.1f}" height="10" fill="{esc(color)}"/>')
        x += w
        pct = round(100 * count / s["lang_total"])
        y = 140 + i * 26
        legend.append(
            f'<circle cx="586" cy="{y-4}" r="5" fill="{esc(color)}"/>'
            f'<text class="k" x="602" y="{y}">{esc(name)}</text>'
            f'<text class="v" x="862" y="{y}" text-anchor="end">{pct}%</text>'
        )
    segs_svg = "\n    ".join(segs)
    legend_svg = "\n  ".join(legend)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300" role="img" aria-label="GitHub stats for {esc(LOGIN)}: activity grade {esc(s["grade"])}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a855f7"/><stop offset="1" stop-color="#ec4899"/></linearGradient>
    <clipPath id="bar"><rect x="{bar_x}" y="92" width="{bar_w}" height="10" rx="5"/></clipPath>
  </defs>
  <style>
    text{{font-family:'JetBrains Mono','Fira Code',Consolas,'Courier New',monospace}}
    .title{{fill:#c084fc;font-size:17px;font-weight:700}}
    .k{{fill:#d8ccf5;font-size:13px}}
    .v{{fill:#f0ecff;font-size:13px;font-weight:700}}
    .grade{{fill:#f0ecff;font-size:40px;font-weight:800}}
    .cap{{fill:#9d8fc0;font-size:10px;letter-spacing:1.5px}}
    .scale{{fill:#9d8fc0;font-size:10px}}
    .ring{{stroke-dasharray:{circ:.1f};stroke-dashoffset:{offset:.1f};animation:draw 1.6s ease-out}}
    @keyframes draw{{from{{stroke-dashoffset:{circ:.1f}}}}}
  </style>

  <!-- left card -->
  <rect x="18" y="18" width="520" height="264" rx="12" fill="#0b0a12" stroke="#2e2845"/>
  <text class="title" x="40" y="54">Benat Siraj Ahmed's GitHub Stats</text>
  {stat_rows}
  <circle cx="440" cy="130" r="{r}" fill="none" stroke="#2e2845" stroke-width="8"/>
  <circle class="ring" cx="440" cy="130" r="{r}" fill="none" stroke="url(#g)" stroke-width="8" stroke-linecap="round" transform="rotate(-90 440 130)"/>
  <text class="grade" x="440" y="144" text-anchor="middle">{esc(s["grade"])}</text>
  <text class="cap" x="440" y="202" text-anchor="middle">ACTIVITY GRADE</text>
  <line x1="40" y1="246" x2="516" y2="246" stroke="#2e2845"/>
  <text class="scale" x="40" y="266">Scale (contributions/yr): {scale}</text>

  <!-- right card -->
  <rect x="558" y="18" width="324" height="264" rx="12" fill="#0b0a12" stroke="#2e2845"/>
  <text class="title" x="578" y="54">Most Used Languages</text>
  <text class="scale" x="578" y="76">by repositories</text>
  <g clip-path="url(#bar)">
    {segs_svg}
  </g>
  {legend_svg}
</svg>
'''


def main():
    token = os.environ["STATS_TOKEN"]
    s = summarise(fetch(token))
    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs("assets", exist_ok=True)
    with open("assets/stats.svg", "w", encoding="utf-8") as f:
        f.write(build_svg(s, updated))
    print("Wrote assets/stats.svg:", s["total"], "contributions, grade", s["grade"])


if __name__ == "__main__":
    main()