"""
Weekly refresh. Pulls live FPL data, reprojects the next five gameweeks,
re-runs the transfer search and rewrites dashboard.html.

    py update.py                 # refresh from live API
    py update.py --offline       # reuse the cached download
    py update.py --gw 7          # force the starting gameweek
"""
import json, os, shutil, sys, datetime, io

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import fpl_model as M
import fpl_analyse as A
import fpl_dashboard as D
import fpl_sim as SIM
import fpl_rules as RULES

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "config.json")
HIST = os.path.join(HERE, "history")
HORIZON = 5
SIM_RUNS = 3000


def load_cfg():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)


def save_cfg(cfg):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


SYNCED = {"ok": False}


def resolve_squad(cfg, byid, gw):
    """Prefer the live squad from the FPL API; fall back to the manual list."""
    tid = cfg.get("team_id")
    if tid:
        try:
            ent, picks = M.entry_squad(tid, gw)
            ids = [p["element"] for p in picks["picks"]]
            bank = picks["entry_history"]["bank"] / 10.0
            cfg["bank"] = bank
            cfg["squad"] = ids
            cfg["manager"] = ent.get("name") or cfg.get("manager")
            save_cfg(cfg)
            SYNCED["ok"] = True
            print("  synced squad from FPL team %s (bank £%.1f)" % (tid, bank))
        except Exception as ex:
            print("  ! could not sync team %s (%s); using saved squad" % (tid, ex))
    return [byid[i] for i in cfg["squad"] if i in byid]


def heat_values(p, lavg):
    """Diverging scale per gameweek: >0 favourable, <0 hostile."""
    out = {}
    for gw, legs in p["fixt"].items():
        if not legs:
            out[gw] = (0.0, 0.0)
            continue
        xgf = sum(l["xgf"] for l in legs)
        xga = sum(l["xga"] for l in legs)
        out[gw] = (max(-1.0, min(1.0, (xgf - lavg) / 1.15)),
                   max(-1.0, min(1.0, (lavg - xga) / 1.05)))
    return out


def status_html(p):
    if p["avail"] <= 0.05:
        return '<span class="pill out">Out</span>'
    if p["avail"] < 1.0 or p["news"]:
        return '<span class="pill warn">Doubt</span>'
    if p["p_start"] < 0.6:
        return '<span class="pill warn">Rotation</span>'
    return '<span class="pill ok">Fit</span>'


SCORING_JS = None


