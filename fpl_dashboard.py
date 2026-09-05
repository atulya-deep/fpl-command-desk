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
/* Must outrank every display rule below - a .panel{display:grid} silently
   beats the user-agent [hidden] style and leaves every tab panel on screen. */
[hidden]{display:none !important}
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

/* start screen + builder */
.start{max-width:760px; margin:24px auto; display:flex; flex-direction:column; gap:20px}
.start h1{font-size:clamp(30px,5vw,44px)}
.start .lede{font-size:16px; color:var(--ink-2); max-width:62ch}
.choices{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px}
.choice{text-align:left; background:var(--panel); border:1px solid var(--line); border-radius:3px;
  padding:18px 19px; cursor:pointer; display:flex; flex-direction:column; gap:7px;
  font-family:"Source Sans 3",system-ui,sans-serif}
.choice:hover{border-color:var(--teal)}
.choice:focus-visible{outline:2px solid var(--teal); outline-offset:2px}
.choice b{font-family:Archivo,system-ui,sans-serif; font-size:17px; font-weight:800; color:var(--ink)}
.choice span{font-size:13.5px; color:var(--ink-3); line-height:1.5}
.choice.primary{border-left:5px solid var(--teal)}

.bhead{display:flex; gap:12px; align-items:center; flex-wrap:wrap; justify-content:space-between}
.bfilters{display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:11px 13px;
  background:var(--panel-2); border:1px solid var(--line); border-radius:3px}
.bfilters button[data-et]{font-family:Archivo,system-ui,sans-serif; font-size:11px; font-weight:700;
  letter-spacing:.06em; padding:5px 11px; border:1px solid var(--line-2); background:var(--panel);
  color:var(--ink-2); border-radius:2px; cursor:pointer}
.bfilters button[data-et][aria-pressed="true"]{background:var(--ink); color:var(--bg); border-color:var(--ink)}
input[type=search]{font-family:"Source Sans 3",system-ui,sans-serif; font-size:13px; padding:5px 9px;
  border:1px solid var(--line-2); border-radius:2px; background:var(--panel); color:var(--ink); min-width:150px}
#bList{display:grid; grid-template-columns:repeat(auto-fill,minmax(228px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:3px; overflow:hidden;
  max-height:430px; overflow-y:auto}
.prow{display:flex; align-items:center; gap:7px; padding:8px 11px; background:var(--panel);
  border:none; cursor:pointer; text-align:left; font-family:"Source Sans 3",system-ui,sans-serif;
  font-size:13px; color:var(--ink); width:100%}
.prow:hover:not(:disabled){background:var(--panel-2)}
.prow:disabled{opacity:.34; cursor:not-allowed}
.prow.on{background:color-mix(in oklab,var(--teal) 15%,var(--panel))}
.prow .bp{margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ink-2)}
.prow .be{font-family:"IBM Plex Mono",monospace; font-size:12px; font-weight:600; color:var(--teal);
  min-width:24px; text-align:right}
.tbadge{font-size:12.5px; color:var(--ink-3)}

/* gameweek tabs */
.tabs{display:flex; gap:3px; overflow-x:auto; border-bottom:2px solid var(--ink); padding-bottom:0}
.tab{flex:0 0 auto; padding:8px 15px 7px; font-family:Archivo,system-ui,sans-serif; font-weight:700;
  font-size:13px; border:1px solid var(--line); border-bottom:none; background:var(--panel-2);
  color:var(--ink-2); cursor:pointer; border-radius:3px 3px 0 0; white-space:nowrap; text-align:left}
.tab .sub{display:block; font-size:10px; font-weight:600; letter-spacing:.05em; opacity:.8;
  font-family:"IBM Plex Mono",monospace}
.tab[aria-selected="true"]{background:var(--ink); color:var(--bg); border-color:var(--ink)}
.tab:focus-visible{outline:2px solid var(--teal); outline-offset:-2px}
.panel{padding-top:16px; display:grid; grid-template-columns:1fr 300px; gap:16px; align-items:start}
.vpanel{padding-top:16px; display:flex; flex-direction:column; gap:14px}
@media (max-width:820px){ .panel{grid-template-columns:1fr} }

