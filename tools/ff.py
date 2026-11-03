#!/usr/bin/env python3
"""Fantasy Fucks weekly page tool. Python 3.9+, standard library only.

    python3 tools/ff.py setup          one time per clone: turn on the pre-commit hook
    python3 tools/ff.py new N          start this-season/power-rankings-week-N from week N-1
                                       (page frame, nav link on every page, home card)
    python3 tools/ff.py build N        refresh everything that comes from Sleeper on week N's page:
                                       Week N-1 recap, league overview, waivers, trades, every team's
                                       stat chips + scoring chart, rank numbers and up/down arrows
    python3 tools/ff.py check N        fail (exit 1) if week N's page isn't ready to publish
    python3 tools/ff.py hook           what the pre-commit hook runs (build + check the newest
                                       weekly page when it is part of the commit)

Rankings: put the team blocks (<div id="kris"> ...) in the order you want. `build` numbers them
1..10 in that order and sets "Last Week" + the arrow from week N-1's page. Never hand-edit the
recap, overview, waivers, trades, stat chips, charts, rank numbers or arrows: `build` owns them.
"""
import datetime, html, json, os, re, subprocess, sys, time, urllib.request, zoneinfo
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
CACHE = TOOLS / ".cache"
CFG = json.loads((TOOLS / "league.json").read_text())
TZ = zoneinfo.ZoneInfo(CFG["timezone"])
SHORT = {int(k): v for k, v in CFG["owners"].items()}
SLOT = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "FLEX": "FLEX", "K": "K", "DEF": "DST"}
POSCLS = {"QB": "qb", "RB": "rb", "WR": "wr", "TE": "te", "K": "k", "DEF": "dst"}
WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen"]
E = lambda s: html.escape(s, quote=True)
EQ = lambda s: html.escape(s, quote=False)


def die(msg):
    print(f"ff: {msg}", file=sys.stderr)
    sys.exit(1)


def page_path(n):
    return ROOT / "this-season" / f"power-rankings-week-{n}" / "index.html"


def latest_week():
    weeks = [int(m.group(1)) for p in (ROOT / "this-season").glob("power-rankings-week-*")
             if (m := re.fullmatch(r"power-rankings-week-(\d+)", p.name)) and (p / "index.html").exists()]
    return max(weeks) if weeks else None


def num(x):
    return str(float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))


def cutoff(n):
    """Waivers for week N's page start the Tuesday after week N-1's games (00:00 local)."""
    d = datetime.date.fromisoformat(CFG["week1_tuesday"]) + datetime.timedelta(days=7 * (n - 1))
    return datetime.datetime.combine(d, datetime.time(), TZ)


# ---- Sleeper data --------------------------------------------------------------------------
class Sleeper:
    def __init__(self, upto_week, tx_weeks):
        CACHE.mkdir(exist_ok=True)
        base = f"https://api.sleeper.app/v1/league/{CFG['league_id']}"
        self.league = self._get(base, "league.json")
        self.users = {u["user_id"]: u for u in self._get(f"{base}/users", "users.json")}
        self.rosters = {r["roster_id"]: r for r in self._get(f"{base}/rosters", "rosters.json")}
        self.weeks = {w: self._get(f"{base}/matchups/{w}", f"m{w}.json") for w in range(1, upto_week + 1)}
        self.tx = [t for w in range(1, tx_weeks + 1) for t in self._get(f"{base}/transactions/{w}", f"tx{w}.json")
                   if t["status"] == "complete"]
        self.players = self._get("https://api.sleeper.app/v1/players/nfl", "players.json", max_age=86400)
        missing = set(self.rosters) - set(SHORT)
        if missing: die(f"tools/league.json has no owner name for roster_id {sorted(missing)}")

    @staticmethod
    def _get(url, name, max_age=0):
        f = CACHE / name
        if max_age and f.exists() and time.time() - f.stat().st_mtime < max_age:
            return json.loads(f.read_text())
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    data = r.read()
                break
            except OSError as e:
                if attempt == 2: die(f"can't reach Sleeper ({url}): {e}")
                time.sleep(2)
        f.write_bytes(data)
        return json.loads(data)

    def owner(self, rid): return self.users.get(self.rosters[rid]["owner_id"], {})
    def team(self, rid):
        u = self.owner(rid)
        return (u.get("metadata", {}).get("team_name") or u.get("display_name") or SHORT[rid]).strip()
    def avatar(self, rid):
        u = self.owner(rid); m = u.get("metadata", {}).get("avatar")
        return m if m else f"https://sleepercdn.com/avatars/thumbs/{u.get('avatar')}"
    def player(self, pid):
        """(full name, short name for scorer lines, position)"""
        p = self.players.get(pid, {})
        if p.get("position") == "DEF" or (not p and pid.isalpha()):
            return f"{pid} D/ST", f"{pid} D/ST", "DEF"
        full = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or pid
        words = [w for w in full.split() if w.rstrip(".") not in ("Jr", "Sr", "II", "III", "IV", "V")]
        return full, (words[-1] if words else pid), p.get("position", "")

    def games(self, w):
        g = defaultdict(list)
        for m in self.weeks[w]: g[m["matchup_id"]].append(m)
        return [v for v in g.values() if len(v) == 2]

    def results(self, upto):
        out = {rid: [] for rid in self.rosters}
        for w in range(1, upto + 1):
            for a, b in self.games(w):
                for x, y in ((a, b), (b, a)):
                    out[x["roster_id"]].append((w, x["points"], "W" if x["points"] > y["points"] else "L"))
        return out

    def when(self, t): return datetime.datetime.fromtimestamp(t["status_updated"] / 1000, TZ)


