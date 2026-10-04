"""Build profile stat cards (SVG) for the GitHub profile README.

Data comes from the public profile APIs of TryHackMe, Hack The Box and
CyberDefenders. Cards are saved to assets/. If one site fails, its old card
is kept and the others are still updated.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from html import escape

ASSETS = "assets"
THM_USER = os.environ.get("THM_USER", "")
HTB_PROFILE = os.environ.get("HTB_PROFILE", "")
CD_USER = os.environ.get("CD_USER", "")

W, H = 420, 150
BG, MUTED, TEXT, TRACK = "#1d2230", "#9aa4b8", "#ffffff", "#2e3547"


def fetch(url, accept="application/json"):
    """GET with a few retries: some sites rate-limit GitHub runners (HTTP 429)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (profile-badges; github.com/W0nIE)",
        "Accept": accept,
    })
    for delay in (5, 20, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or delay is None:
                raise
            print(f"{url}: HTTP {e.code}, retry in {delay}s")
            time.sleep(delay)


def get_json(url):
    return json.loads(fetch(url))


def card(site, color, user, subtitle, stats, bar_label, bars):
    """stats: 4 x (label, value); bars: up to 3 x (name, percent, right_text)."""
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        f'<rect width="{W}" height="{H}" rx="10" fill="{BG}"/>',
        f'<rect width="5" height="{H}" rx="2.5" fill="{color}"/>',
        f'<text x="18" y="30" font-size="15" font-weight="700" fill="{color}">{site}</text>',
        f'<text x="{W - 18}" y="30" font-size="15" font-weight="700" fill="{TEXT}" '
        f'text-anchor="end">{escape(user)}</text>',
        f'<text x="{W - 18}" y="47" font-size="11" fill="{MUTED}" text-anchor="end" '
        f'letter-spacing="1">{escape(subtitle.upper())}</text>',
    ]
    for i, (label, value) in enumerate(stats):
        x = 18 + i * 100
        p.append(f'<text x="{x}" y="72" font-size="10" fill="{MUTED}">{label}</text>')
        p.append(f'<text x="{x}" y="90" font-size="15" font-weight="700" fill="{TEXT}">{escape(str(value))}</text>')
    p.append(f'<text x="18" y="113" font-size="10" fill="{MUTED}">{bar_label}</text>')
    bw = 120 if len(bars) > 1 else 384
    for i, (name, pct, right) in enumerate(bars):
        x = 18 + i * 133
        pct = max(0, min(100, pct))
        p.append(f'<text x="{x}" y="129" font-size="11" fill="#d5dbe6">{escape(name)}</text>')
        p.append(f'<text x="{x + bw}" y="129" font-size="11" fill="{TEXT}" text-anchor="end">{escape(right)}</text>')
        p.append(f'<rect x="{x}" y="134" width="{bw}" height="5" rx="2.5" fill="{TRACK}"/>')
        p.append(f'<rect x="{x}" y="134" width="{max(2, bw * pct / 100):.0f}" height="5" rx="2.5" fill="{color}"/>')
    p.append("</svg>")
    return "\n".join(p)


def save(name, svg):
    with open(os.path.join(ASSETS, name), "w", encoding="utf-8") as f:
        f.write(svg + "\n")
    print(f"saved {name}")


def tryhackme():
    try:
        d = get_json(f"https://tryhackme.com/api/v2/public-profile?username={THM_USER}")["data"]
    except Exception as e:
        # API blocked for the runner: use TryHackMe's official badge image instead,
        # wrapped in an SVG so the README link stays the same.
        print(f"TryHackMe API failed ({e}), using official badge image")
        png = fetch(f"https://tryhackme-badges.s3.amazonaws.com/{THM_USER}.png", "image/png")
        b64 = base64.b64encode(png).decode()
        save("tryhackme.svg",
             f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
             f'<rect width="{W}" height="{H}" rx="10" fill="{BG}"/>'
             f'<image x="10" y="10" width="{W - 20}" height="{H - 20}" '
             f'preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{b64}"/></svg>')
        return
    top = d.get("topPercentage") or 100
    save("tryhackme.svg", card(
        "TryHackMe", "#88cc14", d["username"], d.get("rank", ""),
        [("Level", d["level"]), ("Points", d["totalPoints"]),
         ("Rooms", d["completedRoomsNumber"]), ("Badges", d["badgesNumber"])],
        "Global ranking",
        [(f"Top {top}% of users", 100 - top, f"best streak {d.get('largestStreak', 0)} d")],
    ))


def hackthebox():
    base = "https://profile.hackthebox.com/api"
    prof = get_json(f"{base}/v1/public/profile/{HTB_PROFILE}")["data"]
    xp = get_json(f"{base}/experience/v1/account/{prof['account_id']}")
    need = xp["levelExperiencePoints"] + xp["experienceUntilNextLevel"]
    save("hackthebox.svg", card(
        "Hack The Box", "#9fef00", prof["name"], f"{xp['levelTitle']} · grade {xp['levelGrade']}",
        [("Level", xp["level"]), ("Total XP", xp["totalExperiencePoints"]),
         ("Rank", xp["levelTitle"]), ("Best streak", f"{xp['streakData'].get('maxStreak', 0)} w")],
        f"Progress to level {xp['level'] + 1}",
        [("Level XP", 100 * xp["levelExperiencePoints"] / need if need else 0,
          f"{xp['levelExperiencePoints']} / {need} XP")],
    ))


def cyberdefenders():
    base = f"https://cyberdefenders.org/api/user/{CD_USER}"
    user = get_json(base + "/")["user"]
    ranks = get_json(base + "/overview/ranks/")["rank"]
    skills = get_json(base + "/overview/skills/")["skills"]
    bloods = get_json(base + "/overview/first-bloods/")["first_bloods"]["count"]
    streak = get_json(base + "/streak/")["streak"]["longest"]

    def last_rank(key):
        vals = [v for v in ranks[key]["data"] if v not in ("-", None)]
        return f"#{vals[-1]}" if vals else "N/A"

    top = sorted(skills.items(), key=lambda kv: kv[1]["accuracy"], reverse=True)[:3]
    save("cyberdefenders.svg", card(
        "CyberDefenders", "#4f8cff", user["username"], user.get("title", ""),
        [("Global rank", last_rank("global")), ("Country rank", last_rank("country")),
         ("First bloods", bloods), ("Best streak", f"{streak} d")],
        "Top accuracy",
        [(name, s["accuracy"], f"{round(s['accuracy'])}%") for name, s in top],
    ))


def main():
    os.makedirs(ASSETS, exist_ok=True)
    jobs = [("TryHackMe", THM_USER, tryhackme), ("Hack The Box", HTB_PROFILE, hackthebox),
            ("CyberDefenders", CD_USER, cyberdefenders)]
    active = [j for j in jobs if j[1]]
    failed = 0
    for name, _, fn in active:
        try:
            fn()
        except Exception as e:  # keep the old card if a site is down
            failed += 1
            print(f"::warning::{name} failed: {e}")
    sys.exit(1 if active and failed == len(active) else 0)


if __name__ == "__main__":
    main()