.act{border:1px solid var(--line); border-left:5px solid var(--teal); border-radius:3px;
  background:var(--panel); padding:13px 15px; margin-bottom:12px}
.act.bank{border-left-color:var(--ink-3)}
.act .hd{font-family:Archivo,system-ui,sans-serif; font-weight:800; font-size:15px; margin-bottom:3px}
.act .sm{font-size:12.5px; color:var(--ink-3)}
.mv{display:flex; align-items:center; gap:8px; font-size:13px; padding:4px 0;
  border-top:1px solid var(--line)}
.mv:first-of-type{border-top:none; margin-top:7px; padding-top:8px}
.mv .o{color:var(--ink-3); text-decoration:line-through; text-decoration-color:var(--rust)}
.mv .g{margin-left:auto; font-family:"IBM Plex Mono",monospace; color:var(--teal); font-weight:600}

.xi{border:1px solid var(--line); border-radius:3px; background:var(--panel); overflow:hidden}
.xi .grp{display:flex; align-items:center; gap:8px; padding:5px 13px; background:var(--panel-2);
  font-family:Archivo,system-ui,sans-serif; font-size:10px; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-3); border-top:1px solid var(--line)}
.xi .grp:first-child{border-top:none}
.pl{display:grid; grid-template-columns:1fr 74px 90px 42px; gap:10px; align-items:center;
  padding:6px 13px; border-top:1px solid var(--line); font-size:13px}
.pl .fx{font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3)}
.pl .pt{font-family:"IBM Plex Mono",monospace; font-size:12.5px; text-align:right; font-weight:600}
.pl .arm{font-family:Archivo,system-ui,sans-serif; font-size:9.5px; font-weight:800;
  border:1px solid currentColor; border-radius:2px; padding:0 4px}
.pl .arm.c{color:var(--teal)} .pl .arm.v{color:var(--ink-3)}
.pl.benched{opacity:.62}
.mini{height:6px; background:var(--panel-2); border-radius:3px; overflow:hidden}
.mini span{display:block; height:100%; background:var(--teal)}

.rail{display:flex; flex-direction:column; gap:12px}
.card{border:1px solid var(--line); border-radius:3px; background:var(--panel); padding:14px 15px}
.card h3{font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3);
  margin-bottom:9px}
.card .big{font-family:"IBM Plex Mono",monospace; font-size:30px; font-weight:600; line-height:1;
  font-variant-numeric:tabular-nums}
.card .sm{font-size:12.5px; color:var(--ink-3); margin-top:4px}
.spread{position:relative; height:20px; margin-top:11px; background:var(--panel-2); border-radius:2px}
.spread .b{position:absolute; top:0; bottom:0; background:color-mix(in oklab,var(--teal) 34%,var(--panel-2));
  border-radius:2px}
.spread .m{position:absolute; top:-2px; bottom:-2px; width:2px; background:var(--ink)}
.kv{display:flex; justify-content:space-between; gap:10px; font-size:12.5px; padding:4px 0;
  border-top:1px solid var(--line)}
.kv:first-of-type{border-top:none}
.kv b{font-family:"IBM Plex Mono",monospace}

/* per-player simulation grid */
.pgrid{width:100%; border-collapse:collapse; font-size:13px}
.pgrid th{padding:8px 8px}
.pgrid td{padding:5px 8px; border-bottom:1px solid var(--line); white-space:nowrap}
.pgrid tbody tr:last-child td{border-bottom:none}
.pcell{position:relative; height:19px; width:62px; background:var(--panel-2); border-radius:2px;
  overflow:hidden}
.pcell .rng{position:absolute; top:0; bottom:0; background:color-mix(in oklab,var(--teal) 22%,var(--panel-2))}
.pcell .med{position:absolute; top:0; bottom:0; width:2px; background:var(--teal)}
.pcell b{position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font-family:"IBM Plex Mono",monospace; font-size:11px; font-weight:600; color:var(--ink)}
.pcell.zero{background:repeating-linear-gradient(45deg,var(--panel-2),var(--panel-2) 4px,var(--panel) 4px,var(--panel) 8px)}
.pcell.zero b{color:var(--ink-3)}
.vpm{font-family:"IBM Plex Mono",monospace; font-size:12px; font-variant-numeric:tabular-nums}

