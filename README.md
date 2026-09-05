# FPL Command Desk

A projection model and strategy dashboard for Fantasy Premier League 2026/27,
built on the official FPL API.

## Refresh it each week

Double-click `refresh.cmd`, or:

```bash
py update.py
```

It re-downloads live data, reprojects the next five gameweeks, re-runs the
transfer search, and rewrites `dashboard.html`. Run it after each deadline —
ideally the Tuesday or Wednesday before the next one, once injury news has
settled.

| Command | What it does |
| --- | --- |
| `py update.py` | Full refresh from the live API |
| `py update.py --offline` | Re-render from the last download (no network) |
| `py update.py --gw 7` | Force a starting gameweek |

## The weekly run happens in the cloud

`.github/workflows/refresh.yml` runs on GitHub's servers **every six hours**. It
rebuilds the dashboard from live FPL data, commits it, and pushes — which makes
Pages redeploy. Nothing on your machine needs to be switched on.

Six-hourly rather than weekly because prices settle around 01:30 UTC and injury
news lands through the day: a weekly rebuild spent most of its life showing news
that had already moved on.

```powershell
gh workflow run refresh.yml            # trigger a run right now
gh run list --workflow refresh.yml     # see recent runs
gh run view <run-id> --log             # read a run's output
```

You can also hit **Run workflow** on the Actions tab. To change the cadence,
edit the `cron` line — it is always UTC, never local time:

| Cron | Meaning |
| --- | --- |
| `0 */6 * * *` | Every six hours (current) |
| `0 8 * * *` | Once daily, 08:00 UTC |
| `0 8 * * 2,5` | Tuesdays and Fridays only |

GitHub pauses scheduled workflows on a repo with no commits for 60 days. This
one commits most weeks, so it keeps itself alive.

### Running it by hand

`refresh.cmd` still works for an on-demand rebuild. It calls `publish.cmd`,
which rebases onto the remote before pushing, so a manual run cannot collide
with a commit the scheduled workflow already made.

There is deliberately **no Windows scheduled task** any more — two things
pushing to the same branch is a conflict waiting to happen, and the cloud run
does not depend on your laptop being awake.

## Put it on GitHub Pages

The repo is already initialised and committed. Three steps, all of which need
your own GitHub login:

```powershell
winget install --id GitHub.cli -e
```

Restart the terminal so `gh` is on PATH, then:

```powershell
gh auth login
```

```powershell
gh repo create fpl-command-desk --public --source=. --remote=origin --push
```

Then turn Pages on — either in **Settings → Pages → Source: `main`, `/ (root)`**,
or from the CLI:

```powershell
gh api --method POST repos/{owner}/fpl-command-desk/pages -f "source[branch]=main" -f "source[path]=/"
```

The site lands at `https://<your-username>.github.io/fpl-command-desk/`, serving
`index.html` — which `update.py` rewrites alongside `dashboard.html` on every
run. From then on the Wednesday task refreshes the data, commits, and pushes,
and Pages rebuilds within a minute or so. The live site keeps itself current
with no further input.

### Before you make it public

GitHub Pages needs a **public** repo on a free account, and the published page
shows your squad, your manager name and your transfer plan. FPL team names and
ids are already public on the game's own leaderboards, so this leaks nothing new
— but it does mean your weekly strategy is readable by anyone with the link. If
you would rather it stay private, keep using the Claude artifact instead, or put
the repo on a paid plan where Pages can serve from a private repo.

## Your live squad

`config.json` carries team id **7561127**, so squad, bank, team value and
transfers sync from FPL on every run. The banner at the top of the dashboard
turns teal to confirm it, and goes amber if a run ever falls back to the saved
squad.

Keep `chips` current by hand — the API reports chips already played, but not
which you intend to save. Setting `"wildcard1_used": true` stops the model
recommending a chip you have spent.

### Free transfers matter more than they look

Free transfers bank up to five. The recommendation engine works out what those
banked transfers already buy before it will suggest a chip, and only calls for
the Wildcard when it beats the free moves by a wide margin — a chip stays useful
until GW19, so burning one to save four points is a bad trade.

## Files

