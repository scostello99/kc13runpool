#!/usr/bin/env python3
"""
KC 13 Run Pool - results builder.

Reads config.json, fetches every MLB game this season where a team scored
exactly 13 runs (from sportsdatabase.com), computes weekly team assignments
and payouts exactly as the original Excel workbook did, and writes data.json
for the website.

Usage:
  python scripts/build.py               # fetch live from SDQL
  python scripts/build.py --from FILE   # use a saved SDQL HTML page or CSV/JSON of rows instead
"""
import argparse, datetime as dt, json, math, re, sys, urllib.request, html as htmllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

SDQL_URL = ("https://sportsdatabase.com/MLB/query.html?sdql="
            "date%2Cteam%2Cruns%40season%3D{season}+and+runs%3D13+and+_t%3E0"
            "&submit=++S+D+Q+L+%21++")


def excel_round(x):
    """Excel ROUND(x,0): half away from zero."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def fetch_sdql_html(season):
    url = SDQL_URL.format(season=season)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KC13RunPool results bot)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def parse_sdql_html(page):
    """Return list of (yyyymmdd:int, team:str, runs:int) from the SDQL result table (id=pyql_id)."""
    m = re.search(r'<table[^>]*id="pyql_id"[^>]*>(.*?)</table>', page, re.S | re.I)
    if not m:
        raise RuntimeError("SDQL result table (pyql_id) not found in page")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S | re.I):
        cells = [htmllib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(cells) >= 3 and re.fullmatch(r"\d{8}", cells[0]) and cells[2].isdigit():
            rows.append((int(cells[0]), cells[1], int(cells[2])))
    return rows


def load_rows_from_file(path):
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    if path.endswith(".json"):
        return [tuple(r) for r in json.loads(text)]
    if path.endswith(".csv"):
        out = []
        for line in text.splitlines()[1:]:
            d, t, r = [x.strip() for x in line.split(",")[:3]]
            out.append((int(d), t, int(r)))
        return out
    return parse_sdql_html(text)


def build(rows):
    season = CFG["season"]
    opening = dt.date.fromisoformat(CFG["opening_date"])
    last = dt.date.fromisoformat(CFG["last_date"])
    pot = CFG["payout_per_week"]
    seed = CFG["rotation_seed"]
    players = CFG["players"]
    teams = CFG["teams"]                       # [abbr, full name, SDQL name]
    n_teams = len(teams)
    sdql_to_abbr = {t[2]: t[0] for t in teams}
    abbr_to_name = {t[0]: t[1] for t in teams}

    # ---- Weeks: week 1 runs from opening date to the following Sunday; then Mon-Sun.
    weeks = []
    start = opening
    end = opening + dt.timedelta(days=(6 - opening.weekday()))   # next Sunday (Mon=0)
    wid = 1
    while start <= last:
        weeks.append({"id": wid, "start": start, "end": end})
        start = end + dt.timedelta(days=1)
        end = start + dt.timedelta(days=6)
        wid += 1

    def week_of(d):
        for w in weeks:
            if w["start"] <= d <= w["end"]:
                return w["id"]
        return None

    # ---- 13-run events
    events = []
    unknown = set()
    for ymd, team, runs in rows:
        if runs != 13:
            continue
        abbr = sdql_to_abbr.get(team)
        if not abbr:
            unknown.add(team)
            continue
        d = dt.date(ymd // 10000, (ymd // 100) % 100, ymd % 100)
        events.append({"date": d, "team": abbr, "week": week_of(d)})
    if unknown:
        print(f"WARNING: SDQL team names not in config: {sorted(unknown)}", file=sys.stderr)
    events.sort(key=lambda e: (e["date"], e["team"]))

    # ---- Weekly winners / carryover / unit payout (same as the Dates sheet)
    carry = 0
    prev_winners = None
    for w in weeks:
        hits = [e for e in events if e["week"] == w["id"]]
        w["winners"] = len(hits)
        w["carryover"] = 0 if (prev_winners is None or prev_winners > 0) else pot + carry
        carry = w["carryover"]
        w["unit"] = 0 if w["winners"] == 0 else (pot + w["carryover"]) / w["winners"]
        w["total"] = w["unit"] * w["winners"]
        w["teams_hit"] = [e["team"] for e in hits]
        prev_winners = w["winners"]

    # ---- Matrix: team per player per week, payout per cell (Excel: ROUND(count*unit,0))
    matrix = []
    for pid, name in enumerate(players, start=1):
        cells = []
        total = 0
        for w in weeks:
            abbr = teams[(pid + w["id"] + seed) % n_teams][0]
            hits = w["teams_hit"].count(abbr)
            won = excel_round(hits * w["unit"]) if hits else 0
            total += won
            cells.append({"team": abbr, "hits": hits, "won": won})
        matrix.append({"player": name, "weeks": cells, "total": total})

    standings = sorted(({"player": m["player"], "total": m["total"]} for m in matrix),
                       key=lambda s: (-s["total"], s["player"].lower()))

    today = dt.date.today()
    current_week = next((w["id"] for w in weeks if w["start"] <= today <= w["end"]), None)
    if today > last:
        current_week = len(weeks)

    return {
        "pool_name": CFG["pool_name"],
        "season": season,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "opening_date": opening.isoformat(),
        "last_date": last.isoformat(),
        "payout_per_week": pot,
        "entry_fee": CFG.get("entry_fee"),
        "player_count": len(players),
        "total_collected": CFG.get("entry_fee", 0) * len(players),
        "total_paid": sum(m["total"] for m in matrix),
        "current_week": current_week,
        "contact_name": CFG.get("contact_name", ""),
        "contact_email": CFG.get("contact_email", ""),
        "social": CFG.get("social", {}),
        "notices": CFG.get("notices", []),
        "team_names": abbr_to_name,
        "weeks": [{"id": w["id"], "start": w["start"].isoformat(), "end": w["end"].isoformat(),
                   "winners": w["winners"], "carryover": w["carryover"],
                   "unit": round(w["unit"], 2), "total": round(w["total"], 2),
                   "teams_hit": w["teams_hit"]} for w in weeks],
        "events": [{"date": e["date"].isoformat(), "team": e["team"], "week": e["week"]} for e in events],
        "matrix": matrix,
        "standings": standings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", help="saved SDQL HTML, CSV or JSON rows instead of live fetch")
    ap.add_argument("--out", default=str(ROOT / "data.json"))
    a = ap.parse_args()

    if a.src:
        rows = load_rows_from_file(a.src)
    else:
        rows = parse_sdql_html(fetch_sdql_html(CFG["season"]))
    if not rows:
        print("ERROR: no 13-run rows found; leaving existing data.json untouched", file=sys.stderr)
        sys.exit(1)

    data = build(rows)
    Path(a.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"OK: {len(rows)} SDQL rows -> {len(data['events'])} events, "
          f"{len(data['weeks'])} weeks, total paid ${data['total_paid']}")


if __name__ == "__main__":
    main()
