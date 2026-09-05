"""
FPL projection engine.

Builds team attack/defence ratings from live FPL data (shrunk toward a
market-value prior, because the season is only a few games old), converts those
into per-fixture expected goals, and projects FPL points per player per
gameweek.
"""
import json, math, os, sys, urllib.request

API = "https://fantasy.premierleague.com/api"
HDRS = {"User-Agent": "Mozilla/5.0"}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---------- tunables ----------
PRIOR_K      = 5.0    # games of prior weight applied to team ratings
PRIOR_SPREAD = 0.28   # how far market value moves a team rating
HFA          = 1.12   # home advantage multiplier
RATE_PRIOR_M = 200.0  # minutes of prior weight on player rate stats
GOAL_PTS     = {1: 10, 2: 6, 3: 5, 4: 4}
CS_PTS       = {1: 4, 2: 4, 3: 1, 4: 0}
DC_THRESH    = {1: 99, 2: 10, 3: 12, 4: 12}   # defensive contribution threshold
POS          = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def fetch(name, url, refresh=True):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if refresh or not os.path.exists(path):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode("utf-8")
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
        except Exception as ex:
            if not os.path.exists(path):
                raise
            print("  ! fetch %s failed (%s); using cache" % (name, ex), file=sys.stderr)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(refresh=True):
    boot = fetch("bootstrap.json", API + "/bootstrap-static/", refresh)
    fixt = fetch("fixtures.json", API + "/fixtures/", refresh)
    return boot, fixt


def entry_squad(team_id, gw):
    """Live picks, bank and free transfers for an FPL team id."""
    ent = fetch("entry_%s.json" % team_id, "%s/entry/%s/" % (API, team_id), True)
    picks = fetch("picks_%s.json" % team_id,
                  "%s/entry/%s/event/%s/picks/" % (API, team_id, gw), True)
    return ent, picks


def current_gw(boot):
    cur = nxt = None
    for ev in boot["events"]:
        if ev["is_current"]:
            cur = ev["id"]
        if ev["is_next"]:
            nxt = ev["id"]
    if cur is None:
        cur = (nxt - 1) if nxt else 1
    return cur, (nxt or cur + 1)


# ---------------------------------------------------------------- team ratings
def team_ratings(boot, fixt):
    teams = {t["id"]: t for t in boot["teams"]}
    gp = dict((i, 0) for i in teams)
    gf = dict((i, 0) for i in teams)
    ga = dict((i, 0) for i in teams)
    for x in fixt:
        if not x["finished"]:
            continue
        h, a = x["team_h"], x["team_a"]
        gp[h] += 1
        gp[a] += 1
        gf[h] += x["team_h_score"]
        ga[h] += x["team_a_score"]
        gf[a] += x["team_a_score"]
        ga[a] += x["team_h_score"]

    lavg = sum(gf.values()) / max(sum(gp.values()), 1)   # goals per team per game
    if lavg <= 0:
        lavg = 1.45

    # team xG = sum of player xG. team xGA is read off the outfielder with the
    # most minutes, because expected_goals_conceded is a team-level stat that
    # accrues while the player is on the pitch.
    txg = dict((i, 0.0) for i in teams)
    anchor = dict((i, None) for i in teams)
    for e in boot["elements"]:
        t = e["team"]
        txg[t] += float(e["expected_goals"])
        if e["element_type"] != 1 and e["minutes"] > 0:
            if anchor[t] is None or e["minutes"] > anchor[t]["minutes"]:
                anchor[t] = e
    txga = {}
    for i in teams:
        p = anchor[i]
        if p and p["minutes"]:
            txga[i] = float(p["expected_goals_conceded"]) * (90.0 * gp[i] / p["minutes"])
        else:
            txga[i] = lavg * gp[i]

    # market-value prior: total price of the 15 most expensive players
    mv = {}
    for i in teams:
        pr = sorted((e["now_cost"] for e in boot["elements"] if e["team"] == i), reverse=True)[:15]
        mv[i] = sum(pr) / 10.0
    vals = list(mv.values())
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0

    R = {}
    for i in teams:
        n = gp[i]
        w = n / (n + PRIOR_K)
        z = (mv[i] - mu) / sd
        obs_att = min(max((txg[i] / n) / lavg, 0.25), 3.0) if n else 1.0
        obs_def = min(max((txga[i] / n) / lavg, 0.25), 3.0) if n else 1.0
        R[i] = {
            "id": i, "name": teams[i]["name"], "short": teams[i]["short_name"],
            "att": obs_att ** w * math.exp(PRIOR_SPREAD * z) ** (1 - w),
            "def": obs_def ** w * math.exp(-PRIOR_SPREAD * z) ** (1 - w),
            "gp": n, "gf": gf[i], "ga": ga[i],
            "xg_pg": (txg[i] / n) if n else lavg,
            "xga_pg": (txga[i] / n) if n else lavg,
            "mv": mv[i], "mz": z,
        }
    return R, lavg


def fixture_xg(R, lavg, home, away):
    """Expected goals for (home team, away team)."""
    xh = lavg * R[home]["att"] * R[away]["def"] * HFA
    xa = lavg * R[away]["att"] * R[home]["def"] / HFA
    return max(xh, 0.15), max(xa, 0.15)


def upcoming(fixt, gw_from, gw_to):
    """{team: {gw: [legs]}} - a list per gw so doubles and blanks both work."""
    out = {}
    for x in fixt:
        ev = x["event"]
        if ev is None or not (gw_from <= ev <= gw_to) or x["finished"]:
            continue
        for t, o, h in ((x["team_h"], x["team_a"], True), (x["team_a"], x["team_h"], False)):
            out.setdefault(t, {}).setdefault(ev, []).append({"opp": o, "home": h})
    return out


