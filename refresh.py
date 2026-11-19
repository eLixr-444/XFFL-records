# XFFL Record Book Bible - data refresh
# Downloads every season of ESPN league 35342021 (public league API) and builds the
# three data files the record book page reads: out/games.json, out/seasons.json, out/champions.json.
# Run:  python refresh.py
# Completed seasons are cached in cache/ so they are not downloaded again.
import json, os, sys, time, datetime, urllib.request, urllib.error

LEAGUE = 35342021
FIRST_SEASON = 2020
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{y}/segments/0/leagues/%d" % LEAGUE
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def fetch(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2)


def season_done(d):
    return any(t.get("rankCalculatedFinal", 0) > 0 for t in d["teams"])


def load_season(y):
    path = os.path.join(CACHE, f"season_{y}.json")
    if os.path.exists(path):
        return json.load(open(path))
    d = fetch(BASE.format(y=y) + "?view=mTeam&view=mMatchup&view=mSettings")
    if d is None:
        return None
    if season_done(d):
        json.dump(d, open(path, "w"))
    return d


def load_bench(y, d):
    """Bench points per team per regular-season week, from weekly box scores."""
    path = os.path.join(CACHE, f"bench_{y}.json")
    if os.path.exists(path):
        return json.load(open(path))
    reg = d["settings"]["scheduleSettings"]["matchupPeriodCount"]
    decided = [m["matchupPeriodId"] for m in d["schedule"] if m.get("winner") not in (None, "UNDECIDED") and m["matchupPeriodId"] <= reg]
    last = max(decided) if decided else 0
    out = {}
    for w in range(1, last + 1):
        b = fetch(BASE.format(y=y) + f"?view=mBoxscore&scoringPeriodId={w}")
        for m in b["schedule"]:
            if m["matchupPeriodId"] != w:
                continue
            for s in ("home", "away"):
                if s not in m:
                    continue
                e = (m[s].get("rosterForCurrentScoringPeriod") or {}).get("entries", [])
                out[f"{w}-{m[s]['teamId']}"] = round(sum(x["playerPoolEntry"]["appliedStatTotal"] for x in e if x["lineupSlotId"] == 20), 2)
        time.sleep(0.3)
    if season_done(d):
        json.dump(out, open(path, "w"))
    return out


def nm(m):
    return " ".join(w.capitalize() if w.islower() else w for w in (m.get("firstName", "") + " " + m.get("lastName", "")).split())


