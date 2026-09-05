"""
Monte Carlo gameweek simulation.

The projection gives one number per player. This resamples the whole squad
thousands of times under the actual rules of the game - shared clean sheets,
auto-substitutions, the vice-captain taking over - so the output is a
distribution rather than a point estimate.
"""
import math, random

import fpl_rules as RULES


def _poisson(lam, rnd):
    """Knuth sampler. Every lambda here is small, so this is fine."""
    if lam <= 0:
        return 0
    if lam > 30:
        return int(lam)
    p, k, target = 1.0, 0, math.exp(-lam)
    while True:
        p *= rnd.random()
        if p <= target:
            return k
        k += 1


def _legal(counts, bounds, playing):
    """Does this set of positions make a legal XI?"""
    if counts.get(1, 0) != 1:
        return False
    if sum(counts.values()) != playing:
        return False
    for et in (2, 3, 4):
        b = bounds.get(et, {})
        if not (b.get("min_play", 0) <= counts.get(et, 0) <= b.get("max_play", 11)):
            return False
    return True


def simulate(squad, gws, boot, n=4000, seed=7, captain_of=None, xi_of=None):
    """
    Returns per-gameweek and total point distributions for a 15-man squad.

    squad      list of projected player dicts (needs ["fixt"][gw][leg]["sim"])
    captain_of {gw: player_id}; defaults to the highest projected starter
    xi_of      {gw: [player_ids]}; defaults to the best projected XI
    """
    rnd = random.Random(seed)
    SC = RULES.scoring(boot)
    rules = RULES.squad_rules(boot)
    bounds, playing = rules["bounds"], rules["playing"]
    GOAL, CS, CONC, DCP = SC["goals"], SC["clean_sheet"], SC["conceded"], SC["dc"]

    per_gw = dict((g, []) for g in gws)
    # per-player, per-gameweek samples so the dashboard can show where the
    # points actually come from rather than only the squad total
    pp = dict((p["id"], dict((g, []) for g in gws)) for p in squad)
    pp_tot = dict((p["id"], []) for p in squad)
    totals = []
    cap_returns = dict((g, 0) for g in gws)
    autosubs = 0

    for _ in range(n):
        run_total = 0.0
        for gw in gws:
            starters = [p for p in squad if p["id"] in (xi_of or {}).get(gw, [])] or None
            if starters is None:
                starters, bench = _default_xi(squad, gw, bounds, playing)
            else:
                sids = set(p["id"] for p in starters)
                bench = sorted([p for p in squad if p["id"] not in sids],
                               key=lambda x: -x["gws"].get(gw, 0))

            # one shared conceded draw per club per fixture, so team-mates'
            # clean sheets rise and fall together
            conceded = {}
            for p in squad:
                for i, leg in enumerate(p["fixt"].get(gw) or []):
                    key = (leg["sim"]["team"], gw, i)
                    if key not in conceded:
                        conceded[key] = _poisson(leg["sim"]["xga"], rnd)

            pts, mins = {}, {}
            for p in squad:
                pt, mn = _player_gw(p, gw, conceded, rnd, SC, GOAL, CS, CONC, DCP)
                pts[p["id"]], mins[p["id"]] = pt, mn

            # auto-subs: a starter on zero minutes is replaced by the first
            # bench player who did play, provided the XI stays legal
            active = [p for p in starters if mins[p["id"]] > 0]
            blanks = [p for p in starters if mins[p["id"]] == 0]
            counts = {}
            for p in active:
                counts[p["et"]] = counts.get(p["et"], 0) + 1
            for _b in blanks:
                for sub in bench:
                    if mins[sub["id"]] == 0 or sub in active:
                        continue
                    if _b["et"] == 1 and sub["et"] != 1:
                        continue          # only a keeper replaces a keeper
                    if sub["et"] == 1 and _b["et"] != 1:
                        continue
                    trial = dict(counts)
                    trial[sub["et"]] = trial.get(sub["et"], 0) + 1
                    if _legal(trial, bounds, playing) or sum(trial.values()) < playing:
                        active.append(sub)
                        counts = trial
                        autosubs += 1
                        break

            cap_id = (captain_of or {}).get(gw)
            if cap_id is None and starters:
                cap_id = max(starters, key=lambda x: x["gws"].get(gw, 0))["id"]
            # vice takes the armband if the captain did not appear
            if rules["vice_captain"] and mins.get(cap_id, 0) == 0:
                pool = [p for p in starters if p["id"] != cap_id and mins[p["id"]] > 0]
                if pool:
                    cap_id = max(pool, key=lambda x: x["gws"].get(gw, 0))["id"]

            gw_pts = sum(pts[p["id"]] for p in active)
            if any(p["id"] == cap_id for p in active):
                gw_pts += pts[cap_id]
                if pts[cap_id] >= 6:
                    cap_returns[gw] += 1

            act = set(p["id"] for p in active)
            for p in squad:
                v = pts[p["id"]] if p["id"] in act else 0.0
                if p["id"] == cap_id and p["id"] in act:
                    v *= 2
                pp[p["id"]][gw].append(v)

            per_gw[gw].append(gw_pts)
            run_total += gw_pts
        totals.append(run_total)
    for pid in pp:
        pp_tot[pid] = [sum(pp[pid][g][i] for g in gws) for i in range(n)]

    return {
        "n": n,
        "per_gw": dict((g, _describe(v)) for g, v in per_gw.items()),
        "total": _describe(totals),
        "captain_return_rate": dict((g, cap_returns[g] / n) for g in gws),
        "autosubs_per_run": autosubs / n,
        "samples": totals,
        "players": dict(
            (pid, {"gw": dict((g, _describe(pp[pid][g])) for g in gws),
                   "total": _describe(pp_tot[pid])})
            for pid in pp),
    }