# ---------------------------------------------------------- player projections
def pois_ge(lam, k):
    """P(X >= k) for a Poisson with mean lam."""
    if lam <= 0:
        return 0.0
    p, c = math.exp(-lam), 0.0
    for i in range(k):
        c += p
        p *= lam / (i + 1)
    return max(0.0, min(1.0, 1.0 - c))


def price_baseline(boot):
    """Median xGI/90 by position and price band - the shrinkage target."""
    buckets = {}
    for e in boot["elements"]:
        if e["minutes"] >= 90:
            key = (e["element_type"], int(e["now_cost"] // 10))
            buckets.setdefault(key, []).append(float(e["expected_goal_involvements_per_90"]))
    med = {}
    for k, v in buckets.items():
        v.sort()
        med[k] = v[len(v) // 2]
    return med


def project(boot, fixt, gw_from, gw_to):
    R, lavg = team_ratings(boot, fixt)
    fx = upcoming(fixt, gw_from, gw_to)
    base = price_baseline(boot)
    gp = dict((i, R[i]["gp"]) for i in R)

    players = []
    for e in boot["elements"]:
        if e.get("removed"):
            continue
        et, tid = e["element_type"], e["team"]
        mins, tg = e["minutes"], max(gp[tid], 1)

        # availability
        cop = e["chance_of_playing_next_round"]
        avail = 1.0 if cop is None else cop / 100.0
        if e["status"] in ("i", "s", "n", "u"):
            avail = 0.0 if cop is None else cop / 100.0
        elif e["status"] == "d":
            avail = min(avail, 0.75 if cop is None else cop / 100.0)

        p_start = min(e["starts"] / tg, 1.0) * avail
        exp_min = (min(mins / tg, 90.0) * avail) if mins else 0.0
        p60 = p_start * 0.88

        # attacking rate, shrunk toward the price/position baseline
        pri = base.get((et, int(e["now_cost"] // 10)), 0.15)
        xgi = float(e["expected_goal_involvements"])
        xgi90 = (xgi + pri * RATE_PRIOR_M / 90.0) / (mins + RATE_PRIOR_M) * 90.0
        xg, xa = float(e["expected_goals"]), float(e["expected_assists"])
        if (xg + xa) > 0.3:
            gshare = xg / (xg + xa)
        else:
            gshare = {1: 0.0, 2: 0.35, 3: 0.45, 4: 0.70}[et]
        xg90, xa90 = xgi90 * gshare, xgi90 * (1 - gshare)

        # defensive contribution rate
        dcmed = {1: 0.0, 2: 8.0, 3: 6.0, 4: 3.0}[et]
        dc90 = (float(e["defensive_contribution"]) + dcmed * RATE_PRIOR_M / 90.0) / (mins + RATE_PRIOR_M) * 90.0

        bonus90 = (e["bonus"] + 0.12 * RATE_PRIOR_M / 90.0) / (mins + RATE_PRIOR_M) * 90.0
        saves90 = float(e["saves_per_90"]) if (et == 1 and mins) else 0.0
        yc90 = (e["yellow_cards"] / mins * 90.0) if mins else 0.15

        gws, details = {}, {}
        for gw in range(gw_from, gw_to + 1):
            tot = 0.0
            legs = fx.get(tid, {}).get(gw, [])
            leg_info = []
            for leg in legs:
                if leg["home"]:
                    xgf, xga = fixture_xg(R, lavg, tid, leg["opp"])
                else:
                    xga, xgf = fixture_xg(R, lavg, leg["opp"], tid)
                ref = R[tid]["xg_pg"] if R[tid]["gp"] else lavg
                att_mult = min(max(xgf / max(ref, 0.4), 0.55), 1.8)
                mfrac = exp_min / 90.0

                pts = 2 * p60 + 1 * (p_start - p60)                 # appearance
                pts += xg90 * mfrac * att_mult * GOAL_PTS[et]       # goals
                pts += xa90 * mfrac * att_mult * 3                  # assists
                pcs = math.exp(-xga)
                pts += pcs * CS_PTS[et] * p60                       # clean sheet
                if et in (1, 2):
                    pts -= (xga / 2.0) * mfrac * 0.75               # goals conceded
                if et == 1:
                    pts += (saves90 * (xga / max(R[tid]["xga_pg"] or lavg, 0.4)) * mfrac) / 3.0
                if et != 1:
                    pts += 2.0 * pois_ge(dc90 * mfrac, DC_THRESH[et]) * avail
                pts += bonus90 * mfrac
                pts -= yc90 * mfrac * 0.9
                tot += max(pts, 0.0)
                leg_info.append({
                    "opp": R[leg["opp"]]["short"], "home": leg["home"],
                    "xgf": round(xgf, 2), "xga": round(xga, 2), "cs": round(pcs, 3),
                })
            gws[gw] = tot
            details[gw] = leg_info

        players.append({
            "id": e["id"], "name": e["web_name"], "team": tid, "team_short": R[tid]["short"],
            "pos": POS[et], "et": et, "price": e["now_cost"] / 10.0,
            "sel": float(e["selected_by_percent"]), "form": float(e["form"]),
            "pts": e["total_points"], "mins": mins, "status": e["status"], "news": e["news"],
            "avail": avail, "p_start": p_start, "xgi90": xgi90, "dc90": dc90,
            "ep_next": float(e["ep_next"] or 0),
            "gws": gws, "fixt": details, "total": sum(gws.values()),
            "n_fix": sum(len(fx.get(tid, {}).get(g, [])) for g in range(gw_from, gw_to + 1)),
        })
    return players, R, lavg, fx
