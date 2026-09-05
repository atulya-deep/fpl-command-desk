"""Renders the strategy dashboard to a self-contained HTML file."""
import html, json, math, os, datetime

CSS = """
:root{
  color-scheme: light;
  --bg:#f4f6f2; --panel:#ffffff; --panel-2:#eef1ec; --line:#dbe0d8; --line-2:#c7cec3;
  --ink:#101613; --ink-2:#4a544d; --ink-3:#78827a;
  --teal:#0e8f7e; --rust:#bf5220; --amber:#a9761a; --violet:#5b4bb0;
  --good-fill:#8ccec1; --bad-fill:#e3a684; --mid-fill:#e7eae4;
  --chip:#e7ebe4; --shadow:0 1px 2px rgba(16,22,19,.06),0 8px 24px -16px rgba(16,22,19,.28);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#0f1512; --panel:#171f1b; --panel-2:#1e2823; --line:#2a352f; --line-2:#3a473f;
    --ink:#eef2ec; --ink-2:#a8b3ab; --ink-3:#7d887f;
    --teal:#17a189; --rust:#d96e2e; --amber:#d9a441; --violet:#9085e9;
    --good-fill:#124f47; --bad-fill:#6b3520; --mid-fill:#1d2723;
    --chip:#222d27; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -16px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#0f1512; --panel:#171f1b; --panel-2:#1e2823; --line:#2a352f; --line-2:#3a473f;
  --ink:#eef2ec; --ink-2:#a8b3ab; --ink-3:#7d887f;
  --teal:#17a189; --rust:#d96e2e; --amber:#d9a441; --violet:#9085e9;
  --good-fill:#124f47; --bad-fill:#6b3520; --mid-fill:#1d2723;
  --chip:#222d27; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -16px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
body{
  background:var(--bg); color:var(--ink); margin:0;
  font-family:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding:28px 20px 72px; display:flex; flex-direction:column; gap:30px}
h1,h2,h3{font-family:Archivo,"Arial Narrow",system-ui,sans-serif; margin:0; text-wrap:balance; letter-spacing:-.015em}
h1{font-size:clamp(28px,4.4vw,42px); font-weight:800; line-height:1.03}
h2{font-size:19px; font-weight:700}
h3{font-size:15px; font-weight:700}
.num{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace; font-variant-numeric:tabular-nums}
.eyebrow{font-size:11px; font-weight:700; letter-spacing:.13em; text-transform:uppercase; color:var(--ink-3);
  font-family:Archivo,system-ui,sans-serif}

/* header */
header{display:flex; flex-wrap:wrap; gap:18px; align-items:flex-end; justify-content:space-between;
  border-bottom:2px solid var(--ink); padding-bottom:16px}
.hmeta{display:flex; gap:22px; flex-wrap:wrap}
.hmeta div{display:flex; flex-direction:column; gap:2px}
.hmeta b{font-size:16px; font-weight:600}

/* decision strip */
.verdict{background:var(--panel); border:1px solid var(--line); border-left:5px solid var(--teal);
  border-radius:3px; padding:20px 22px; box-shadow:var(--shadow); display:flex; flex-direction:column; gap:10px}
.verdict p{margin:0; color:var(--ink-2); max-width:74ch}
.verdict .call{font-family:Archivo,system-ui,sans-serif; font-size:22px; font-weight:800; line-height:1.2}

/* kpi row */
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:1px; background:var(--line);
  border:1px solid var(--line); border-radius:3px; overflow:hidden}
.kpi{background:var(--panel); padding:15px 16px; display:flex; flex-direction:column; gap:4px}
.kpi .v{font-family:"IBM Plex Mono",monospace; font-size:27px; font-weight:600; line-height:1;
  font-variant-numeric:tabular-nums}
.kpi .s{font-size:12.5px; color:var(--ink-3)}

section{display:flex; flex-direction:column; gap:14px}
.shead{display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap;
  border-bottom:1px solid var(--line-2); padding-bottom:7px}
.shead p{margin:0; font-size:13px; color:var(--ink-3); max-width:60ch}

/* tables */
.tw{overflow-x:auto; border:1px solid var(--line); border-radius:3px; background:var(--panel)}
table{border-collapse:collapse; width:100%; font-size:13.5px}
th{font-family:Archivo,system-ui,sans-serif; font-size:10.5px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--ink-3); text-align:left; padding:9px 10px; border-bottom:1px solid var(--line-2); white-space:nowrap;
  background:var(--panel)}
td{padding:8px 10px; border-bottom:1px solid var(--line); white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--panel-2)}
td.n,th.n{text-align:right; font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums}
.pname{font-weight:600}
.tm{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3); margin-left:6px}
.pos{display:inline-block; min-width:34px; text-align:center; font-family:Archivo,system-ui,sans-serif;
  font-size:10px; font-weight:700; letter-spacing:.06em; padding:2px 5px; border-radius:2px;
  background:var(--chip); color:var(--ink-2)}
/* set-piece duty */
.sp{display:inline-block; font-family:Archivo,system-ui,sans-serif; font-size:9px; font-weight:800;
  letter-spacing:.07em; padding:1px 4px; border-radius:2px; margin-left:4px; vertical-align:1px;
  border:1px solid currentColor}
.sp.pen{color:var(--violet)}
.sp.set{color:var(--ink-3)}

/* inline projection bar */
.bar{position:relative; height:16px; min-width:104px; background:var(--panel-2); border-radius:2px; overflow:hidden}
.bar span{position:absolute; inset:0 auto 0 0; background:var(--teal); border-radius:0 2px 2px 0}
.bar b{position:absolute; right:5px; top:0; line-height:16px; font-size:11px; font-weight:600;
  font-family:"IBM Plex Mono",monospace; color:var(--ink)}

/* heat cells */
.hc{display:block; padding:6px 5px; border-radius:2px; text-align:center; font-family:"IBM Plex Mono",monospace;
  font-size:11.5px; line-height:1.25; background:var(--mid-fill); color:var(--ink)}
.hc.good{background:color-mix(in oklab, var(--good-fill) calc(var(--t)*100%), var(--mid-fill))}
.hc.bad{background:color-mix(in oklab, var(--bad-fill) calc(var(--t)*100%), var(--mid-fill))}
.hc small{display:block; font-size:9.5px; color:var(--ink-2); letter-spacing:.02em}
.grid td{padding:3px}
.grid th.gw{text-align:center}

/* simulation distribution */
.dist{display:flex; flex-direction:column; gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:3px; overflow:hidden}
.drow{background:var(--panel); display:grid; grid-template-columns:54px 1fr 122px; gap:14px;
  align-items:center; padding:11px 15px}
.drow.head{background:var(--panel-2)}
.drow.head span{font-family:Archivo,system-ui,sans-serif; font-size:10.5px; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-3)}
.gwlab{font-family:Archivo,system-ui,sans-serif; font-weight:800; font-size:13px}
.track{position:relative; height:24px}
.track .axis{position:absolute; left:0; right:0; top:50%; height:1px; background:var(--line)}
.track .band{position:absolute; top:5px; height:14px; border-radius:2px;
  background:color-mix(in oklab, var(--teal) 20%, var(--panel))}
.track .iqr{position:absolute; top:5px; height:14px; border-radius:2px;
  background:color-mix(in oklab, var(--teal) 46%, var(--panel))}
.track .med{position:absolute; top:2px; width:2px; height:20px; background:var(--ink); border-radius:1px}
.track .cap{position:absolute; top:-1px; font-size:9.5px; color:var(--ink-3);
  font-family:"IBM Plex Mono",monospace}
.dnum{font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; font-size:12.5px;
  text-align:right; color:var(--ink-2)}
.dnum b{color:var(--ink); font-size:14px}

/* legend */
.legend{display:flex; align-items:center; gap:9px; font-size:12px; color:var(--ink-3); flex-wrap:wrap}
.ramp{display:flex; height:11px; border-radius:2px; overflow:hidden; width:150px; border:1px solid var(--line)}
.ramp i{flex:1}

/* week plan */
.weeks{display:grid; grid-template-columns:repeat(auto-fit,minmax(196px,1fr)); gap:12px}
.week{background:var(--panel); border:1px solid var(--line); border-radius:3px; padding:14px 15px;
  display:flex; flex-direction:column; gap:9px}
.week .wn{display:flex; align-items:baseline; gap:8px}
.week .wn i{font-family:Archivo,system-ui,sans-serif; font-style:normal; font-size:11px; font-weight:800;
  color:var(--ink-3); letter-spacing:.08em}
.week .cap{font-weight:600; font-size:15px}
.week .cap em{font-style:normal; color:var(--ink-3); font-weight:400; font-size:12px; display:block}
.week ul{margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:5px;
  border-top:1px solid var(--line); padding-top:9px}
.week li{display:flex; justify-content:space-between; gap:8px; font-size:12.5px; color:var(--ink-2)}
.week li b{font-family:"IBM Plex Mono",monospace; font-weight:600; color:var(--ink)}

/* ledger */
.ledger{display:flex; flex-direction:column; gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:3px; overflow:hidden}
.row{background:var(--panel); display:grid; grid-template-columns:1fr auto 1fr auto; gap:14px; align-items:center;
  padding:12px 15px}
.row .out .pname{text-decoration:line-through; text-decoration-color:var(--rust); text-decoration-thickness:2px}
.row .arrow{color:var(--ink-3); font-family:"IBM Plex Mono",monospace}
.row .gain{font-family:"IBM Plex Mono",monospace; font-weight:600; color:var(--teal); font-size:15px}
.row .sub{font-size:11.5px; color:var(--ink-3); font-family:"IBM Plex Mono",monospace}
@media (max-width:640px){ .row{grid-template-columns:1fr auto; gap:8px} .row .arrow{display:none} }

/* pills */
.pill{display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:2px 8px;
  border-radius:99px; font-family:Archivo,system-ui,sans-serif; letter-spacing:.04em}
.pill.out{background:color-mix(in oklab,var(--rust) 16%,var(--panel)); color:var(--rust)}
.pill.warn{background:color-mix(in oklab,var(--amber) 20%,var(--panel)); color:var(--amber)}
.pill.ok{background:color-mix(in oklab,var(--teal) 16%,var(--panel)); color:var(--teal)}
.pill::before{content:""; width:5px; height:5px; border-radius:99px; background:currentColor}

.cols{display:grid; grid-template-columns:repeat(auto-fit,minmax(272px,1fr)); gap:16px}
.note{font-size:12.5px; color:var(--ink-3); line-height:1.6; max-width:78ch}
.note code{font-family:"IBM Plex Mono",monospace; font-size:11.5px; background:var(--chip); padding:1px 5px;
  border-radius:2px}
footer{border-top:1px solid var(--line-2); padding-top:16px; display:flex; flex-direction:column; gap:8px}
button.tg{font-family:Archivo,system-ui,sans-serif; font-size:11px; font-weight:700; letter-spacing:.07em;
  text-transform:uppercase; padding:5px 11px; border:1px solid var(--line-2); background:var(--panel);
  color:var(--ink-2); border-radius:2px; cursor:pointer}
button.tg[aria-pressed="true"]{background:var(--ink); color:var(--bg); border-color:var(--ink)}
button.tg:focus-visible{outline:2px solid var(--teal); outline-offset:2px}
@media (prefers-reduced-motion:no-preference){ .hc,button.tg{transition:background .18s ease,color .18s ease} }
"""

