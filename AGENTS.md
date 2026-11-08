# Fantasy Fucks

Static site on GitHub Pages, published from the root of `main`. Pages are hand-written HTML, so edits to them are what go live. The exception is the weekly power rankings pages, which are built with `tools/ff.py`: follow `CLAUDE.md` for those. Every file in the repo is publicly reachable, including this one.

Commit or push only when asked. Commit messages are one imperative sentence ending in a period, e.g. `Grade the finished Week Eight games and leave Seattle open for Monday night.`

## George Pick'ems

Everything lives in `george-pickems/index.html`. Copy the markup of existing rows rather than writing new markup; `pickems.js` and `pickems.css` handle the rest.

### Weekly rhythm

Do each step when asked. The days are the usual pattern, not a schedule.

| When | Step |
|---|---|
| After Monday night | Grade the last game, close the week, post the next week's lines unlocked |
| Wednesday | Refresh unlocked lines, lock Thursday's game |
| Friday | Grade Thursday's game, refresh, lock everything else, remove the banner |
| As they come in | Log picks |
| Sunday and Monday | Grade finished games, leave unplayed ones open |

Bump `Updated YYYY-MM-DD` in the page header on every edit.

### Lines

Use DraftKings lines only.

1. Pull them from ESPN, which labels the provider. Confirm `provider.name` is `Draft Kings`:
   `curl -s --compressed 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week=9&seasontype=2&dates=2026'`
   Each event has the line at `competitions[0].odds[0].details` and `.overUnder`.
2. Cross-check against the DraftKings column on [VegasInsider](https://www.vegasinsider.com/nfl/odds/las-vegas/). Cells aren't labeled by book: DraftKings is the 4th column, after Open, bet365 and BetMGM.
3. If the two disagree, or a line moved a lot, find out why (usually a quarterback injury) and tell the user before locking it.

Do not call DraftKings directly. It blocks automated requests, so don't try to get around that.

Once a game is `LOCKED` or `FINAL`, its line never changes, even if DraftKings moves. Only refresh unlocked rows.

### Lines table

- List games in kickoff order, with `Away @ Home`. Add the city for neutral-site games: `Bengals @ Falcons (Madrid)`.
- Show the favorite as `TEAM -N`, and the total as a bare number.
- Show times in Pacific: `Thu 5:15 PM`. Convert from ESPN's UTC, and watch for daylight saving ending in early November.
- While any game is unlocked, keep this banner directly under the heading:
  `<p><span class="result-badge is-warn"><span class="result-badge-pick">NOT LOCKED IN</span></span></p>`

Game cell by status:

```html
<!-- unlocked -->
<td><span class="result-badge open"><span class="result-badge-pick">Jets @ Chiefs</span></span></td>
<!-- locked -->
<td><span class="result-badge cover"><span class="result-badge-pick">Jets @ Chiefs</span><span class="result-badge-score">LOCKED</span></span></td>
<!-- finished -->
<td><span class="result-badge cover"><span class="result-badge-pick">Jets @ Chiefs</span><span class="result-badge-score">FINAL</span></span></td>
```

### Grading

Grade against the locked line, using ESPN's final score. Only grade games ESPN marks `Final`.

Scores are written away team first: `(CHI 34, SEA 17)`. Add `OT` after overtime: `(NYG 27, HOU 21 OT)`.

| Cell | Class | Text |
|---|---|---|
| Lines table, favorite covered | `cover` | `GB -3.5: ✅ Cover` |
| Lines table, favorite failed | `loss` | `CIN -12.5: ❌ Loss` |
| Lines table, over hit | `cover` | `⬆️ Over 46.5` |
| Lines table, under hit | `under` | `⬇️ Under 47.5` |
| Pick won | `cover` | `DET -3: ✅ Cover` or `Under 39.5: ✅ Cover` |
| Pick lost | `loss` | `SEA -3: ❌ Loss` |
| Pick pushed | `push` | `SEA -7: 🤝 Push` |
| Pick not played yet | `open` | `SEA -3`, or `Over 40.5` with `(HOU @ LAC)` below |

A graded cell also carries the score:

```html
<td><span class="result-badge loss"><span class="result-badge-pick">SEA -3: ❌ Loss</span><span class="result-badge-score">(CHI 34, SEA 17)</span></span></td>
```

After grading, update each person's week result and season record, then re-sort the table: most wins, then fewest losses, then alphabetical on ties. Records are `W–L`, with `–T` added only once someone has a push, written with `&ndash;`. Count only graded picks.

### Logging picks

Replace the `&mdash;` cell with an `open` cell such as `SEA -3` or `Over 54.5`, in the order the person gave them.

Over/under picks also name the game below the pick, away team first, until grading replaces it with the score:

```html
<td><span class="result-badge open"><span class="result-badge-pick">Over 40.5</span><span class="result-badge-score">(HOU @ LAC)</span></span></td>
```

Several games can share a total, so take the game from what the person said, not from the number, and ask if they didn't say. Everyone gets two picks a week. Don't re-sort until grading.

### Opening a new week

1. Grade anything left in the old week.
2. Move the old picks table into a collapsed section, newest first, above the previous week's:
   ```html
   <details class="pickems-week">
   <summary>Week Eight Picks</summary>
   <!-- table -->
   </details>
   ```
3. Replace the old lines table with the new week's, including the banner. Old lines tables aren't kept.
4. Add `<h2>Week Nine Picks</h2>` and a new table, with the header `Wk 9 Result`. Sort by season record. Give everyone `&mdash;` for both picks, `0&ndash;0` for the week, and their carried-over record.

### Before finishing

- Add up every person's picks across all weeks and confirm each week result and season record matches the table.
- Check the page in a browser on desktop and phone width.
- Tell the user any line that moved, any game left open, and anything you couldn't verify.
- If something isn't covered here, check `git log -- george-pickems/index.html` for how it was handled before, or ask.
