"""
Squad evaluation, best-XI selection, captaincy and transfer search,
built on top of the projections in fpl_model.
"""
import itertools
import fpl_model as M

FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1), (5, 3, 2), (5, 4, 1), (5, 2, 3), (3, 3, 4)]
HIT = 4.0


def best_xi(squad, gw):
    """Highest-projecting legal XI for one gameweek. Returns (xi, bench, total)."""
    by = {p: [] for p in ("GK", "DEF", "MID", "FWD")}
    for pl in squad:
        by[pl["pos"]].append(pl)
    for k in by:
        by[k].sort(key=lambda x: -x["gws"].get(gw, 0))
    if not by["GK"]:
        return [], [], 0.0
    best = None
    for d, m, f in FORMATIONS:
        if len(by["DEF"]) < d or len(by["MID"]) < m or len(by["FWD"]) < f:
            continue
        xi = [by["GK"][0]] + by["DEF"][:d] + by["MID"][:m] + by["FWD"][:f]
        tot = sum(p["gws"].get(gw, 0) for p in xi)
        if best is None or tot > best[2]:
            ids = set(p["id"] for p in xi)
            bench = [p for p in squad if p["id"] not in ids]
            bench.sort(key=lambda x: -x["gws"].get(gw, 0))
            best = (xi, bench, tot, (d, m, f))
    return best if best else ([], [], 0.0, None)


def squad_report(squad, gws):
    """Per-gameweek XI, captain and expected total for the whole horizon."""
    out = []
    for gw in gws:
        xi, bench, tot, form = best_xi(squad, gw)
        cap = max(xi, key=lambda p: p["gws"].get(gw, 0)) if xi else None
        vice = sorted(xi, key=lambda p: -p["gws"].get(gw, 0))[1] if len(xi) > 1 else None
        out.append({
            "gw": gw, "xi": xi, "bench": bench, "formation": form,
            "base": tot, "captain": cap, "vice": vice,
            "total": tot + (cap["gws"].get(gw, 0) if cap else 0),
        })
    return out


def _club_counts(squad):
    c = {}
    for p in squad:
        c[p["team"]] = c.get(p["team"], 0) + 1
    return c


def horizon_value(squad, gws):
    """Expected points over the horizon, counting captaincy."""
    return sum(r["total"] for r in squad_report(squad, gws))


def single_transfers(squad, pool, gws, bank, limit=6):
    """Rank every legal one-for-one swap by gain in expected points."""
    base = horizon_value(squad, gws)
    counts = _club_counts(squad)
    owned = set(p["id"] for p in squad)
    results = []
    for out_p in squad:
        budget = out_p["price"] + bank
        cands = [c for c in pool
                 if c["et"] == out_p["et"] and c["id"] not in owned
                 and c["price"] <= budget + 1e-9 and c["avail"] > 0.25
                 and c["total"] > out_p["total"]]
        cands.sort(key=lambda c: -c["total"])
        for c in cands[:40]:
            if c["team"] != out_p["team"] and counts.get(c["team"], 0) >= 3:
                continue
            new = [c if p["id"] == out_p["id"] else p for p in squad]
            gain = horizon_value(new, gws) - base
            results.append({
                "out": out_p, "in": c, "gain": gain,
                "bank_after": round(bank + out_p["price"] - c["price"], 1),
            })
    results.sort(key=lambda r: -r["gain"])
    # keep the best option per outgoing player so the list is not one player repeated
    seen, top = set(), []
    for r in results:
        if r["out"]["id"] in seen:
            continue
        seen.add(r["out"]["id"])
        top.append(r)
        if len(top) >= limit:
            break
    return top, base


def double_transfer(squad, pool, gws, bank, shortlist=5):
    """Best pair of transfers, searched over the strongest single moves."""
    singles, base = single_transfers(squad, pool, gws, bank, limit=shortlist)
    best = None
    for a in singles:
        sq2 = [a["in"] if p["id"] == a["out"]["id"] else p for p in squad]
        b_bank = bank + a["out"]["price"] - a["in"]["price"]
        seconds, _ = single_transfers(sq2, pool, gws, b_bank, limit=shortlist)
        for b in seconds:
            if b["in"]["id"] == a["in"]["id"]:
                continue
            sq3 = [b["in"] if p["id"] == b["out"]["id"] else p for p in sq2]
            gain = horizon_value(sq3, gws) - base
            if best is None or gain > best["gain"]:
                best = {"moves": [a, b], "gain": gain, "squad": sq3,
                        "bank_after": round(b_bank + b["out"]["price"] - b["in"]["price"], 1)}
    return best, base


def top_targets(pool, gws, per_pos=8, max_price=None):
    out = {}
    for pos in ("GK", "DEF", "MID", "FWD"):
        c = [p for p in pool if p["pos"] == pos and p["avail"] > 0.5 and p["mins"] > 0]
        if max_price:
            c = [p for p in c if p["price"] <= max_price]
        c.sort(key=lambda p: -p["total"])
        out[pos] = c[:per_pos]
    return out