JS = """
(function(){
  var btns=document.querySelectorAll('[data-view]');
  function apply(mode){
    document.querySelectorAll('.hc[data-att]').forEach(function(c){
      var v=parseFloat(c.dataset[mode]);
      c.classList.toggle('good', v>0); c.classList.toggle('bad', v<0);
      c.style.setProperty('--t', Math.min(Math.abs(v),1).toFixed(3));
    });
    btns.forEach(function(b){ b.setAttribute('aria-pressed', String(b.dataset.view===mode)); });
  }
  btns.forEach(function(b){ b.addEventListener('click',function(){ apply(b.dataset.view); }); });
})();
"""


def esc(s):
    return html.escape(str(s), quote=True)


def heat(v):
    """v in [-1,1]; returns (class, magnitude) for the diverging fill."""
    c = "good" if v > 0 else ("bad" if v < 0 else "")
    return c, min(abs(v), 1.0)


def cell(opp_txt, sub, att, dfn):
    c, t = heat(att)
    return ('<span class="hc %s" data-att="%.3f" data-def="%.3f" style="--t:%.3f">%s<small>%s</small></span>'
            % (c, att, dfn, t, esc(opp_txt), esc(sub)))


def dist_row(label, d, lo, hi, extra=""):
    """One p10-p90 range bar with an interquartile block and a median tick."""
    span = max(hi - lo, 1.0)
    def x(v):
        return max(0.0, min(100.0, (v - lo) / span * 100.0))
    return (
        '<div class="drow"><span class="gwlab">%s</span>'
        '<div class="track"><span class="axis"></span>'
        '<span class="band" style="left:%.1f%%;width:%.1f%%"></span>'
        '<span class="iqr" style="left:%.1f%%;width:%.1f%%"></span>'
        '<span class="med" style="left:%.1f%%"></span>'
        '<span class="cap" style="left:%.1f%%">%s</span>'
        '<span class="cap" style="left:%.1f%%">%s</span></div>'
        '<span class="dnum"><b>%s</b>%s</span></div>'
        % (esc(label),
           x(d["p10"]), x(d["p90"]) - x(d["p10"]),
           x(d["p25"]), x(d["p75"]) - x(d["p25"]),
           x(d["median"]),
           x(d["p10"]), d["p10"], min(x(d["p90"]), 94.0), d["p90"],
           d["median"], esc(extra)))