# ---- recap: matchup cards + league overview --------------------------------------------------
def _side(S, m, res):
    st = [(p, pts) for p, pts in zip(m["starters"], m["starters_points"]) if p != "0"]
    top = sorted(st, key=lambda x: -x[1])[:2]
    scor = " &middot; ".join(f'{E(S.player(p)[1])} <span class="pts">{num(pts)}</span>' for p, pts in top)
    rid = m["roster_id"]
    return f'''        <div class="matchup-side {"is-win" if res == "W" else "is-loss"}">
          <img class="matchup-avatar" src="{S.avatar(rid)}" alt="" loading="lazy">
          <div class="matchup-id">
            <div class="matchup-name">{SHORT[rid]}</div>
            <div class="matchup-team">{EQ(S.team(rid))}</div>
            <div class="matchup-scorers">{scor}</div>
          </div>
          <div class="matchup-score">{num(m["points"])}<span class="matchup-result">{res}</span></div>
        </div>'''


def _row(S, pid, pts, label=None, bench=False):
    name, _, pos = S.player(pid)
    return f'''      <div class="lineup-row{" is-bench" if bench else ""}">
        <span class="pos pos-{POSCLS.get(pos, pos.lower())}">{label or SLOT.get(pos, pos)}</span>
        <span class="lineup-name">{E(name)}</span>
        <span class="lineup-pts">{num(pts)}</span>
      </div>'''


def _lineup(S, m, res):
    slots = [s for s in S.league["roster_positions"] if s != "BN"]
    rows = ['      <div class="lineup-label">Starters</div>']
    rows += [_row(S, p, pts, SLOT[slot]) for slot, p, pts in zip(slots, m["starters"], m["starters_points"]) if p != "0"]
    bench = [p for p in m["players"] if p not in m["starters"]]
    if bench:
        rows.append('      <div class="lineup-label">Bench</div>')
        rows += [_row(S, p, m["players_points"].get(p, 0), bench=True) for p in bench]
    return (f'    <div class="matchup-lineup {"is-win" if res == "W" else "is-loss"}" aria-label="{SHORT[m["roster_id"]]} lineup">\n'
            + "\n".join(rows) + "\n      </div>")


def recap_html(S, w):
    out = [f"<h2>Week {WORDS[w]} Recap</h2>", '<div class="matchups">']
    games = [tuple(sorted(g, key=lambda m: -m["points"])) for g in S.games(w)]
    for a, b in sorted(games, key=lambda g: -(g[0]["points"] - g[1]["points"])):
        out.append(f'''<details class="matchup-card">
  <summary class="matchup-summary">
    <div class="matchup-scoreboard" role="group" aria-label="{SHORT[a["roster_id"]]} versus {SHORT[b["roster_id"]]}">
{_side(S, a, "W")}
        <div class="matchup-vs" aria-hidden="true">vs</div>
{_side(S, b, "L")}
    </div>
  </summary>
  <div class="matchup-lineups">
{_lineup(S, a, "W")}
{_lineup(S, b, "L")}
  </div>
</details>''')
    out.append("</div>")
    return "\n".join(out) + "\n\n" + overview_html(S, w)


