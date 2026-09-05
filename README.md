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

## The weekly run

A Windows scheduled task named **FPL Weekly Refresh** is already registered and
runs every Wednesday at 09:00. It calls `refresh.cmd /quiet`, which updates the
data and rewrites `dashboard.html` without opening a browser window.

```powershell
schtasks /query  /tn "FPL Weekly Refresh" /fo LIST   # check it
schtasks /run    /tn "FPL Weekly Refresh"            # run it now
schtasks /delete /tn "FPL Weekly Refresh" /f         # remove it
```

To recreate it from scratch (PowerShell — note the path is quoted as a single
argument, with no backslash escaping):

```powershell
schtasks /create /tn "FPL Weekly Refresh" /tr "C:\Users\Abcom\Downloads\FPL\refresh.cmd /quiet" /sc weekly /d WED /st 09:00 /f
```

If the machine is asleep at 09:00 the task is skipped rather than queued; just
double-click `refresh.cmd` when you next sit down.

After each refresh, `refresh.cmd` calls `publish.cmd`, which commits and pushes
the rebuilt page. Until an `origin` remote exists it skips that step quietly, so
the weekly task works whether or not GitHub is set up.

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

## Connect your live squad

Put your FPL team id in `config.json` and the squad, bank and team value sync
themselves on every run — no more hand-editing.

```json
{ "team_id": 1234567 }
```

Your id is the number in the URL when you view your own team on the FPL site:
`fantasy.premierleague.com/entry/<THIS NUMBER>/event/3`.

Also keep `chips` current — setting `"wildcard1_used": true` stops the model
recommending a chip you have already spent.

## Files

| File | Role |
| --- | --- |
| `fpl_model.py` | Team ratings, fixture model, per-player point projections |
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

### Known limits

- Rotation is inferred from starts to date, so it lags a manager's change of mind.
- The wildcard optimiser maximises the model's own numbers and will therefore
  overstate its edge. Read its **shape** as the recommendation, not its exact XV.
- Set-piece and penalty duties are not modelled explicitly; they show up only
  through realised expected goals.