def _default_xi(squad, gw, bounds, playing):
    by = {}
    for p in squad:
        by.setdefault(p["et"], []).append(p)
    for k in by:
        by[k].sort(key=lambda x: -x["gws"].get(gw, 0))
    best = None
    for nd in range(bounds[2]["min_play"], bounds[2]["max_play"] + 1):
        for nm in range(bounds[3]["min_play"], bounds[3]["max_play"] + 1):
            nf = playing - 1 - nd - nm
            if not (bounds[4]["min_play"] <= nf <= bounds[4]["max_play"]):
                continue
            if len(by.get(2, [])) < nd or len(by.get(3, [])) < nm or len(by.get(4, [])) < nf:
                continue
            xi = by[1][:1] + by[2][:nd] + by[3][:nm] + by[4][:nf]
            tot = sum(p["gws"].get(gw, 0) for p in xi)
            if best is None or tot > best[1]:
                best = (xi, tot)
    xi = best[0] if best else []
    ids = set(p["id"] for p in xi)
    bench = sorted([p for p in squad if p["id"] not in ids],
                   key=lambda x: -x["gws"].get(gw, 0))
    return xi, bench


def _player_gw(p, gw, conceded, rnd, SC, GOAL, CS, CONC, DCP):
    """One player's points and minutes for one gameweek."""
    legs = p["fixt"].get(gw) or []
    if not legs:
        return 0.0, 0
    et = p["et"]
    total, played = 0.0, 0
    for i, leg in enumerate(legs):
        s = leg["sim"]
        # minutes: started and saw it out, started and came off, or did not play
        r = rnd.random()
        if r > p["p_start"]:
            continue
        long_game = rnd.random() < 0.88
        played += 1
        total += SC["appearance_long"] if long_game else SC["appearance_short"]

        total += _poisson(s["lam_g"], rnd) * GOAL[et]
        total += _poisson(s["lam_a"], rnd) * SC["assist"]

        gc = conceded.get((s["team"], gw, i), 0)
        if long_game and gc == 0:
            total += CS[et]
        if CONC[et]:
            total += CONC[et] * (gc // SC["conceded_per_point"])
        if et == 1:
            total += _poisson(s["saves_mu"], rnd) // SC["saves_per_point"] * SC["save"]
        if DCP[et] and rnd.random() < s["p_dc"]:
            total += DCP[et]
        if rnd.random() < s["yc"]:
            total += SC["yellow"]
        if rnd.random() < s["rc"]:
            total += SC["red"]
        # Bonus arrives in whole points. A 1/2/3 draw averages 2, so firing it
        # with probability mu/2 makes the expectation come out at mu.
        mu = s["bonus_mu"]
        if rnd.random() < min(mu / 2.0, 0.95):
            total += rnd.choice([1, 2, 3]) * SC["bonus"]
    return total, played


def _describe(vals):
    v = sorted(vals)
    n = len(v)
    if not n:
        return {}
    def q(f):
        return v[min(n - 1, int(f * n))]
    mean = sum(v) / n
    return {
        "mean": round(mean, 1), "median": round(q(0.5), 1),
        "p10": round(q(0.10), 1), "p25": round(q(0.25), 1),
        "p75": round(q(0.75), 1), "p90": round(q(0.90), 1),
        "min": round(v[0], 1), "max": round(v[-1], 1),
        "sd": round((sum((x - mean) ** 2 for x in v) / n) ** 0.5, 1),
    }


def beat_probability(a_samples, b_samples):
    """P(squad A outscores squad B), pairing the runs by index."""
    n = min(len(a_samples), len(b_samples))
    if not n:
        return 0.0
    return sum(1 for i in range(n) if a_samples[i] > b_samples[i]) / n