def record_class(w, l):
    return "is-win" if l == 0 else ("is-warn" if w >= l else "is-loss")


def overview_html(S, upto):
    res = S.results(upto)
    allp = [p for r in res.values() for _, p, _ in r]
    hi, lo = max(allp), min(allp)
    pf = {rid: sum(p for _, p, _ in r) for rid, r in res.items()}
    wins = {rid: sum(1 for x in r if x[2] == "W") for rid, r in res.items()}
    out = ['<details class="score-pulse" open>', '  <summary>League overview</summary>', '  <div class="league-overview">',
           '    <table class="standings-table">', '      <thead>', '        <tr>', '          <th class="rk"></th>',
           '          <th class="who">Team</th>', '          <th class="rec">Record</th>', '          <th class="pf">PF</th>',
           '          <th class="scoring">Scoring</th>', '        </tr>', '      </thead>', '      <tbody>']
    for i, rid in enumerate(sorted(res, key=lambda r: (-wins[r], -pf[r])), 1):
        r = res[rid]; w = wins[rid]; l = len(r) - w
        bars = "".join(f'<span class="score-h {"is-win" if x == "W" else "is-loss"}{" is-best" if p == hi else ""}{" is-worst" if p == lo else ""}" '
                       f'style="width:{round(p / hi * 100)}%" title="W{k} {num(p)} {x}"></span>' for k, p, x in r)
        nums = "".join(f"<span>W{k}: {num(p)}</span>" for k, p, _ in r)
        rc = "is-win" if l == 0 else ("is-warn" if w > l else "is-loss")
        out += ['        <tr>', f'          <td class="rk">{i}</td>', f'          <td class="who">{SHORT[rid]}</td>',
                f'          <td class="rec {rc}">{w}&ndash;{l}</td>', f'          <td class="pf">{num(pf[rid])}</td>',
                '          <td class="scoring">', f'            <div class="score-hs">{bars}</div>',
                f'            <div class="score-nums">{nums}</div>', '          </td>', '        </tr>']
    return "\n".join(out + ['      </tbody>', '    </table>', '  </div>', '</details>'])


# ---- waivers + trades --------------------------------------------------------------------------
def _waiver_groups(S, items, newest_first):
    by = defaultdict(list)
    for d, rid, pid, bid in items: by[d.date()].append((rid, pid, bid))
    out = []
    for day in sorted(by, reverse=newest_first):
        rows = sorted(by[day], key=lambda x: (-x[2], SHORT[x[0]], S.player(x[1])[0]))
        lis = "\n".join(f"      <li>{SHORT[rid]} - {EQ(S.player(pid)[0])} ({SLOT.get(S.player(pid)[2], S.player(pid)[2])}) - ${bid}</li>"
                        for rid, pid, bid in rows)
        out.append(f'  <div class="waiver-group">\n    <p class="waiver-date">{day.strftime("%A, %b ")}{day.day}</p>\n    <ul>\n{lis}\n    </ul>\n  </div>')
    return out


def waivers_html(S, n):
    lo, hi = cutoff(n), cutoff(n + 1)
    items = []
    for t in S.tx:
        if t["type"] not in ("waiver", "free_agent") or not t.get("adds"): continue
        bid = (t.get("settings") or {}).get("waiver_bid", 0) if t["type"] == "waiver" else 0
        items += [(S.when(t), rid, pid, bid) for pid, rid in t["adds"].items()]
    cur = [i for i in items if lo <= i[0] < hi]; old = [i for i in items if i[0] < lo]
    out = ['<div class="roster waiver-log">', f'  <h3 class="waiver-heading">Week {WORDS[n]} Waivers</h3>']
    out += _waiver_groups(S, cur, False) or ['  <p class="waiver-date">No pickups yet this week.</p>']
    out += ['</div>', '<details class="roster waiver-log">', f'  <summary>Earlier pickups ({len(old)})</summary>']
    return "\n".join(out + _waiver_groups(S, old, True) + ['</details>'])