/* value scatter small multiples */
.facets{display:grid; grid-template-columns:repeat(auto-fit,minmax(232px,1fr)); gap:12px}
.facet{background:var(--panel); border:1px solid var(--line); border-radius:3px; padding:12px 12px 8px}
.facet h3{font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-2);
  margin-bottom:6px}
.facet svg{display:block; width:100%; height:auto; overflow:visible}
.facet .ax{stroke:var(--line-2); stroke-width:1}
.facet .gl{stroke:var(--line); stroke-width:1}
.facet text{fill:var(--ink-3); font-family:"IBM Plex Mono",monospace; font-size:8.5px}
.facet text.lbl{fill:var(--ink); font-family:"Source Sans 3",sans-serif; font-size:9.5px; font-weight:600}
.facet .pool{fill:var(--ink-3); opacity:.30}
.facet .mine{fill:var(--teal); stroke:var(--panel); stroke-width:1.5}

/* provenance banner */
.prov{display:flex; gap:12px; align-items:flex-start; padding:13px 16px; border-radius:3px;
  border:1px solid var(--line); background:var(--panel); font-size:13px; color:var(--ink-2)}
.prov.assumed{border-left:5px solid var(--amber)}
.prov.synced{border-left:5px solid var(--teal)}
.prov b{color:var(--ink)}
.prov p{margin:0; max-width:80ch}

/* live simulation controls */
.ctl{display:flex; gap:10px; align-items:center; flex-wrap:wrap; padding:12px 15px;
  background:var(--panel-2); border:1px solid var(--line); border-radius:3px}
.ctl label{font-family:Archivo,system-ui,sans-serif; font-size:10.5px; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-3)}
select, .ctl button{font-family:"Source Sans 3",system-ui,sans-serif; font-size:13px;
  padding:5px 9px; border:1px solid var(--line-2); border-radius:2px; background:var(--panel);
  color:var(--ink)}
.ctl button{font-family:Archivo,system-ui,sans-serif; font-size:11px; font-weight:700;
  letter-spacing:.07em; text-transform:uppercase; cursor:pointer}
.ctl button:hover:not(:disabled){background:var(--ink); color:var(--bg); border-color:var(--ink)}
.ctl button:disabled{opacity:.55; cursor:progress}
select:focus-visible, button:focus-visible{outline:2px solid var(--teal); outline-offset:2px}
.capsel{font-size:12px; padding:3px 6px; max-width:132px}
.drow{grid-template-columns:54px 1fr 108px 136px}
.drow.head{grid-template-columns:54px 1fr 108px 136px}
@media (max-width:720px){
  .drow, .drow.head{grid-template-columns:44px 1fr 92px; }
  .capsel{display:none}
}

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