def duty(p):
    """Set-piece duty badges: penalties first, then corners / free kicks."""
    out = []
    if p.get("pen_order") in (1, 2):
        out.append('<span class="sp pen" title="Penalty taker, order %d">PEN%s</span>'
                   % (p["pen_order"], "" if p["pen_order"] == 1 else "2"))
    if p.get("ck_order") == 1:
        out.append('<span class="sp set" title="First-choice corners">CO</span>')
    if p.get("fk_order") == 1:
        out.append('<span class="sp set" title="First-choice direct free kicks">FK</span>')
    return "".join(out)


def bar(val, vmax, label=None):
    pct = 0 if vmax <= 0 else max(3.0, min(100.0, val / vmax * 100.0))
    return ('<div class="bar"><span style="width:%.1f%%"></span><b>%s</b></div>'
            % (pct, esc(label if label is not None else "%.1f" % val)))


def render(ctx, path):
    gws = ctx["gws"]
    P = []
    A = P.append

    A('<title>%s</title>' % esc(ctx["title"]))
    A('<link rel="preconnect" href="https://fonts.googleapis.com">')
    A('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    A('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Archivo:wght@700;800&family=IBM+Plex+Mono:wght@500;600&'
      'family=Source+Sans+3:wght@400;600&display=swap">')
    A("<style>%s</style>" % CSS)
    A('<div class="wrap">')

    # ---- header
    A('<header><div>')
    A('<div class="eyebrow">Fantasy Premier League &middot; %s</div>' % esc(ctx["season"]))
    A("<h1>%s</h1>" % esc(ctx["headline"]))
    A('</div><div class="hmeta">')
    for lab, val in ctx["header_meta"]:
        A('<div><span class="eyebrow">%s</span><b class="num">%s</b></div>' % (esc(lab), esc(val)))
    A("</div></header>")

    # ---- verdict
    v = ctx["verdict"]
    A('<div class="verdict"><span class="eyebrow">The call for GW%d</span>' % gws[0])
    A('<div class="call">%s</div>' % esc(v["call"]))
    for para in v["body"]:
        A("<p>%s</p>" % para)
    A("</div>")

    # ---- kpis
    A('<div class="kpis">')
    for k in ctx["kpis"]:
        A('<div class="kpi"><span class="eyebrow">%s</span><span class="v">%s</span>'
          '<span class="s">%s</span></div>' % (esc(k[0]), esc(k[1]), esc(k[2])))
    A("</div>")

    # ---- simulation
    sim = ctx.get("sim")
    if sim:
        A('<section><div class="shead"><h2>%s</h2><p>%s</p></div>' % (esc(sim["title"]), sim["sub"]))
        A('<div class="dist"><div class="drow head"><span>Week</span>'
          '<span>10th percentile &rarr; 90th percentile &middot; box is the middle half</span>'
          '<span style="text-align:right">Median</span></div>')
        for r in sim["rows"]:
            A(dist_row(r["label"], r["d"], sim["lo"], sim["hi"], r["extra"]))
        A("</div>")
        A('<p class="note">%s</p>' % sim["note"])
        A("</section>")

    # ---- week plan
    A('<section><div class="shead"><h2>The five-week sequence</h2>'
      '<p>Each week&rsquo;s projected XI total, captain, and the fixture that decides it.</p></div>')
    A('<div class="weeks">')
    for i, w in enumerate(ctx["weeks"], 1):
        A('<div class="week"><div class="wn"><i>WEEK %d</i><span class="eyebrow">GW%d</span></div>' % (i, w["gw"]))
        A('<div class="cap">%s <em>captain &middot; %s</em></div>' % (esc(w["cap"]), esc(w["cap_fix"])))
        A("<ul>")
        for lab, val in w["rows"]:
            A("<li><span>%s</span><b>%s</b></li>" % (esc(lab), esc(val)))
        A("</ul></div>")
    A("</div></section>")

    # ---- squad
    A('<section><div class="shead"><h2>Your squad, week by week</h2>'
      '<p>Projected points per gameweek. Colour runs from a favourable fixture to a hostile one.</p></div>')
    A('<div class="tw"><table><thead><tr><th>Player</th><th>Pos</th><th class="n">&pound;</th>')
    for g in gws:
        A('<th class="gw">GW%d</th>' % g)
    A('<th>5&#8209;GW projection</th><th>Status</th></tr></thead><tbody>')
    smax = max((p["total"] for p in ctx["squad"]), default=1)
    for p in ctx["squad"]:
        A("<tr>")
        A('<td><span class="pname">%s</span><span class="tm">%s</span>%s</td>'
          % (esc(p["name"]), esc(p["team_short"]), duty(p)))
        A('<td><span class="pos">%s</span></td><td class="n">%.1f</td>' % (esc(p["pos"]), p["price"]))
        for g in gws:
            f = p["fixt"].get(g) or []
            if not f:
                A('<td class="grid"><span class="hc">&ndash;<small>blank</small></span></td>')
            else:
                opp = "/".join(x["opp"] for x in f)
                ha = "".join("H" if x["home"] else "A" for x in f)
                A('<td class="grid">%s</td>' % cell(opp, "%s · %.1f" % (ha, p["gws"][g]),
                                                    p["heat"][g][0], p["heat"][g][1]))
        A("<td>%s</td>" % bar(p["total"], smax))
        A("<td>%s</td>" % p["status_html"])
        A("</tr>")
    A("</tbody></table></div></section>")

    # ---- transfers
    A('<section><div class="shead"><h2>%s</h2><p>%s</p></div>' % (esc(ctx["plan"]["title"]), ctx["plan"]["sub"]))
    A('<div class="ledger">')
    for m in ctx["plan"]["moves"]:
        A('<div class="row"><div class="out"><span class="pname">%s</span><span class="tm">%s</span>'
          '<div class="sub">%s</div></div><div class="arrow">&rarr;</div>'
          '<div class="in"><span class="pname">%s</span><span class="tm">%s</span><div class="sub">%s</div></div>'
          '<div class="gain">%s</div></div>'
          % (esc(m["out"]), esc(m["out_tm"]), esc(m["out_sub"]),
             esc(m["in"]), esc(m["in_tm"]), esc(m["in_sub"]), esc(m["gain"])))
    A("</div>")
    if ctx["plan"].get("footnote"):
        A('<p class="note">%s</p>' % ctx["plan"]["footnote"])
    A("</section>")

    # ---- fixture grid
    A('<section><div class="shead"><h2>Fixture swing, GW%d&ndash;%d</h2>' % (gws[0], gws[-1]))
    A('<p>Every club, by modelled expected goals. Switch the scale to read it from a defender&rsquo;s side.</p>'
      '</div>')
    A('<div class="legend"><button class="tg" data-view="att" aria-pressed="true">Attack</button>'
      '<button class="tg" data-view="def" aria-pressed="false">Defence</button>'
      '<span style="margin-left:6px">Hostile</span>'
      '<span class="ramp"><i style="background:color-mix(in oklab,var(--bad-fill) 100%,var(--mid-fill))"></i>'
      '<i style="background:color-mix(in oklab,var(--bad-fill) 55%,var(--mid-fill))"></i>'
      '<i style="background:var(--mid-fill)"></i>'
      '<i style="background:color-mix(in oklab,var(--good-fill) 55%,var(--mid-fill))"></i>'
      '<i style="background:color-mix(in oklab,var(--good-fill) 100%,var(--mid-fill))"></i></span>'
      '<span>Favourable</span></div>')
    A('<div class="tw"><table class="grid"><thead><tr><th>Club</th>')
    for g in gws:
        A('<th class="gw">GW%d</th>' % g)
    A('<th class="n">xGF/g</th><th class="n">xGA/g</th></tr></thead><tbody>')
    for r in ctx["ticker"]:
        A('<tr><td><span class="pname">%s</span></td>' % esc(r["team"]))
        for c in r["cells"]:
            if not c["legs"]:
                A('<td><span class="hc">&ndash;<small>blank</small></span></td>')
            else:
                A("<td>%s</td>" % cell(c["opp"], c["sub"], c["att"], c["def"]))
        A('<td class="n">%.2f</td><td class="n">%.2f</td></tr>' % (r["att_score"], r["def_score"]))
    A("</tbody></table></div></section>")

    # ---- target boards
    A('<section><div class="shead"><h2>Transfer targets by position</h2>'
      '<p>Ranked on projected points across the window, not on last week&rsquo;s haul.</p></div>')
    A('<div class="cols">')
    for pos, rows in ctx["targets"].items():
        A('<div class="tw"><table><thead><tr><th>%s</th><th class="n">&pound;</th><th class="n">5GW</th>'
          '<th class="n">Own</th></tr></thead><tbody>' % esc(pos))
        for p in rows:
            own = '<td class="n">%.0f%%</td>' % p["sel"]
            A('<tr><td><span class="pname">%s</span><span class="tm">%s</span>%s</td>'
              '<td class="n">%.1f</td><td class="n">%.1f</td>%s</tr>'
              % (esc(p["name"]), esc(p["team_short"]), duty(p), p["price"], p["total"], own))
        A("</tbody></table></div>")
    A("</div></section>")

    # ---- differentials + watchlist
    A('<div class="cols">')
    A('<section><div class="shead"><h2>Differentials</h2><p>Under 8% owned.</p></div>')
    A('<div class="tw"><table><thead><tr><th>Player</th><th class="n">&pound;</th><th class="n">5GW</th>'
      '<th class="n">Own</th></tr></thead><tbody>')
    for p in ctx["diffs"]:
        A('<tr><td><span class="pname">%s</span><span class="tm">%s</span> <span class="pos">%s</span>%s</td>'
          '<td class="n">%.1f</td><td class="n">%.1f</td><td class="n">%.1f%%</td></tr>'
          % (esc(p["name"]), esc(p["team_short"]), esc(p["pos"]), duty(p), p["price"], p["total"], p["sel"]))
    A("</tbody></table></div></section>")

    A('<section><div class="shead"><h2>Availability watchlist</h2><p>Live from the FPL feed.</p></div>')
    A('<div class="tw"><table><thead><tr><th>Player</th><th>Note</th></tr></thead><tbody>')
    for n in ctx["watch"]:
        A('<tr><td><span class="pname">%s</span><span class="tm">%s</span></td><td>%s %s</td></tr>'
          % (esc(n["name"]), esc(n["team_short"]), n["pill"], esc(n["news"])))
    A("</tbody></table></div></section>")
    A("</div>")

    # ---- method
    A("<footer><span class=\"eyebrow\">How these numbers are made</span>")
    A('<p class="note">%s</p>' % ctx["method"])
    A("</footer></div>")
    A("<script>%s</script>" % JS)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(P))
    return path