def trades_html(S, n):
    lines = []
    for t in sorted((t for t in S.tx if t["type"] == "trade" and S.when(t) < cutoff(n + 1)), key=lambda t: -t["status_updated"]):
        creator = next((r["roster_id"] for r in S.rosters.values() if r["owner_id"] == t["creator"]), None)
        parts = []
        for rid in sorted(t["roster_ids"], key=lambda r: r != creator):
            got = sorted((S.player(p)[0] for p, r in (t.get("adds") or {}).items() if r == rid), key=lambda x: (x.split()[-1], x))
            got += [f"${b['amount']}" for b in (t.get("waiver_budget") or []) if b["receiver"] == rid]
            parts.append(f"{SHORT[rid]} gets {', '.join(got)}")
        lines.append("      <li>" + EQ("; ".join(parts)) + "</li>")
    return '<div class="trades">\n  <h3>Trades</h3>\n  <ul>\n' + "\n".join(lines) + "\n  </ul>\n</div>"


# ---- team stat chips + scoring chart -------------------------------------------------------------
def stat_blocks(S, upto):
    res = S.results(upto)
    allp = [p for r in res.values() for _, p, _ in r]
    hi, lo, avg = max(allp), min(allp), sum(allp) / len(allp)
    pf = {rid: sum(p for _, p, _ in r) for rid, r in res.items()}
    order = sorted(pf, key=lambda r: -pf[r])
    budget = S.league["settings"].get("waiver_budget", 100)
    out = {}
    for rid, r in res.items():
        w = sum(1 for x in r if x[2] == "W"); l = len(r) - w
        last = r[-1][2]; streak = 0
        for x in reversed(r):
            if x[2] != last: break
            streak += 1
        pos = order.index(rid)
        pc = "is-win" if pos < 3 else ("is-loss" if pos >= len(order) - 2 else "is-warn")
        pts = [p for _, p, _ in r]
        faab = budget - S.rosters[rid]["settings"].get("waiver_budget_used", 0)
        cols = "\n".join(f'''    <div class="score-col">
      <span class="score-val">{num(p)}</span>
      <div class="score-bar {"is-hot" if p > 125 else ("is-mid" if p >= 100 else "is-cold")}{" is-best" if p == hi else ""}{" is-worst" if p == lo else ""}" style="height:{round(p / hi * 120)}px"></div>
      <span class="score-wk">W{k}</span>
    </div>''' for k, p, _ in r)
        out[SHORT[rid].lower()] = f'''<p class="rank-chips">
  <span class="stat-badge {record_class(w, l)}">{w}-{l}</span>
  <span class="stat-badge {"is-win" if last == "W" else "is-loss"}">{last}{streak}</span>
  <span class="stat-badge {pc}">PF: {num(pf[rid])}</span>
  <span class="stat-badge is-loss">FAAB: ${faab}</span>
</p>
<details class="score-log">
  <summary>Week-to-week scoring <span class="score-spread">spread {num(max(pts) - min(pts))}</span></summary>
  <div class="score-chart" style="--max:{num(hi)};--avg:{num(avg)}">
    <div class="score-plot">
      <div class="score-avg" title="League average {num(avg)}"></div>
{cols}
    </div>
    <p class="score-legend">Dashed line is league average ({num(avg)}). Same scale for every team. Red under 100, yellow 100–125, green over 125.</p>
  </div>
</details>'''
    return out


# ---- rankings: numbers + arrows ---------------------------------------------------------------
BLOCK_RE = re.compile(r'<div id="(\w+)">\n((?:(?!<div id=).)*?)<h2><span class="rank-name">(\d+)\. ', re.S)
GRADE_RE = re.compile(r'<span class="rank-grade [^"]*" title="[^"]*">Last Week: \d+ <span class="rank-move">[^<]*</span></span>')


def rank_order(s):
    return [m.group(1) for m in BLOCK_RE.finditer(s)]


