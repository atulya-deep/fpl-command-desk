"""
The game's own rules, read from the API rather than hardcoded.

FPL publishes its full scoring table and squad rules in bootstrap-static under
game_config. Reading them means a mid-season rule tweak flows through on the
next refresh instead of silently rotting in a constant.
"""

# element_type id -> the key FPL uses in its scoring table
POS_KEY = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# Used only if an older payload omits game_config entirely.
_FALLBACK = {
    "long_play": 2, "short_play": 1, "assists": 3, "saves": 1, "bonus": 1,
    "penalties_saved": 5, "penalties_missed": -2,
    "yellow_cards": -1, "red_cards": -3, "own_goals": -2,
    "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -1, "DEF": -1, "MID": 0, "FWD": 0},
    "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
}

# Defensive-contribution thresholds are not published, so they stay here.
# Defenders count clearances, blocks, interceptions and tackles; everyone else
# also counts ball recoveries, against a higher bar.
DC_THRESHOLD = {1: 999, 2: 10, 3: 12, 4: 12}

# Saves needed per point, also unpublished.
SAVES_PER_POINT = 3
# Goals conceded per penalty point, likewise.
CONCEDED_PER_POINT = 2


def _by_pos(table, default=0):
    """Turn a {"GKP": x, ...} scoring entry into {element_type: x}."""
    if not isinstance(table, dict):
        return {i: table for i in POS_KEY}
    return {i: table.get(POS_KEY[i], default) for i in POS_KEY}


def scoring(boot):
    """Everything the projection needs, keyed by element_type where relevant."""
    sc = dict(_FALLBACK)
    sc.update((boot.get("game_config") or {}).get("scoring") or {})
    return {
        "appearance_long": sc.get("long_play", 2),
        "appearance_short": sc.get("short_play", 1),
        "goals": _by_pos(sc.get("goals_scored")),
        "clean_sheet": _by_pos(sc.get("clean_sheets")),
        "conceded": _by_pos(sc.get("goals_conceded")),
        "dc": _by_pos(sc.get("defensive_contribution")),
        "assist": sc.get("assists", 3),
        "save": sc.get("saves", 1),
        "bonus": sc.get("bonus", 1),
        "pen_saved": sc.get("penalties_saved", 5),
        "pen_missed": sc.get("penalties_missed", -2),
        "yellow": sc.get("yellow_cards", -1),
        "red": sc.get("red_cards", -3),
        "own_goal": sc.get("own_goals", -2),
        "dc_threshold": DC_THRESHOLD,
        "saves_per_point": SAVES_PER_POINT,
        "conceded_per_point": CONCEDED_PER_POINT,
    }


def squad_rules(boot):
    """Squad size, budget, club cap, formation bounds, transfer rules."""
    r = (boot.get("game_config") or {}).get("rules") or boot.get("game_settings") or {}
    bounds = {}
    for et in boot.get("element_types", []):
        bounds[et["id"]] = {
            "select": et.get("squad_select", 0),
            "min_play": et.get("squad_min_play", 0),
            "max_play": et.get("squad_max_play", 0),
        }
    base_ft = 1
    return {
        "squad_size": r.get("squad_squadsize", 15),
        "playing": r.get("squad_squadplay", 11),
        "club_limit": r.get("squad_team_limit", 3),
        "budget": r.get("squad_total_spend", 1000) / 10.0,
        "bounds": bounds,
        # 1 free transfer a week, banking up to max_extra_free_transfers more
        "max_free_transfers": base_ft + r.get("max_extra_free_transfers", 4),
        "hit_cost": 4,
        # sell for purchase price plus this share of any profit
        "sell_on_fee": r.get("transfers_sell_on_fee", 0.5),
        "sell_at_purchase_price": r.get("element_sell_at_purchase_price", False),
        "vice_captain": r.get("sys_vice_captain_enabled", True),
        "transfers_cap": r.get("transfers_cap", 20),
    }


def formations(boot):
    """Every legal outfield split, derived from the published bounds."""
    b = squad_rules(boot)["bounds"]
    out = []
    d, m, f = b.get(2, {}), b.get(3, {}), b.get(4, {})
    playing = squad_rules(boot)["playing"] - 1   # minus the keeper
    for nd in range(d.get("min_play", 3), d.get("max_play", 5) + 1):
        for nm in range(m.get("min_play", 2), m.get("max_play", 5) + 1):
            nf = playing - nd - nm
            if f.get("min_play", 1) <= nf <= f.get("max_play", 3):
                out.append((nd, nm, nf))
    return out


def selling_price(bought_at, now):
    """
    What you actually get back. Profit is halved and rounded down to 0.1;
    losses are taken in full.
    """
    if now <= bought_at:
        return now
    profit = round((now - bought_at) * 10)      # in 0.1m units
    return bought_at + (profit // 2) / 10.0


def price_change_deadlines(boot):
    return ((boot.get("game_config") or {}).get("settings") or {}).get(
        "price_change_deadlines", [])