| File | Role |
| --- | --- |
| `fpl_rules.py` | The game's own scoring table and squad rules, read from the API |
| `fpl_model.py` | Team ratings, fixture model, per-player point projections |
| `fpl_sim.py` | Monte Carlo gameweek simulation (server side) |
| `live_sim.js` | The same simulation, re-run live in the reader's browser |
| `fpl_analyse.py` | Best XI, captaincy, transfer search, wildcard optimiser |
| `fpl_dashboard.py` | HTML rendering |
| `update.py` | Entry point — ties the three together |
| `config.json` | Your squad, bank, free transfers, chip state |
| `history/` | One snapshot per gameweek, used for the week-over-week delta |
| `data/` | Cached API responses |

## How the model works

Team attack and defence ratings come from this season's expected goals, shrunk
toward a squad-market-value prior — after three rounds the raw per-team numbers
are far too noisy to use directly, so early on the prior does most of the work
and observed form takes over as games accumulate.

Those ratings feed a Poisson fixture model producing expected goals for and
against in every remaining fixture. That drives clean-sheet probability, and
attacking returns are scaled by each player's expected goal involvement per 90
(itself shrunk toward a price-and-position baseline). Defensive-contribution
points use a Poisson tail on each player's CBIT-plus-tackles rate against the
10 / 12 thresholds. Save points, bonus, cards and appearance points are
estimated from per-90 rates. Availability comes live from the official feed.

### Rules

Nothing about scoring is hardcoded. FPL publishes its whole scoring table and
squad rules in `bootstrap-static` under `game_config`, and `fpl_rules.py` reads
them on every run: goals by position (keeper 10, defender 6, midfielder 5,
forward 4), clean sheets, goals conceded, assists, saves, penalties saved and
missed, yellow and red cards, own goals, bonus and defensive contribution. Squad
size, the £100.0m budget, the three-per-club cap, the legal formations and the
five-free-transfer ceiling come from the same place. A mid-season rule change
flows through on the next refresh rather than rotting in a constant.

Two things FPL does not publish stay in `fpl_rules.py` as named constants: the
defensive-contribution thresholds (10 for defenders, 12 for everyone else) and
the three-saves-per-point rate.

### Weekly simulation

`fpl_sim.py` resamples the squad 3,000 times per refresh instead of trusting a
single expected value. Each run draws goals and assists from Poisson
distributions, and — importantly — draws **one shared conceded total per club
per fixture**, so team-mates' clean sheets rise and fall together. Three players
from the same defence is a correlated bet, and the spread reflects that.

It then applies the rules a point estimate cannot: **auto-substitutions** (a
starter on zero minutes is replaced by the first bench player who featured,
provided the XI stays legal, keepers only for keepers) and the **vice-captain**
inheriting the armband when the captain does not appear.

The output is a median with a 10th-to-90th-percentile range per gameweek, the
captain's return rate, and the probability that the recommended squad outscores
the current one across paired runs.

### Set-piece duty

The official feed publishes an explicit penalty, corner and free-kick order per
club, and the model uses all three. Penalties are the material one: the league
runs at roughly 0.12 per team per game converting at about 79%, so the nominated
taker carries around 0.095 extra goals per 90, scaled by how threatening the
side is in that particular fixture. The second name on the list gets 20% of that
(they only take them when the first is off the pitch). Corner duty lifts assist
rate by 12% for the first-choice taker; direct free kicks add a small goal term.

The constants live at the top of `fpl_model.py` as `PEN_PER_GAME`, `PEN_CONV`,
`PEN_SHARE`, `CK_XA_BOOST` and `FK_XG90`. Across the whole player pool this
moves the mean projection by less than a tenth of a point — it is a targeted
correction for the ~66 players who actually have duty, not a thumb on the scale.
Players carrying duty are badged **PEN**, **CO** and **FK** on the dashboard.

### Known limits

- Rotation is inferred from starts to date, so it lags a manager's change of mind.
- The wildcard optimiser maximises the model's own numbers and will therefore
  overstate its edge. Read its **shape** as the recommendation, not its exact XV.
- Penalty duty is added as a flat expectation rather than stripped out of each
  player's realised xG first, so a nominated taker who has already scored a
  penalty this season is counted very slightly twice. The shrinkage toward the
  price baseline absorbs most of it, and the constants below are deliberately
  set at the conservative end.