def grade(prev, now):
    if prev is None: return None
    if prev == now: return f'<span class="rank-grade is-same" title="Held at {now}">Last Week: {prev} <span class="rank-move">&harr;</span></span>'
    if now < prev: return f'<span class="rank-grade is-up" title="Up {prev - now} from {prev}">Last Week: {prev} <span class="rank-move">▲</span></span>'
    return f'<span class="rank-grade is-down" title="Down {now - prev} from {prev}">Last Week: {prev} <span class="rank-move">▼</span></span>'


def apply_ranks(s, prev_page):
    prev = {}
    if prev_page and prev_page.exists():
        prev = {tid: i for i, tid in enumerate(rank_order(prev_page.read_text()), 1)}
    order = rank_order(s)
    for i, tid in enumerate(order, 1):
        start = s.index(f'<div id="{tid}">')
        h2s = s.index("<h2>", start); h2e = s.index("</h2>", h2s)
        h2 = re.sub(r'(<span class="rank-name">)\d+\. ', rf"\g<1>{i}. ", s[h2s:h2e], count=1)
        g = grade(prev.get(tid), i)
        if g: h2 = GRADE_RE.sub(lambda _: g, h2, count=1)
        s = s[:h2s] + h2 + s[h2e:]
    return s


# ---- build --------------------------------------------------------------------------------------
def sub_once(pattern, repl, s, what):
    new, k = re.subn(pattern, lambda _: repl, s, count=1, flags=re.S)
    if k != 1: die(f"couldn't find the {what} section on the page; was the layout changed? (tools/ff.py needs updating)")
    return new


def build_html(n, s, S):
    s = sub_once(r'<h2>Week \w+ Recap</h2>\n.*?(?=\n\n<h1>)', recap_html(S, n - 1), s, "Week N Recap")
    s = sub_once(r'<div class="roster waiver-log">.*?</div>\n\n(?=<hr>)', waivers_html(S, n) + "\n" + trades_html(S, n) + "\n\n", s, "waivers/trades")
    s = sub_once(r'<h1>Week \w+ Power Rankings</h1>', f"<h1>Week {WORDS[n]} Power Rankings</h1>", s, "Power Rankings heading")
    blocks = stat_blocks(S, n - 1)
    for tid, block in blocks.items():
        s, k = re.subn(rf'(<div id="{tid}">\n(?:(?!<div id=).)*?<h2>.*?</h2>\n)<p class="rank-chips">.*?</details>',
                       lambda m: m.group(1) + block, s, count=1, flags=re.S)
        if k != 1: die(f"couldn't find the stat block for '{tid}' (every team needs <div id=\"{tid}\"> with its rank-chips and score-log)")
    for rid in S.rosters:  # team names in the headers come from Sleeper, so renames show up
        tid, name = SHORT[rid].lower(), EQ(S.team(rid))
        s, k = re.subn(rf'(<div id="{tid}">\n(?:(?!<div id=).)*?<h2><span class="rank-name">\d+\. [^<]*? &mdash; )[^<]*(?=</span>)',
                       lambda m: m.group(1) + name, s, count=1, flags=re.S)
        if k != 1: die(f"couldn't find the team name in '{tid}'s header (expected: <span class=\"rank-name\">N. {SHORT[rid]} &mdash; Team Name</span>)")
    return apply_ranks(s, page_path(n - 1))


def cmd_build(n):
    p = page_path(n)
    if not p.exists(): die(f"{p.relative_to(ROOT)} doesn't exist; run: python3 tools/ff.py new {n}")
    S = Sleeper(n - 1, n)
    p.write_text(build_html(n, p.read_text(), S))
    pending = [(SHORT[m["roster_id"]], S.player(pid)[0]) for m in S.weeks[n - 1]
               for pid, pts in zip(m["starters"], m["starters_points"]) if pid != "0" and pts == 0]
    print(f"ff: built week {n} (Week {n - 1} recap, waivers, trades, stats, team names, ranks); starters at 0 pts in week {n - 1}: {len(pending)}")


# ---- check ---------------------------------------------------------------------------------------
class _Balance(HTMLParser):
    TAGS = ("div", "article", "main", "section", "nav", "aside", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td",
            "th", "h1", "h2", "h3", "p", "details", "summary", "figure")
    def __init__(self): super().__init__(); self.stack, self.bad = [], []
    def handle_starttag(self, t, a):
        if t in self.TAGS: self.stack.append((t, self.getpos()[0]))
    def handle_endtag(self, t):
        if t not in self.TAGS: return
        if self.stack and self.stack[-1][0] == t: self.stack.pop()
        else: self.bad.append(f"stray </{t}> on line {self.getpos()[0]}")


