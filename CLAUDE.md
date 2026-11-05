# Fantasy Fucks site

Static GitHub Pages site (served from `main`). Every page is hand-written HTML with its own copy of the sidebar nav. Python tools in `tools/` (standard library only) own everything that comes from Sleeper.

## Weekly power rankings page

Week N's page (`this-season/power-rankings-week-N/index.html`) recaps week N-1 and ranks teams going into week N.

1. **Start it:** `python3 tools/ff.py new N`. It copies week N-1's page, adds the nav link to every page and the home page card.
2. **Write the human parts:** intro, Matchup of the Week, team write-ups, banner (`assets/weekN-hero.jpg`).
3. **Rank by order:** put the team blocks (`<div id="tony">`, `<div id="kris">`, ...) in ranking order. Don't type rank numbers or arrows.
4. **Build:** `python3 tools/ff.py build N`, once week N-1's games are final. It regenerates the Week N-1 recap, league overview, waivers, trades, every team's stat chips and scoring chart, the team names in the headers, the rank numbers, and the ▲/▼ "Last Week" arrows (from week N-1's page).
5. **Check:** `python3 tools/ff.py check N`. It fails on leftover text or images from last week, `[PLACEHOLDER]` text, broken links, unbalanced HTML, missing nav links, stale Sleeper data, or a week Sleeper hasn't finished scoring.
6. Commit and push.

## Rules

- A hook in `.claude/settings.json` runs build + check automatically before any `git commit` that touches the newest weekly page, and blocks the commit if the check fails. Fix what it reports. Never get around it: no `--no-verify`, no editing `tools/` or the hook just to make it pass, no hand-edited stats.
- Never hand-edit the generated sections: recap, league overview, waivers, trades, stat chips, scoring charts, header team names, rank numbers, arrows. Change the inputs (block order, Sleeper) and rebuild.
- If the page layout changes (restyle, new section), update `tools/ff.py` in the same change and prove it: `build` on the previous week's page should change nothing except data that really changed since it was posted.
- League settings (league id, owner names by Sleeper roster_id, timezone, week-1 Tuesday) are in `tools/league.json`. Update it each new season.
- Plain `git` commits outside Claude Code: run `python3 tools/ff.py setup` once per clone to turn on the same check as a git pre-commit hook.

## George Pick'ems

The weekly pick'ems update is documented in `AGENTS.md`:

@AGENTS.md