def main():
    this_year = datetime.date.today().year
    S, B, names = {}, {}, {}
    for y in range(FIRST_SEASON, this_year + 1):
        d = load_season(y)
        if d is None or not d.get("schedule"):
            continue
        S[y] = d
        B[y] = load_bench(y, d)
        for m in d.get("members", []):
            names[m["id"]] = nm(m)
    if not S:
        sys.exit("No seasons downloaded - is ESPN reachable and the league still public?")

    games, seasons, champs = [], [], []
    current, current_week = None, 0
    for y, d in S.items():
        ss = d["settings"]["scheduleSettings"]
        reg, pt = ss["matchupPeriodCount"], ss["playoffTeamCount"]
        done = season_done(d)
        tm = {t["id"]: t for t in d["teams"]}
        own = {t["id"]: names.get(t["owners"][0], t["owners"][0]) for t in d["teams"]}
        lastp = max(m["matchupPeriodId"] for m in d["schedule"])
        bench = B[y]
        gl = []
        for m in d["schedule"]:
            if "away" not in m or m.get("winner") in (None, "UNDECIDED"):
                continue
            h, a, p = m["home"], m["away"], m["matchupPeriodId"]
            if p <= reg:
                kind = "Regular season"
            elif tm[h["teamId"]]["playoffSeed"] <= pt and tm[a["teamId"]]["playoffSeed"] <= pt:
                kind = "Playoffs"
            else:
                continue
            if done and kind == "Playoffs" and p == lastp and {tm[h["teamId"]]["rankCalculatedFinal"], tm[a["teamId"]]["rankCalculatedFinal"]} == {1, 2}:
                kind = "Championship"
            g = dict(id=f"{y}-w{p}-{m['id']}", season=y, week=p, kind=kind,
                     home=own[h["teamId"]], home_team=tm[h["teamId"]]["name"].strip(), home_score=round(h["totalPoints"], 2),
                     away=own[a["teamId"]], away_team=tm[a["teamId"]]["name"].strip(), away_score=round(a["totalPoints"], 2),
                     home_bench=bench.get(f"{p}-{h['teamId']}") if p <= reg else None,
                     away_bench=bench.get(f"{p}-{a['teamId']}") if p <= reg else None)
            games.append(g)
            gl.append(g)
        if not done:
            current = y
            current_week = max([g["week"] for g in gl] or [0])
        # expected wins: all-play record each regular-season week
        exp, weeks = {}, {}
        for g in gl:
            if g["kind"] == "Regular season":
                weeks.setdefault(g["week"], []).extend([(g["home"], g["home_score"]), (g["away"], g["away_score"])])
        for sc in weeks.values():
            for o, s in sc:
                exp[o] = exp.get(o, 0) + sum(1 if s > s2 else .5 if s == s2 else 0 for o2, s2 in sc if o2 != o) / (len(sc) - 1)
        for t in d["teams"]:
            r, o, tc = t["record"]["overall"], own[t["id"]], t.get("transactionCounter", {})
            gp = r["wins"] + r["losses"] + r["ties"]
            seasons.append(dict(
                id=f"{y}-{o}", season=y, status="Complete" if done else "In progress", manager=o, team=t["name"].strip(),
                wins=r["wins"], losses=r["losses"], ties=r["ties"], points_for=round(r["pointsFor"], 2), points_against=round(r["pointsAgainst"], 2),
                seed=t["playoffSeed"], made_playoffs=bool(done and t["playoffSeed"] <= pt), finish=t["rankCalculatedFinal"] if done else None,
                expected_wins=round(exp.get(o, 0), 2), bench_points=round(sum(bench.get(f"{w}-{t['id']}", 0) for w in range(1, reg + 1)), 2),
                games=gp, avg_score=round(r["pointsFor"] / max(1, gp), 2),
                trades=tc.get("trades", 0), acquisitions=tc.get("acquisitions", 0), drops=tc.get("drops", 0),
                add_drops=tc.get("acquisitions", 0) + tc.get("drops", 0)))
        if done:
            rk = {t["rankCalculatedFinal"]: t for t in d["teams"]}
            top = max(d["teams"], key=lambda t: t["record"]["overall"]["pointsFor"])
            s1 = [t for t in d["teams"] if t["playoffSeed"] == 1][0]
            champs.append(dict(
                season=y, champion=own[rk[1]["id"]], champion_team=rk[1]["name"].strip(),
                champion_record=f"{rk[1]['record']['overall']['wins']}-{rk[1]['record']['overall']['losses']}",
                runner_up=own[rk[2]["id"]], third_place=own[rk[3]["id"]], top_seed=own[s1["id"]],
                most_points=own[top["id"]], most_points_total=round(top["record"]["overall"]["pointsFor"], 2), playoff_teams=pt))

    pulled = datetime.date.today().isoformat()
    status = f"{current} season through Week {current_week}" if current else "all seasons complete"
    meta = [
        {"label": "Source", "value": f"ESPN Fantasy Football league {LEAGUE}, public league API, seasons {min(S)}-{max(S)}"},
        {"label": "Pulled", "value": f"{pulled}, {status}"},
        {"label": "refresh.py", "value": open(os.path.abspath(__file__)).read(), "type": "code", "lang": "python"},
    ]
    for n, rows in (("games", games), ("seasons", seasons), ("champions", champs)):
        json.dump({"rows": rows, "meta": meta}, open(os.path.join(OUT, n + ".json"), "w"), separators=(",", ":"))
    summary = {"pulled": pulled, "status": status, "games": len(games), "seasons": len(seasons), "champions": len(champs)}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