def _paras(s):
    """Hand-written text on a page: <p> and <li> outside the generated sections."""
    s = re.sub(r'<nav class="sidebar-nav">.*?</nav>', "", s, flags=re.S)
    s = re.sub(r'<h2>Week \w+ Recap</h2>.*?(?=\n\n<h1>)', "", s, flags=re.S)
    s = re.sub(r'<div class="roster waiver-log">.*?</div>\n\n(?=<hr>)', "", s, flags=re.S)
    s = re.sub(r'<p class="rank-chips">.*?</details>', "", s, flags=re.S)
    out = []
    for m in re.finditer(r"<(p|li)(?: class=\"[^\"]*\")?>(.*?)</\1>", s, re.S):
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if len(text) > 25: out.append(text)
    return out


def check_problems(n, S=None):
    p = page_path(n)
    if not p.exists(): return [f"{p.relative_to(ROOT)} doesn't exist"]
    s = p.read_text(); probs = []
    b = _Balance(); b.feed(s)
    probs += b.bad[:5] + [f"<{t}> opened on line {ln} is never closed" for t, ln in b.stack[:5]]
    for ph in sorted(set(re.findall(r"\[[A-Z][A-Z0-9 /&\-]{2,}\]", s))):
        probs.append(f"placeholder text still on the page: {ph}")
    prev = page_path(n - 1)
    if prev.exists():
        old = set(_paras(prev.read_text()))
        for t in _paras(s):
            if t in old: probs.append(f"text copied from week {n - 1}'s page: \"{t[:70]}...\"")
        for img in sorted(set(re.findall(rf'src="([^"]*week-?{n - 1}[^"]*)"', s))):
            probs.append(f"week {n - 1} image still on the page: {img}")
    for ref in sorted(set(re.findall(r'(?:href|src)="([^"#:?]+)"', s))):
        tgt = (p.parent / ref).resolve()
        if ref.endswith("/") or tgt.is_dir(): tgt = tgt / "index.html"
        if not tgt.exists(): probs.append(f"broken link: {ref}")
    me = f"power-rankings-week-{n}/"
    for page in ROOT.rglob("*.html"):
        if ".git" in page.parts or page == p: continue
        t = page.read_text()
        if 'class="sidebar-nav"' in t and me not in t: probs.append(f"no nav link to week {n} in {page.relative_to(ROOT)}")
    if me not in (ROOT / "index.html").read_text(): probs.append(f"no week {n} card on the home page")
    S = S or Sleeper(n - 1, n)
    if S.league["settings"].get("last_scored_leg", 0) < n - 1:
        probs.append(f"Sleeper hasn't finished scoring week {n - 1} yet; wait until its games are final, then build again")
    if build_html(n, s, S) != s:
        probs.append(f"Sleeper data on the page is out of date or was hand-edited; run: python3 tools/ff.py build {n}")
    return probs


def cmd_check(n):
    probs = check_problems(n)
    if probs:
        print(f"ff: week {n} is NOT ready to publish:", file=sys.stderr)
        for x in probs: print(f"  - {x}", file=sys.stderr)
        sys.exit(1)
    print(f"ff: week {n} passed every check")