def export_payload(squad, pool, gws, cfg, synced, bank, ft):
    """
    Everything the in-browser simulator needs. The FPL API sends no CORS
    header, so the page cannot fetch it directly - we ship the parameters
    with the page instead and resample them client-side.
    """
    def pack(p):
        g = {}
        for gw in gws:
            legs = p["fixt"].get(gw) or []
            g[str(gw)] = [{
                "tm": l["sim"]["team"], "opp": l["opp"], "h": 1 if l["home"] else 0,
                "lg": round(l["sim"]["lam_g"], 4), "la": round(l["sim"]["lam_a"], 4),
                "xga": round(l["sim"]["xga"], 3), "pdc": round(l["sim"]["p_dc"], 4),
                "sv": round(l["sim"]["saves_mu"], 3), "bo": round(l["sim"]["bonus_mu"], 3),
                "yc": round(l["sim"]["yc"], 4), "rc": round(l["sim"]["rc"], 5),
            } for l in legs]
        return {
            "n": p["name"], "t": p["team_short"], "pos": p["pos"], "et": p["et"],
            "pr": p["price"], "sel": p["sel"], "ps": round(p["p_start"], 4),
            "ep": round(p["total"], 1), "pen": p["pen_order"] or 0,
            "st": p["status"], "gw": g,
        }

    sq_ids = [p["id"] for p in squad]
    # squad plus a deep enough bench of alternatives to make swaps meaningful
    extra = [p for p in sorted(pool, key=lambda x: -x["total"])
             if p["id"] not in sq_ids and p["avail"] > 0.5 and p["n_fix"] > 0][:140]
    players = {}
    for p in squad + extra:
        players[str(p["id"])] = pack(p)
    return {
        "gws": gws, "squad": sq_ids, "players": players, "scoring": SCORING_JS,
        "bank": bank, "ft": ft,
        "provenance": {
            "squad": "synced" if synced else "assumed",
            "team_id": cfg.get("team_id"),
            "chips": cfg.get("chips", {}),
        },
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    args = sys.argv[1:]
    offline = "--offline" in args
    cfg = load_cfg()

    boot, fixt = M.load(refresh=not offline)
    cur, nxt = M.current_gw(boot)
    if "--gw" in args:
        nxt = int(args[args.index("--gw") + 1])
    gws = list(range(nxt, min(nxt + HORIZON, 39)))

    global SCORING_JS
    _sc = RULES.scoring(boot)
    SCORING_JS = {
        "long": _sc["appearance_long"], "short": _sc["appearance_short"],
        "goals": _sc["goals"], "cs": _sc["clean_sheet"], "conc": _sc["conceded"],
        "dc": _sc["dc"], "assist": _sc["assist"], "save": _sc["save"],
        "bonus": _sc["bonus"], "yellow": _sc["yellow"], "red": _sc["red"],
    }

    print("Projecting GW%d-%d ..." % (gws[0], gws[-1]))
    pool, R, lavg, fx = M.project(boot, fixt, gws[0], gws[-1])
    byid = {p["id"]: p for p in pool}

    squad = resolve_squad(cfg, byid, cur)
    bank = float(cfg.get("bank", 0.0))
    ft = int(cfg.get("free_transfers", 1))

    for p in pool:
        p["heat"] = heat_values(p, lavg)
        p["status_html"] = status_html(p)

    rep = A.squad_report(squad, gws)
    base = sum(r["total"] for r in rep)
    singles, _ = A.single_transfers(squad, pool, gws, bank, limit=6)
    sval = sum(p["price"] for p in squad)
    wc, wcval = A.build_squad(pool, gws, sval + bank)

    dead = [p for p in squad if p["avail"] <= 0.05]
    broken = [p for p in squad if p["total"] < 16.0]

    # ---- decide the headline recommendation
    #
    # Free transfers accumulate to five, so the real question is never
    # "wildcard or nothing" - it is whether the wildcard beats what the banked
    # free transfers already buy. A chip is only worth burning for a wide
    # margin, because it stays useful right up to GW19.
    ftplan = A.multi_transfer(squad, pool, gws, bank, max(ft, 1))
    wc_gain = wcval - base
    wc_used = bool(cfg.get("chips", {}).get("wildcard1_used"))
    wc_edge = wc_gain - ftplan["gain"]
    if not wc_used and wc_edge > 35 and len(broken) >= 5:
        mode = "wildcard"
    elif ftplan["moves"] and ftplan["gain"] > 3:
        mode = "transfers"
    else:
        mode = "hold"

    # ---- verdict copy
    top = singles[0] if singles else None
    if mode == "wildcard":
        call = "Play the first Wildcard now."
        body = [
            "The model rates a rebuilt squad %.0f points higher than the current one across GW%d&ndash;%d. "
            "That gap is not one bad pick &mdash; it is %d of your 15 slots projecting under 16 points for the "
            "window, including %s."
            % (wc_gain, gws[0], gws[-1], len(broken),
               ", ".join(p["name"] for p in broken[:4])),
            "Fixing that with weekly transfers costs roughly %d gameweeks and up to %d points in hits. "
            "The Wildcard does it in one move, and it expires at GW19, so spending it on a six-slot repair "
            "is what the chip is for." % (len(broken), (len(broken) - 1) * 4),
        ]
    elif mode == "transfers":
        n = len(ftplan["moves"])
        call = ("Use %d of your %d free transfers. Keep the Wildcard." % (n, ft)
                if ft > 1 else
                "One transfer: %s → %s." % (ftplan["moves"][0]["out"]["name"],
                                            ftplan["moves"][0]["in"]["name"]))
        body = [
            "They cost nothing and add about <b>%.0f points</b> across GW%d&ndash;%d: %s."
            % (ftplan["gain"], gws[0], gws[-1],
               ", ".join("%s &rarr; %s" % (m["out"]["name"], m["in"]["name"])
                         for m in ftplan["moves"])),
        ]
        if not wc_used:
            body.append(
                "A full Wildcard rebuild is worth %.0f over the same window, so the chip buys only "
                "<b>%.0f more points</b> than the free moves you already have banked. That is not "
                "enough to spend a chip which stays available until GW19 &mdash; hold it for an "
                "injury pile-up, a fixture swing or a double gameweek, and keep banking a transfer "
                "a week in the meantime." % (wc_gain, wc_edge))
    else:
        call = "Hold. Bank the transfer."
        body = ["Nothing on the board clears the noise this week, and you have %d free transfer%s "
                "banked for when something does." % (ft, "" if ft == 1 else "s")]

    if dead:
        body.append("Non-negotiable either way: <b>%s</b> %s dead weight &mdash; %s."
                    % (", ".join(p["name"] for p in dead),
                       "are" if len(dead) > 1 else "is",
                       dead[0]["news"] or "unavailable"))

    # ---- week cards
    weeks = []
    for r in rep:
        cap = r["captain"]
        legs = cap["fixt"].get(r["gw"]) or []
        cf = ", ".join("%s (%s)" % (l["opp"], "H" if l["home"] else "A") for l in legs) or "blank"
        alts = sorted(r["xi"], key=lambda p: -p["gws"][r["gw"]])[1:4]
        weeks.append({
            "gw": r["gw"], "cap": cap["name"], "cap_fix": cf,
            "rows": [("Projected XI", "%.0f pts" % r["total"]),
                     ("Formation", "%d-%d-%d" % r["formation"])] +
                    [("Alt: " + a["name"], "%.1f" % a["gws"][r["gw"]]) for a in alts],
        })

    # ---- fixture ticker
    ticker = []
    for row in A.fixture_ticker(R, fx, gws, lavg):
        cells = []
        for c in row["cells"]:
            if not c:
                cells.append({"legs": 0, "opp": "", "sub": "", "att": 0, "def": 0})
            else:
                xgf = sum(x["xgf"] for x in c)
                xga = sum(x["xga"] for x in c)
                cells.append({
                    "legs": len(c),
                    "opp": "/".join(x["opp"] for x in c),
                    "sub": "%s · %.1f" % ("".join("H" if x["home"] else "A" for x in c), xgf),
                    "att": max(-1.0, min(1.0, (xgf - lavg) / 1.15)),
                    "def": max(-1.0, min(1.0, (lavg - xga) / 1.05)),
                })
        row["cells"] = cells
        ticker.append(row)

    # ---- plan ledger
    if mode == "wildcard":
        keep = set(p["id"] for p in squad)
        moves = []
        outs = sorted([p for p in squad if p["id"] not in set(x["id"] for x in wc)],
                      key=lambda p: p["total"])
        ins = sorted([p for p in wc if p["id"] not in keep], key=lambda p: -p["total"])
        for o, i in zip(outs, ins):
            moves.append({
                "out": o["name"], "out_tm": o["team_short"],
                "out_sub": "£%.1f · %.0f pts projected" % (o["price"], o["total"]),
                "in": i["name"], "in_tm": i["team_short"],
                "in_sub": "£%.1f · %.0f pts projected" % (i["price"], i["total"]),
                "gain": "%+.0f" % (i["total"] - o["total"]),
            })
        plan = {
            "title": "Wildcard draft — %d changes" % len(moves),
            "sub": "Spends £%.1f of £%.1f. Keeps %s." % (
                sum(p["price"] for p in wc), sval + bank,
                ", ".join(p["name"] for p in wc if p["id"] in keep) or "nobody"),
            "moves": moves,
            "footnote": "This is a draft, not a lock. The optimiser slightly overfits its own projections, so "
                        "treat the shape &mdash; a heavy Arsenal defence, a premium mid, cheap enablers &mdash; as "
                        "the instruction, and swap individuals you have a strong read on.",
        }
    else:
        src = ftplan["moves"] if mode == "transfers" else singles[:3]
        moves = []
        for m in src:
            moves.append({
                "out": m["out"]["name"], "out_tm": m["out"]["team_short"],
                "out_sub": "£%.1f · %.0f pts projected" % (m["out"]["price"], m["out"]["total"]),
                "in": m["in"]["name"], "in_tm": m["in"]["team_short"],
                "in_sub": "£%.1f · %.0f pts projected" % (m["in"]["price"], m["in"]["total"]),
                "gain": "%+.0f" % m["gain"],
            })
        plan = {
            "title": "Recommended transfers" if mode == "transfers" else "Best single moves, ranked",
            "sub": "Gain is expected points across GW%d&ndash;%d, after re-picking the XI each week."
                   % (gws[0], gws[-1]),
            "moves": moves,
            "footnote": None,
        }

    watch = []
    for p in sorted(pool, key=lambda x: -x["sel"]):
        if p["news"] and (p["sel"] > 3 or p["id"] in set(s["id"] for s in squad)):
            watch.append({"name": p["name"], "team_short": p["team_short"],
                          "news": p["news"], "pill": p["status_html"]})
        if len(watch) >= 14:
            break

    # ---- week-over-week delta
    os.makedirs(HIST, exist_ok=True)
    snap = os.path.join(HIST, "gw%02d.json" % gws[0])
    prev_val = None
    older = sorted(f for f in os.listdir(HIST) if f.endswith(".json") and f != os.path.basename(snap))
    if older:
        try:
            with open(os.path.join(HIST, older[-1]), encoding="utf-8") as f:
                prev_val = json.load(f).get("projection")
        except Exception:
            pass
    with open(snap, "w", encoding="utf-8") as f:
        json.dump({"gw": gws[0], "projection": round(base, 1),
                   "squad": [p["id"] for p in squad], "value": round(sval, 1),
                   "generated": datetime.datetime.now().isoformat(timespec="seconds")}, f, indent=2)

    delta = "" if prev_val is None else " (%+.0f vs last run)" % (base - prev_val)

    # ---- Monte Carlo: the squad as it stands vs the recommended squad
    print("Simulating %d seasons ..." % SIM_RUNS)
    plan_squad = wc if mode == "wildcard" else (
        ftplan["squad"] if mode == "transfers" else squad)
    sim_now = SIM.simulate(squad, gws, boot, n=SIM_RUNS)
    sim_plan = SIM.simulate(plan_squad, gws, boot, n=SIM_RUNS, seed=7)
    p_better = SIM.beat_probability(sim_plan["samples"], sim_now["samples"])

    lo = min(sim_now["per_gw"][g]["p10"] for g in gws) - 4
    hi = max(sim_plan["per_gw"][g]["p90"] for g in gws) + 4
    rows = []
    for g in gws:
        d = sim_now["per_gw"][g]
        rows.append({"label": "GW%d" % g, "d": d,
                     "extra": " ±%.0f" % d["sd"]})
    sim_ctx = {
        "title": "Weekly simulation",
        "sub": "%s runs of the full squad under the real rules &mdash; shared clean sheets, "
               "auto-substitutions and the vice-captain taking over." % "{:,}".format(SIM_RUNS),
        "rows": rows, "lo": lo, "hi": hi,
        "note": (
            "Across five gameweeks the current squad lands between <b>%.0f and %.0f points</b> "
            "eight times out of ten, with a median of <b>%.0f</b>. The recommended squad "
            "medians <b>%.0f</b> and outscores the current one in <b>%.0f%%</b> of paired runs. "
            "The captain returns six or more in %.0f&ndash;%.0f%% of weeks. Auto-substitutions "
            "rescue %.1f blanks per five gameweeks, which is why the bench still matters."
            % (sim_now["total"]["p10"], sim_now["total"]["p90"], sim_now["total"]["median"],
               sim_plan["total"]["median"], p_better * 100,
               min(sim_now["captain_return_rate"].values()) * 100,
               max(sim_now["captain_return_rate"].values()) * 100,
               sim_now["autosubs_per_run"])),
    }

    # ---- per-player simulation table
    prole = {}
    for r in rep:
        for p_ in r["xi"]:
            prole[p_["id"]] = prole.get(p_["id"], 0) + 1
    cap_counts = {}
    for r in rep:
        cap_counts[r["captain"]["id"]] = cap_counts.get(r["captain"]["id"], 0) + 1

    prows = []
    for p_ in squad:
        d = sim_now["players"][p_["id"]]
        starts = prole.get(p_["id"], 0)
        if cap_counts.get(p_["id"]):
            role = '<span class="pill ok">Captain &times;%d</span>' % cap_counts[p_["id"]]
        elif p_["avail"] <= 0.05:
            role = '<span class="pill out">Out</span>'
        elif starts >= 4:
            role = '<span class="pill ok">Starter</span>'
        elif starts == 0:
            role = '<span class="pill warn">Bench</span>'
        else:
            role = '<span class="pill warn">Rotates in %d/%d</span>' % (starts, len(gws))
        prows.append({
            "name": p_["name"], "team": p_["team_short"], "pos": p_["pos"],
            "price": p_["price"], "duty": D.duty(p_),
            "gw": dict((g, d["gw"][g]) for g in gws), "total": d["total"],
            "per_m": d["total"]["median"] / p_["price"] if p_["price"] else 0.0,
            "role": role, "et": p_["et"],
        })
    prows.sort(key=lambda r: (r["et"], -r["total"]["median"]))
    cell_max = max((r["gw"][g]["p90"] for r in prows for g in gws), default=1) or 1
    best_v = max(prows, key=lambda r: r["per_m"])
    worst_v = min([r for r in prows if r["total"]["median"] > 0] or prows, key=lambda r: r["per_m"])
    player_sim = {
        "rows": prows, "cell_max": cell_max,
        "note": (
            "A hatched cell means the player is on your bench that week and only scores if an "
            "auto-substitution brings him on. <b>%s</b> returns the most per million (%.1f points "
            "per &pound;m across the window); <b>%s</b> the least (%.1f). Price is the constraint "
            "that makes this a squad problem rather than a shopping list &mdash; every pound tied "
            "up in a low-yield slot is a pound not spent on a premium."
            % (best_v["name"], best_v["per_m"], worst_v["name"], worst_v["per_m"])),
    }

    # ---- value against price, faceted by position
    mine = set(p_["id"] for p_ in squad)
    panels = []
    for et, label in ((1, "Goalkeepers"), (2, "Defenders"), (3, "Midfielders"), (4, "Forwards")):
        cand = [p_ for p_ in pool
                if p_["et"] == et and p_["n_fix"] > 0 and (p_["avail"] > 0.5 or p_["id"] in mine)
                and (p_["mins"] > 45 or p_["id"] in mine)]
        cand.sort(key=lambda x: -x["total"])
        keep = cand[:48] + [p_ for p_ in squad if p_["et"] == et]
        seen, rows_ = set(), []
        for p_ in keep:
            if p_["id"] in seen:
                continue
            seen.add(p_["id"])
            rows_.append({"id": p_["id"], "name": p_["name"], "price": p_["price"],
                          "total": p_["total"]})
        panels.append({"title": label, "rows": rows_})
    value_facets = {
        "panels": panels, "mine": mine,
        "note": (
            "Up and to the left is what you want: points without spending for them. A player sitting "
            "low and to the right is the argument for a transfer &mdash; you are paying premium money "
            "for a mid-table return, and that budget moves. Position matters because the scales "
            "differ: a &pound;5.0m defender returning 25 is doing a different job from a &pound;15.5m "
            "forward returning 29."),
    }

    dl = next((e["deadline_time"] for e in boot["events"] if e["id"] == gws[0]), "")
    dl_txt = dl.replace("T", " ")[:16] + " UTC" if dl else "-"

    ctx = {
        "title": cfg.get("dashboard_title", "FPL Command Desk"),
        "season": "2026/27",
        "headline": "%s — GW%d to GW%d" % (cfg.get("manager", "Squad"), gws[0], gws[-1]),
        "header_meta": [
            ("GW%d deadline" % gws[0], dl_txt),
            ("Squad value", "£%.1f" % sval),
            ("In the bank", "£%.1f" % bank),
            ("Updated", datetime.datetime.now().strftime("%d %b %Y, %H:%M")),
        ],
        "gws": gws,
        "sim": sim_ctx,
        "player_sim": player_sim,
        "live_kpis": [
            ("liveHead", "%.0f" % sim_now["total"]["median"],
             "median over GW%d&ndash;%d" % (gws[0], gws[-1])),
            ("liveRange", "%.0f&ndash;%.0f" % (sim_now["total"]["p10"], sim_now["total"]["p90"]),
             "80%% of {:,} runs".format(SIM_RUNS)),
            ("liveCap", "%.0f&ndash;%.0f%%" % (min(sim_now["captain_return_rate"].values()) * 100,
                                               max(sim_now["captain_return_rate"].values()) * 100),
             "captain returns 6+"),
            ("liveSubs", "%.1f" % sim_now["autosubs_per_run"], "auto-subs per five weeks"),
        ],
        "value_facets": value_facets,
        "payload": export_payload(squad, pool, gws, cfg, SYNCED["ok"], bank, ft),
        "live_js": open(os.path.join(HERE, "live_sim.js"), encoding="utf-8").read(),
        "provenance": {
            "synced": SYNCED["ok"],
            "text": (
                ("Squad, bank and team value are <b>synced live</b> from FPL team "
                 "%s, so this page reflects the team you actually own." % cfg.get("team_id"))
                if SYNCED["ok"] else
                ("<b>This squad is assumed, not synced.</b> It was entered by hand and has not been "
                 "checked against your real team, and the bank (&pound;%.1f), free transfers (%d) "
                 "and chip status are assumptions too &mdash; so any of them can be wrong, and every "
                 "transfer recommendation below inherits that. Put your FPL team id in "
                 "<code>config.json</code> and all four sync themselves on the next refresh."
                 % (bank, ft))
            ),
        },
        "verdict": {"call": call, "body": body},
        "kpis": [
            ("Simulated GW%d-%d" % (gws[0], gws[-1]), "%.0f" % sim_now["total"]["median"],
             "median of %s runs%s" % ("{:,}".format(SIM_RUNS), delta)),
            ("Realistic range", "%.0f-%.0f" % (sim_now["total"]["p10"], sim_now["total"]["p90"]),
             "80%% of simulated outcomes"),
            ("Wildcard ceiling", "%.0f" % wcval, "%+.0f if fully rebuilt" % wc_gain),
            ("Slots underperforming", "%d" % len(broken), "of 15 projecting under 16 pts"),
        ],
        "squad": sorted(squad, key=lambda p: (p["et"], -p["total"])),
        "weeks": weeks,
        "plan": plan,
        "ticker": ticker,
        "targets": A.top_targets(pool, gws, per_pos=8),
        "diffs": A.differentials(pool, gws, max_sel=8.0, n=10),
        "watch": watch,
        "method": (
            "Team attack and defence ratings come from this season&rsquo;s expected goals, shrunk toward a "
            "squad-market-value prior &mdash; after only %d rounds the raw numbers are far too noisy to trust "
            "on their own. Those ratings feed a Poisson fixture model that produces expected goals for and "
            "against in every remaining fixture, which in turn drives clean-sheet odds, attacking returns "
            "(scaled by each player&rsquo;s expected goal involvement per 90, itself shrunk toward a "
            "price-and-position baseline), defensive-contribution points, save points and bonus. "
            "Nominated penalty, corner and free-kick takers carry an explicit uplift &mdash; badged "
            "<b>PEN</b>, <b>CO</b> and <b>FK</b> below. "
            "Availability is taken live from the official feed. Re-run <code>py update.py</code> after each "
            "deadline and this page rewrites itself." % max(R[1]["gp"], 1)),
    }

    out = os.path.join(HERE, "dashboard.html")
    D.render(ctx, out)
    # GitHub Pages serves index.html from the repo root
    shutil.copyfile(out, os.path.join(HERE, "index.html"))
    print("  mode: %s | base %.0f | wildcard %.0f (%+.0f)" % (mode, base, wcval, wc_gain))
    print("  wrote %s" % out)
    return out


if __name__ == "__main__":
    main()