TAB_JS = """
(function(){
  document.querySelectorAll('[role="tablist"]').forEach(function(bar){
    var tabs=[].slice.call(bar.querySelectorAll('[role="tab"]'));
    if(!tabs.length) return;
    function show(i){
      tabs.forEach(function(t,j){
        var on=i===j, panel=document.getElementById(t.getAttribute('aria-controls'));
        t.setAttribute('aria-selected',String(on));
        t.tabIndex=on?0:-1;
        if(panel) panel.hidden=!on;
      });
    }
    tabs.forEach(function(t,i){
      t.addEventListener('click',function(){ show(i); });
      t.addEventListener('keydown',function(e){
        var n=null;
        if(e.key==='ArrowRight') n=(i+1)%tabs.length;
        else if(e.key==='ArrowLeft') n=(i-1+tabs.length)%tabs.length;
        else if(e.key==='Home') n=0;
        else if(e.key==='End') n=tabs.length-1;
        if(n!==null){ e.preventDefault(); show(n); tabs[n].focus(); }
      });
    });
  });
})();
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


def week_panels(wk, gws):
    """Tabbed gameweek-by-gameweek plan."""
    P, A = [], None
    out = []
    out.append('<div class="tabs" role="tablist" aria-label="Gameweek plan">')
    for i, w in enumerate(wk):
        out.append(
            '<button class="tab" role="tab" id="tb%d" aria-controls="tp%d" '
            'aria-selected="%s" tabindex="%d" type="button">GW%d'
            '<span class="sub">%s</span></button>'
            % (w["gw"], w["gw"], "true" if i == 0 else "false", 0 if i == 0 else -1,
               w["gw"], esc(w["tab_sub"])))
    out.append("</div>")

    for i, w in enumerate(wk):
        out.append('<div class="panel" role="tabpanel" id="tp%d" aria-labelledby="tb%d"%s>'
                   % (w["gw"], w["gw"], "" if i == 0 else " hidden"))
        # ---- left column
        out.append("<div>")
        cls = "act" if w["moves"] else "act bank"
        out.append('<div class="%s"><div class="hd">%s</div><div class="sm">%s</div>'
                   % (cls, esc(w["action"]), w["action_sub"]))
        for m in w["moves"]:
            out.append('<div class="mv"><span class="o">%s</span><span>&rarr;</span>'
                       '<span class="pname">%s</span><span class="tm">%s</span>'
                       '<span class="g">%s</span></div>'
                       % (esc(m["out"]), esc(m["in"]), esc(m["in_tm"]), esc(m["gain"])))
        out.append("</div>")

        out.append('<div class="xi">')
        for grp in w["groups"]:
            out.append('<div class="grp">%s</div>' % esc(grp["label"]))
            for pl in grp["players"]:
                arm = ""
                if pl["armband"]:
                    arm = '<span class="arm %s">%s</span>' % (
                        "c" if pl["armband"] == "C" else "v", pl["armband"])
                out.append(
                    '<div class="pl%s"><span><span class="pname">%s</span>'
                    '<span class="tm">%s</span>%s %s</span>'
                    '<span class="fx">%s</span>'
                    '<span class="mini"><span style="width:%.0f%%"></span></span>'
                    '<span class="pt">%.1f</span></div>'
                    % (" benched" if pl["benched"] else "", esc(pl["name"]), esc(pl["team"]),
                       pl["duty"], arm, esc(pl["fix"]), pl["pct"], pl["pts"]))
        out.append("</div></div>")

        # ---- right rail
        out.append('<div class="rail">')
        d = w["dist"]
        lo, hi = w["dist_lo"], w["dist_hi"]
        span = max(hi - lo, 1.0)
        x = lambda v: max(0.0, min(100.0, (v - lo) / span * 100.0))
        out.append(
            '<div class="card"><h3>Simulated GW%d</h3><div class="big">%s</div>'
            '<div class="sm">median &middot; 80%% land between %s and %s</div>'
            '<div class="spread"><span class="b" style="left:%.1f%%;width:%.1f%%"></span>'
            '<span class="m" style="left:%.1f%%"></span></div></div>'
            % (w["gw"], d["median"], d["p10"], d["p90"],
               x(d["p10"]), x(d["p90"]) - x(d["p10"]), x(d["median"])))
        out.append('<div class="card"><h3>Transfer balance</h3>')
        for k, v in w["kv"]:
            out.append('<div class="kv"><span>%s</span><b>%s</b></div>' % (esc(k), esc(v)))
        out.append("</div>")
        if w.get("chip"):
            out.append('<div class="card"><h3>Chips</h3><div class="sm">%s</div></div>' % w["chip"])
        out.append("</div></div>")
    return "".join(out)


def pcell(d, vmax):
    """One player-gameweek: p10-p90 band, median tick, value in the middle."""
    if not d or d.get("p90", 0) <= 0:
        return '<div class="pcell zero"><b>0</b></div>'
    w = lambda v: max(0.0, min(100.0, v / vmax * 100.0))
    return ('<div class="pcell"><span class="rng" style="left:%.1f%%;width:%.1f%%"></span>'
            '<span class="med" style="left:%.1f%%"></span><b>%.0f</b></div>'
            % (w(d["p10"]), max(w(d["p90"]) - w(d["p10"]), 1.5), w(d["median"]), d["median"]))


def scatter(title, rows, mine_ids):
    """Price against projected points for one position. Emphasis, not category."""
    W, H, PL, PB, PT, PR = 232, 150, 26, 20, 8, 8
    xs = [r["price"] for r in rows] or [4.0]
    ys = [r["total"] for r in rows] or [0.0]
    x0, x1 = min(xs), max(max(xs), min(xs) + 0.5)
    y0, y1 = 0.0, max(max(ys), 1.0)
    def sx(v):
        return PL + (v - x0) / (x1 - x0) * (W - PL - PR)
    def sy(v):
        return H - PB - (v - y0) / (y1 - y0) * (H - PB - PT)
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s: price against projected points">'
         % (W, H, esc(title))]
    for frac in (0.0, 0.5, 1.0):
        yv = y0 + (y1 - y0) * frac
        p.append('<line class="gl" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                 % (PL, sy(yv), W - PR, sy(yv)))
        p.append('<text x="%.1f" y="%.1f" text-anchor="end">%.0f</text>' % (PL - 4, sy(yv) + 3, yv))
    p.append('<line class="ax" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (PL, H - PB, W - PR, H - PB))
    for xv in (x0, (x0 + x1) / 2, x1):
        p.append('<text x="%.1f" y="%.1f" text-anchor="middle">%.1f</text>' % (sx(xv), H - PB + 11, xv))
    p.append('<text x="%.1f" y="%.1f" text-anchor="middle">price &#163;m</text>'
             % ((PL + W - PR) / 2, H - 3))
    for r in rows:
        if r["id"] in mine_ids:
            continue
        p.append('<circle class="pool" cx="%.1f" cy="%.1f" r="2.6"/>' % (sx(r["price"]), sy(r["total"])))
    # place labels last, nudging any that would collide with one already placed
    placed = []
    mine = sorted([r for r in rows if r["id"] in mine_ids], key=lambda r: -r["total"])
    for r in mine:
        cx, cy = sx(r["price"]), sy(r["total"])
        p.append('<circle class="mine" cx="%.1f" cy="%.1f" r="4"/>' % (cx, cy))
        anchor = "end" if cx > W * 0.62 else "start"
        dx = -7 if anchor == "end" else 7
        ly = cy + 3.2
        for _ in range(6):
            if not any(abs(ly - py) < 9.5 and abs(cx - px) < 62 for px, py in placed):
                break
            ly += 10.0
        ly = min(ly, H - PB - 2)
        placed.append((cx, ly))
        p.append('<text class="lbl" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
                 % (cx + dx, ly, anchor, esc(r["name"])))
    p.append("</svg>")
    return '<div class="facet"><h3>%s</h3>%s</div>' % (esc(title), "".join(p))


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

    # Declared here, not left to the host: opening the file from disk or from a
    # server that omits the charset otherwise renders every pound sign as mojibake.
    A('<meta charset="utf-8">')
    A('<title>%s</title>' % esc(ctx["title"]))
    A('<link rel="preconnect" href="https://fonts.googleapis.com">')
    A('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    A('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Archivo:wght@700;800&family=IBM+Plex+Mono:wght@500;600&'
      'family=Source+Sans+3:wght@400;600&display=swap">')
    A("<style>%s</style>" % CSS)
    A('<div class="wrap">')

    # ---- start screen (first visit, or after "use a different team")
    A('<div id="startScreen" hidden><div class="start">')
    A('<div><div class="eyebrow">Fantasy Premier League &middot; %s</div>'
      "<h1>Set up your team</h1></div>" % esc(ctx["season"]))
    A('<p class="lede">This desk projects the next five gameweeks, plans your transfers deadline '
      "by deadline, and simulates the result thousands of times. It needs a squad to work from.</p>")
    A('<div class="choices">')
    A('<button class="choice primary" id="usePublished" type="button"><b>Use team %s</b>'
      "<span>The squad this site is built for, synced from FPL on the server every six hours. "
      "Best if it is your team, or you just want to look around.</span></button>"
      % esc(ctx["provenance"].get("team_id") or "-"))
    A('<button class="choice" id="startBuild" type="button"><b>Build a new team</b>'
      "<span>Pick fifteen players against the real &pound;100.0m budget, two-five-five-three "
      "shape and three-per-club limit. Everything on the page then runs off your squad.</span>"
      "</button>")
    A("</div>")
    A('<p class="note">A note on live syncing: the FPL API sends no cross-origin header, so this '
      "page cannot read your team straight from your browser &mdash; no site can. A squad you build "
      "here is saved in this browser. To have a team synced automatically instead, put its id in "
      "<code>config.json</code> in the repository and the six-hourly job will do it.</p>")
    A("</div></div>")

    # ---- squad builder
    A('<div id="builder" hidden><div class="start" style="max-width:none">')
    A('<div class="bhead"><div><div class="eyebrow">Build a squad</div>'
      "<h1 style=\"font-size:30px\">Pick your fifteen</h1></div>"
      '<div style="display:flex;gap:8px">'
      '<button class="tg" id="bAuto" type="button">Auto-fill</button>'
      '<button class="tg" id="bClear" type="button">Clear</button>'
      '<button class="tg" id="bDone" type="button" disabled>Pick 15 more</button></div></div>')
    A('<div class="kpis" id="bStats"></div>')
    A('<div class="bfilters">'
      '<button data-et="1" aria-pressed="true" type="button">GK</button>'
      '<button data-et="2" aria-pressed="false" type="button">DEF</button>'
      '<button data-et="3" aria-pressed="false" type="button">MID</button>'
      '<button data-et="4" aria-pressed="false" type="button">FWD</button>'
      '<input type="search" id="bSearch" placeholder="Search name or club" aria-label="Search players">'
      '<label for="bSort">Sort</label>'
      '<select id="bSort"><option value="ep">Projected points</option>'
      '<option value="value">Points per &pound;m</option>'
      '<option value="price">Price</option></select></div>')
    A('<div id="bList"></div>')
    A('<p class="note">Greyed-out players would break a rule: the position is full, they cost more '
      "than you have left, or you already hold three from that club. Auto-fill builds a legal squad "
      "on points per million, which is a starting point rather than an answer.</p>")
    A("</div></div>")

    A('<div id="appBody">')

    # ---- header
    A('<header><div>')
    A('<div class="eyebrow">Fantasy Premier League &middot; %s</div>' % esc(ctx["season"]))
    A("<h1>%s</h1>" % esc(ctx["headline"]))
    A('<div class="tbadge" id="teamBadge" style="margin-top:7px"></div>')
    A('</div><div class="hmeta">')
    for lab, val in ctx["header_meta"]:
        A('<div><span class="eyebrow">%s</span><b class="num">%s</b></div>' % (esc(lab), esc(val)))
    A('<div style="display:flex;gap:8px;align-self:flex-end">'
      '<button class="tg" id="rebuildTeam" type="button">Edit squad</button>'
      '<button class="tg" id="switchTeam" type="button">Use a different team</button></div>')
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

    # ---- provenance
    pv = ctx.get("provenance")
    if pv:
        A('<div class="prov %s"><div><span class="eyebrow">Where these inputs come from</span>'
          '<p>%s</p></div></div>' % ("synced" if pv["synced"] else "assumed", pv["text"]))

    # ---- simulation, tabbed
    if ctx.get("payload"):
        A('<section><div class="shead"><h2>Simulation</h2>'
          '<p>Every number here is resampled in your browser. Change a captain or swap a '
          'player and all three views recompute together.</p></div>')
        A('<div class="ctl">'
          '<label for="liveRuns">Runs</label>'
          '<select id="liveRuns"><option value="1000">1,000</option>'
          '<option value="3000" selected>3,000</option>'
          '<option value="10000">10,000</option></select>'
          '<label for="swapOut">Swap</label><select id="swapOut"></select>'
          '<span style="color:var(--ink-3)">&rarr;</span><select id="swapIn"></select>'
          '<button id="liveSwap" type="button">Apply</button>'
          '<button id="liveReset" type="button">Reset</button>'
          '<button id="liveRun" type="button">Re-run</button></div>')
        lk = ctx.get("live_kpis") or []
        A('<div class="kpis">')
        for tid, val, sub in lk:
            A('<div class="kpi" id="%s"><span class="v">%s</span><span class="s">%s</span></div>'
              % (tid, val, sub))
        A("</div>")

        views = [("sv-week", "By gameweek", "Spread of the squad total, week by week"),
                 ("sv-player", "By player", "Who actually produces the points"),
                 ("sv-value", "By value", "Points against price, per position")]
        A('<div class="tabs" role="tablist" aria-label="Simulation views">')
        for i, (vid, lab, sub) in enumerate(views):
            A('<button class="tab" role="tab" id="%s-t" aria-controls="%s" aria-selected="%s" '
              'tabindex="%d" type="button">%s<span class="sub">%s</span></button>'
              % (vid, vid, "true" if i == 0 else "false", 0 if i == 0 else -1,
                 esc(lab), esc(sub)))
        A("</div>")

        # view 1 - weekly spread
        A('<div class="vpanel" role="tabpanel" id="sv-week" aria-labelledby="sv-week-t">')
        A('<div class="dist"><div class="drow head"><span>Week</span>'
          '<span>10th &rarr; 90th percentile &middot; box is the middle half</span>'
          '<span style="text-align:right">Median</span><span>Captain</span></div>')
        A('<div id="liveRows">')
        sim = ctx.get("sim")
        if sim:
            for r in sim["rows"]:
                A(dist_row(r["label"], r["d"], sim["lo"], sim["hi"], r["extra"]))
        A("</div></div>")
        if sim:
            A('<p class="note">%s</p>' % sim["note"])
        A("</div>")

        # view 2 - per player
        ps = ctx.get("player_sim")
        A('<div class="vpanel" role="tabpanel" id="sv-player" aria-labelledby="sv-player-t" hidden>')
        A('<div id="playerHost">')
        if ps:
            A('<div class="tw"><table class="pgrid"><thead><tr><th>Player</th><th>Pos</th>'
              '<th class="n">&pound;</th>')
            for g in gws:
                A('<th class="gw" style="text-align:center">GW%d</th>' % g)
            A('<th class="n">5&#8209;GW</th><th class="n">Per &pound;m</th><th>Role</th></tr>'
              "</thead><tbody>")
            for r in ps["rows"]:
                A('<tr><td><span class="pname">%s</span><span class="tm">%s</span>%s</td>'
                  '<td><span class="pos">%s</span></td><td class="n">%.1f</td>'
                  % (esc(r["name"]), esc(r["team"]), r["duty"], esc(r["pos"]), r["price"]))
                for g in gws:
                    A('<td>%s</td>' % pcell(r["gw"].get(g), ps["cell_max"]))
                A('<td class="n">%.0f</td><td class="vpm">%.1f</td><td>%s</td></tr>'
                  % (r["total"]["median"], r["per_m"], r["role"]))
            A("</tbody></table></div>")
        A("</div>")
        if ps:
            A('<p class="note">%s</p>' % ps["note"])
        A("</div>")

        # view 3 - value by position
        vf = ctx.get("value_facets")
        A('<div class="vpanel" role="tabpanel" id="sv-value" aria-labelledby="sv-value-t" hidden>')
        if vf:
            A('<div class="facets">')
            for f in vf["panels"]:
                A(scatter(f["title"], f["rows"], vf["mine"]))
            A("</div>")
            A('<p class="note">%s</p>' % vf["note"])
        A("</div>")
        A("</section>")

    # ---- week-by-week plan, tabbed
    if ctx.get("week_tabs"):
        A('<section><div class="shead"><h2>The plan, week by week</h2>'
          '<p>%s</p></div>' % ctx["week_tabs_sub"])
        A('<p class="note" id="planSummary"></p>')
        A('<div id="weekHost">')
        A(week_panels(ctx["week_tabs"], gws))
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
    A("</div>")   # /appBody
    A("<footer><span class=\"eyebrow\">How these numbers are made</span>")
    A('<p class="note">%s</p>' % ctx["method"])
    A("</footer></div>")
    A("<script>%s</script>" % JS)
    A("<script>%s</script>" % TAB_JS)
    if ctx.get("payload"):
        A('<script type="application/json" id="simdata">%s</script>'
          % json.dumps(ctx["payload"], separators=(",", ":")).replace("</", "<\/"))
        A("<script>%s</script>" % ctx["live_js"])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(P))
    return path