# ---- new week -------------------------------------------------------------------------------------
def cmd_new(n):
    src, dst = page_path(n - 1), page_path(n)
    if not src.exists(): die(f"week {n - 1}'s page doesn't exist")
    if dst.exists(): die(f"{dst.relative_to(ROOT)} already exists")
    s = src.read_text()
    old_t = re.search(r"<title>(.*?) — Fantasy Fucks</title>", s).group(1)
    new_t = f"Power Rankings (Week {n})"
    for a, b in [(f"<title>{old_t} — ", f"<title>{new_t} — "), (f'<span class="topbar-title">{old_t}</span>', f'<span class="topbar-title">{new_t}</span>'),
                 (f"/ {old_t}</p>", f"/ {new_t}</p>"), (f"<h1>{old_t}</h1>", f"<h1>{new_t}</h1>")]:
        if s.count(a) != 1: die(f"couldn't retitle the copied page (looking for {a!r})")
        s = s.replace(a, b)
    s = re.sub(r"<!-- clickup-export:[^>]*-->\n", "", s)
    s = re.sub(r'<p class="meta">Updated \d{4}-\d{2}-\d{2}</p>', f'<p class="meta">Updated {datetime.date.today()}</p>', s, count=1)
    li = re.compile(r'<li class="nav-node(?: is-branch)?"><a class="nav-link" href="([^"]*)" title="' + re.escape(old_t)
                    + r'"(?: aria-current="page")?>' + re.escape(old_t) + r"</a></li>")
    mk = lambda href, cur=False: (f'<li class="nav-node is-branch"><a class="nav-link" href="./" title="{new_t}" aria-current="page">{new_t}</a></li>' if cur
                                  else f'<li class="nav-node"><a class="nav-link" href="{href}" title="{new_t}">{new_t}</a></li>')
    s, k = li.subn(lambda m: mk(None, True) + f'<li class="nav-node"><a class="nav-link" href="../power-rankings-week-{n - 1}/" title="{old_t}">{old_t}</a></li>', s, count=1)
    if k != 1: die("couldn't find the nav entry on the copied page")
    dst.parent.mkdir(); dst.write_text(s)
    changed = 0
    for page in sorted(ROOT.rglob("*.html")):
        if ".git" in page.parts or page == dst: continue
        t = page.read_text(); m = li.search(t)
        if not m: continue
        href = m.group(1).replace(f"power-rankings-week-{n - 1}/", f"power-rankings-week-{n}/") if m.group(1) != "./" else f"../power-rankings-week-{n}/"
        page.write_text(t[:m.start()] + mk(href) + t[m.start():]); changed += 1
    home = ROOT / "index.html"; t = home.read_text()
    card = f'    <a class="page-card" href="this-season/power-rankings-week-{n - 1}/">'
    if t.count(card) == 1:
        hero = next((f"assets/{f.name}" for f in sorted((ROOT / "assets").glob(f"week{n}-hero.*"))), f"assets/week{n}-hero.jpg")
        home.write_text(t.replace(card, f'    <a class="page-card" href="this-season/power-rankings-week-{n}/">\n      <h2>{new_t}</h2>\n'
                                        f'      <img src="{hero}" alt="" loading="lazy">\n    </a>\n' + card))
    print(f"ff: created {dst.relative_to(ROOT)} from week {n - 1}; nav link added to {changed} pages; home card added.\n"
          f"    Next: write the intro, Matchup of the Week, ranking order and team write-ups, add assets/week{n}-hero.jpg,\n"
          f"    then: python3 tools/ff.py build {n} && python3 tools/ff.py check {n}")


# ---- setup + hook --------------------------------------------------------------------------------
def cmd_setup():
    subprocess.run(["git", "-C", str(ROOT), "config", "core.hooksPath", "tools/hooks"], check=True)
    print("ff: pre-commit hook on (git config core.hooksPath tools/hooks)")


def cmd_hook():
    n = latest_week()
    if n is None: return
    rel = str(page_path(n).relative_to(ROOT))
    staged = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split()
    if rel not in staged: return
    cmd_build(n)
    subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True)
    probs = check_problems(n)
    if probs:
        print(f"ff: commit blocked, week {n} is not ready to publish:", file=sys.stderr)
        for x in probs: print(f"  - {x}", file=sys.stderr)
        print("    Fix these, then commit again. (Sleeper data was refreshed and staged for you.)", file=sys.stderr)
        sys.exit(1)
    print(f"ff: week {n} built from Sleeper and passed every check")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"): print(__doc__); sys.exit(0)
    cmd, args = a[0], a[1:]
    week = lambda: int(args[0]) if args else (latest_week() or die("no weekly pages found"))
    if cmd == "setup": cmd_setup()
    elif cmd == "hook": cmd_hook()
    elif cmd == "new": cmd_new(int(args[0]) if args else latest_week() + 1)
    elif cmd == "build": cmd_build(week())
    elif cmd == "check": cmd_check(week())
    else: die(f"unknown command {cmd!r}; see python3 tools/ff.py --help")