def differentials(pool, gws, max_sel=8.0, min_total=15.0, n=12):
    c = [p for p in pool if p["sel"] <= max_sel and p["total"] >= min_total and p["avail"] > 0.6]
    c.sort(key=lambda p: -p["total"])
    return c[:n]


def value_picks(pool, n=12):
    c = [p for p in pool if p["avail"] > 0.6 and p["mins"] > 60 and p["price"] <= 6.0]
    c.sort(key=lambda p: -(p["total"] / p["price"]))
    return c[:n]


def fixture_ticker(R, fx, gws, lavg):
    """Per-team attacking and defensive ease over the horizon."""
    rows = []
    for tid, r in R.items():
        cells, att_sum, def_sum, n = [], 0.0, 0.0, 0
        for gw in gws:
            legs = fx.get(tid, {}).get(gw, [])
            cell = []
            for leg in legs:
                if leg["home"]:
                    xgf, xga = M.fixture_xg(R, lavg, tid, leg["opp"])
                else:
                    xga, xgf = M.fixture_xg(R, lavg, leg["opp"], tid)
                cell.append({
                    "opp": R[leg["opp"]]["short"], "home": leg["home"],
                    "xgf": round(xgf, 2), "xga": round(xga, 2),
                })
                att_sum += xgf
                def_sum += xga
                n += 1
            cells.append(cell)
        rows.append({
            "team": r["short"], "name": r["name"], "cells": cells,
            "att_score": att_sum / max(n, 1), "def_score": def_sum / max(n, 1),
            "n_fix": n, "att": r["att"], "def": r["def"],
        })
    rows.sort(key=lambda x: -x["att_score"])
    return rows


# ------------------------------------------------------------------ wildcard
def build_squad(pool, gws, budget, must_keep=(), seed=None):
    """
    Greedy build then local-search swaps, maximising expected points over the
    horizon (horizon_value already picks the best XI and captain each week).
    """
    need = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    cands = [p for p in pool if p["avail"] > 0.5 and (p["mins"] > 0 or p["price"] >= 5.0)]
    cands.sort(key=lambda p: -p["total"])

    squad = list(must_keep)
    counts = _club_counts(squad)
    have = {k: 0 for k in need}
    for p in squad:
        have[p["pos"]] += 1
    spent = sum(p["price"] for p in squad)
    ids = set(p["id"] for p in squad)

    # greedy on points-per-million, leaving room for the cheapest remaining slots
    floor = {}
    for pos in need:
        cheap = sorted((p["price"] for p in cands if p["pos"] == pos))
        floor[pos] = cheap[0] if cheap else 4.0

    order = sorted(cands, key=lambda p: -(p["total"] / p["price"]))
    for p in order:
        pos = p["pos"]
        if have[pos] >= need[pos] or p["id"] in ids:
            continue
        if counts.get(p["team"], 0) >= 3:
            continue
        remaining = sum((need[q] - have[q]) * floor[q] for q in need) - floor[pos]
        if spent + p["price"] + remaining > budget:
            continue
        squad.append(p); ids.add(p["id"]); have[pos] += 1
        counts[p["team"]] = counts.get(p["team"], 0) + 1
        spent += p["price"]

    for pos in need:  # fill any gaps with the cheapest legal option
        while have[pos] < need[pos]:
            for p in sorted(cands, key=lambda x: x["price"]):
                if p["pos"] != pos or p["id"] in ids or counts.get(p["team"], 0) >= 3:
                    continue
                if spent + p["price"] > budget:
                    continue
                squad.append(p); ids.add(p["id"]); have[pos] += 1
                counts[p["team"]] = counts.get(p["team"], 0) + 1
                spent += p["price"]
                break
            else:
                break

    keep_ids = set(p["id"] for p in must_keep)
    best_val = horizon_value(squad, gws)
    for _ in range(6):
        improved = False
        for out_p in list(squad):
            if out_p["id"] in keep_ids:
                continue
            cur_spent = sum(p["price"] for p in squad)
            room = budget - cur_spent + out_p["price"]
            others = [p for p in squad if p["id"] != out_p["id"]]
            oc = _club_counts(others)
            for c in cands:
                if c["pos"] != out_p["pos"] or c["id"] in set(p["id"] for p in squad):
                    continue
                if c["price"] > room or oc.get(c["team"], 0) >= 3:
                    continue
                if c["total"] <= out_p["total"] and c["price"] >= out_p["price"]:
                    continue
                trial = others + [c]
                v = horizon_value(trial, gws)
                if v > best_val + 1e-6:
                    squad, best_val, improved = trial, v, True
                    break
            if improved:
                break
        if not improved:
            break
    return squad, best_val
