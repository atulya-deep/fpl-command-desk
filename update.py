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


def main():
    args = sys.argv[1:]
    offline = "--offline" in args
    cfg = load_cfg()

    boot, fixt = M.load(refresh=not offline)
    cur, nxt = M.current_gw(boot)
    if "--gw" in args:
        nxt = int(args[args.index("--gw") + 1])
    gws = list(range(nxt, min(nxt + HORIZON, 39)))

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
    dbl, _ = A.double_transfer(squad, pool, gws, bank, shortlist=5)
    sval = sum(p["price"] for p in squad)
    wc, wcval = A.build_squad(pool, gws, sval + bank)

    dead = [p for p in squad if p["avail"] <= 0.05]
    broken = [p for p in squad if p["total"] < 16.0]

    # ---- decide the headline recommendation
    wc_gain = wcval - base
    if cfg.get("chips", {}).get("wildcard1_used"):
        wc_gain = -1
    if wc_gain > 35 and len(broken) >= 5:
        mode = "wildcard"
    elif dbl and dbl["gain"] - (0 if ft >= 2 else A.HIT) > max((s["gain"] for s in singles), default=0):
        mode = "double"
    else:
        mode = "single"

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
    elif mode == "double":
        call = "Two transfers: %s and %s out." % (dbl["moves"][0]["out"]["name"], dbl["moves"][1]["out"]["name"])
        body = ["Together they add %.0f points across the window%s." %
                (dbl["gain"], "" if ft >= 2 else ", or %.0f after the 4-point hit" % (dbl["gain"] - 4))]
    else:
        call = "One transfer: %s → %s." % (top["out"]["name"], top["in"]["name"]) if top else "Hold your transfer."
        body = ["Worth about %.0f points over the window." % top["gain"]] if top else \
               ["No single move clears the noise this week. Bank the transfer."]

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
        src = dbl["moves"] if mode == "double" else singles[:3]
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
            "title": "Recommended transfers" if mode == "double" else "Best single moves, ranked",
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
        dbl["squad"] if mode == "double" and dbl else
        [singles[0]["in"] if p["id"] == singles[0]["out"]["id"] else p for p in squad]
        if singles else squad)
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
