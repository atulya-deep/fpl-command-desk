/* Team-level app: onboarding, squad builder, and full client-side recompute.

   The FPL API sends no CORS header on any endpoint, so a browser cannot fetch
   a visitor's team. Instead the whole eligible player pool ships with the page
   and everything - projections, the rolling plan, the simulation - is computed
   here from whichever squad is loaded. */
(function () {
  var el = document.getElementById("simdata");
  if (!el) return;
  var DATA = JSON.parse(el.textContent);
  var SC = DATA.scoring, P = DATA.players, GWS = DATA.gws;
  var KEY = "fpl-desk-team-v1";
  var BOUNDS = { 2: [3, 5], 3: [2, 5], 4: [1, 3] };
  var SLOTS = { 1: 2, 2: 5, 3: 5, 4: 3 };
  var BUDGET = 100.0, CLUB_CAP = 3;

  var state = load() || null;
  var captains = {}, vices = {}, runs = 3000;

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var s = JSON.parse(raw);
      if (!s || !s.squad || s.squad.length !== 15) return null;
      if (s.squad.some(function (id) { return !P[id]; })) return null;   // pool moved on
      return s;
    } catch (e) { return null; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }

  // ---------------------------------------------------------------- scoring
  var EP = {};
  function ep(id, gw) {
    var k = id + "|" + gw;
    if (k in EP) return EP[k];
    var p = P[id], legs = (p && p.gw[gw]) || [], t = 0;
    for (var i = 0; i < legs.length; i++) {
      var s = legs[i], p60 = p.ps * 0.88;
      t += SC.long * p60 + SC.short * (p.ps - p60);
      t += s.lg * SC.goals[p.et] + s.la * SC.assist;
      t += Math.exp(-s.xga) * SC.cs[p.et] * p60;
      if (SC.conc[p.et]) t += SC.conc[p.et] * (s.xga / 2) * 0.75;
      t += s.pdc * (SC.dc[p.et] || 0) + s.bo;
    }
    EP[k] = t;
    return t;
  }

  function bestXI(ids, gw) {
    var by = { 1: [], 2: [], 3: [], 4: [] };
    ids.forEach(function (id) { if (P[id]) by[P[id].et].push(id); });
    for (var k in by) by[k].sort(function (a, b) { return ep(b, gw) - ep(a, gw); });
    var best = null;
    for (var d = BOUNDS[2][0]; d <= BOUNDS[2][1]; d++) {
      for (var m = BOUNDS[3][0]; m <= BOUNDS[3][1]; m++) {
        var f = 10 - d - m;
        if (f < BOUNDS[4][0] || f > BOUNDS[4][1]) continue;
        if (by[2].length < d || by[3].length < m || by[4].length < f || !by[1].length) continue;
        var xi = by[1].slice(0, 1).concat(by[2].slice(0, d), by[3].slice(0, m), by[4].slice(0, f));
        var tot = xi.reduce(function (s, id) { return s + ep(id, gw); }, 0);
        if (!best || tot > best.t) best = { xi: xi, t: tot, f: [d, m, f] };
      }
    }
    if (!best) return { xi: [], bench: ids.slice(), t: 0, f: null };
    var inXI = {}; best.xi.forEach(function (i) { inXI[i] = 1; });
    best.bench = ids.filter(function (i) { return !inXI[i]; })
                    .sort(function (a, b) { return ep(b, gw) - ep(a, gw); });
    return best;
  }

  function horizon(ids, gwList) {
    var t = 0;
    for (var i = 0; i < gwList.length; i++) {
      var g = gwList[i], s = bestXI(ids, g);
      t += s.t;
      if (s.xi.length) {
        var cap = s.xi.reduce(function (a, b) { return ep(b, g) > ep(a, g) ? b : a; });
        t += ep(cap, g);
      }
    }
    return t;
  }

  // shortlist per position keeps the transfer search quick
  var BYPOS = { 1: [], 2: [], 3: [], 4: [] };
  Object.keys(P).forEach(function (id) { BYPOS[P[id].et].push(+id); });
  for (var et in BYPOS) {
    BYPOS[et].sort(function (a, b) { return P[b].ep - P[a].ep; });
  }

  function clubCounts(ids) {
    var c = {};
    ids.forEach(function (id) { var t = P[id].t; c[t] = (c[t] || 0) + 1; });
    return c;
  }

  function bestSwap(ids, bank, gwList) {
    var base = horizon(ids, gwList), counts = clubCounts(ids), own = {};
    ids.forEach(function (i) { own[i] = 1; });
    var best = null;
    ids.forEach(function (outId) {
      var budget = P[outId].pr + bank;
      var cands = BYPOS[P[outId].et].slice(0, 70);
      for (var i = 0; i < cands.length; i++) {
        var c = cands[i];
        if (own[c] || P[c].pr > budget + 1e-9) continue;
        if (P[c].t !== P[outId].t && (counts[P[c].t] || 0) >= CLUB_CAP) continue;
        if (P[c].ep <= P[outId].ep && P[c].st !== "a") continue;
        var trial = ids.map(function (x) { return x === outId ? c : x; });
        var gain = horizon(trial, gwList) - base;
        if (!best || gain > best.gain) best = { out: outId, inn: c, gain: gain, squad: trial };
      }
    });
    return best;
  }

  function rollingPlan(ids, bank, ft) {
    var cur = ids.slice(), curBank = bank, curFt = ft, out = [];
    for (var i = 0; i < GWS.length; i++) {
      var gw = GWS[i], rest = GWS.slice(i), moves = [], avail = curFt;
      while (avail > 0) {
        var b = bestSwap(cur, curBank, rest);
        if (!b) break;
        var forced = P[b.out].st !== "a";
        if (!forced && b.gain < 2.5) break;
        cur = b.squad;
        curBank = Math.round((curBank + P[b.out].pr - P[b.inn].pr) * 10) / 10;
        moves.push(b);
        avail--;
      }
      var sel = bestXI(cur, gw);
      var cap = sel.xi.length
        ? sel.xi.reduce(function (a, b2) { return ep(b2, gw) > ep(a, gw) ? b2 : a; }) : null;
      var vice = sel.xi.filter(function (x) { return x !== cap; })
                       .sort(function (a, b2) { return ep(b2, gw) - ep(a, gw); })[0];
      var next = Math.min(5, avail + 1);
      out.push({
        gw: gw, moves: moves, squad: cur.slice(), bank: curBank,
        ftBefore: curFt, ftUsed: moves.length, ftNext: next,
        xi: sel.xi, bench: sel.bench, f: sel.f, cap: cap, vice: vice,
        total: sel.t + (cap ? ep(cap, gw) : 0)
      });
      curFt = next;
    }
    return out;
  }

  // ------------------------------------------------------------- simulation
  function mulberry(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function pois(lam, r) {
    if (lam <= 0) return 0;
    var p = 1, k = 0, target = Math.exp(-lam);
    do { p *= r(); if (p <= target) return k; k++; } while (k < 40);
    return k;
  }
  function legal(c) {
    if ((c[1] || 0) !== 1) return false;
    for (var et in BOUNDS) if ((c[et] || 0) < BOUNDS[et][0] || (c[et] || 0) > BOUNDS[et][1]) return false;
    return true;
  }

  function simulate(ids, n) {
    var r = mulberry(20260905), perGW = {}, totals = [], capRet = {}, subs = 0;
    var pp = {};
    GWS.forEach(function (g) { perGW[g] = []; capRet[g] = 0; });
    ids.forEach(function (id) { pp[id] = { tot: [], gw: {} }; GWS.forEach(function (g) { pp[id].gw[g] = []; }); });
    var plan = {};
    GWS.forEach(function (g) { plan[g] = bestXI(ids, g); });

    for (var it = 0; it < n; it++) {
      var runTotal = 0;
      var acc = {}; ids.forEach(function (id) { acc[id] = 0; });
      for (var gi = 0; gi < GWS.length; gi++) {
        var gw = GWS[gi], sel = plan[gw], conc = {};
        ids.forEach(function (id) {
          (P[id].gw[gw] || []).forEach(function (s, i) {
            var key = s.tm + "|" + i;
            if (!(key in conc)) conc[key] = pois(s.xga, r);
          });
        });
        var pts = {}, mins = {};
        ids.forEach(function (id) {
          var o = playerGW(id, gw, conc, r); pts[id] = o[0]; mins[id] = o[1];
        });
        var active = sel.xi.filter(function (id) { return mins[id] > 0; });
        var blanks = sel.xi.filter(function (id) { return mins[id] === 0; });
        var counts = {};
        active.forEach(function (id) { counts[P[id].et] = (counts[P[id].et] || 0) + 1; });
        for (var b = 0; b < blanks.length; b++) {
          for (var s2 = 0; s2 < sel.bench.length; s2++) {
            var sub = sel.bench[s2];
            if (mins[sub] === 0 || active.indexOf(sub) >= 0) continue;
            if ((P[blanks[b]].et === 1) !== (P[sub].et === 1)) continue;
            var trial = {}; for (var k2 in counts) trial[k2] = counts[k2];
            trial[P[sub].et] = (trial[P[sub].et] || 0) + 1;
            var tot = 0; for (var k3 in trial) tot += trial[k3];
            if (legal(trial) || tot < 11) { active.push(sub); counts = trial; subs++; break; }
          }
        }
        var cap = captains[gw] || (sel.xi.length
          ? sel.xi.reduce(function (a, b2) { return ep(b2, gw) > ep(a, gw) ? b2 : a; }) : null);
        if (cap && mins[cap] === 0) {
          var alt = sel.xi.filter(function (id) { return id !== cap && mins[id] > 0; })
                          .sort(function (a, b2) { return ep(b2, gw) - ep(a, gw); })[0];
          if (alt) cap = alt;
        }
        var act = {}; active.forEach(function (id) { act[id] = 1; });
        var gwPts = active.reduce(function (s3, id) { return s3 + pts[id]; }, 0);
        if (cap && act[cap]) { gwPts += pts[cap]; if (pts[cap] >= 6) capRet[gw]++; }
        ids.forEach(function (id) {
          var v = act[id] ? pts[id] : 0;
          if (id === cap && act[id]) v *= 2;
          pp[id].gw[gw].push(v); acc[id] += v;
        });
        perGW[gw].push(gwPts);
        runTotal += gwPts;
      }
      ids.forEach(function (id) { pp[id].tot.push(acc[id]); });
      totals.push(runTotal);
    }
    var out = { perGW: {}, capRet: {}, subs: subs / n, n: n, plan: plan, players: {} };
    GWS.forEach(function (g) { out.perGW[g] = describe(perGW[g]); out.capRet[g] = capRet[g] / n; });
    ids.forEach(function (id) {
      out.players[id] = { total: describe(pp[id].tot), gw: {} };
      GWS.forEach(function (g) { out.players[id].gw[g] = describe(pp[id].gw[g]); });
    });
    out.total = describe(totals);
    return out;
  }

  function playerGW(id, gw, conc, r) {
    var p = P[id], legs = p.gw[gw] || [], total = 0, played = 0;
    for (var i = 0; i < legs.length; i++) {
      var s = legs[i];
      if (r() > p.ps) continue;
      var long = r() < 0.88;
      played++;
      total += long ? SC.long : SC.short;
      total += pois(s.lg, r) * SC.goals[p.et];
      total += pois(s.la, r) * SC.assist;
      var gc = conc[s.tm + "|" + i] || 0;
      if (long && gc === 0) total += SC.cs[p.et];
      if (SC.conc[p.et]) total += SC.conc[p.et] * Math.floor(gc / 2);
      if (p.et === 1) total += Math.floor(pois(s.sv, r) / 3) * SC.save;
      if (SC.dc[p.et] && r() < s.pdc) total += SC.dc[p.et];
      if (r() < s.yc) total += SC.yellow;
      if (r() < s.rc) total += SC.red;
      if (r() < Math.min(s.bo / 2, 0.95)) total += (1 + Math.floor(r() * 3)) * SC.bonus;
    }
    return [total, played];
  }

  function describe(v) {
    v = v.slice().sort(function (a, b) { return a - b; });
    var n = v.length, q = function (f) { return v[Math.min(n - 1, Math.floor(f * n))]; };
    var mean = v.reduce(function (a, b) { return a + b; }, 0) / n;
    return {
      mean: +mean.toFixed(1), median: q(0.5), p10: q(0.10), p25: q(0.25),
      p75: q(0.75), p90: q(0.90), min: v[0], max: v[n - 1],
      sd: +Math.sqrt(v.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n).toFixed(1)
    };
  }

  // ---------------------------------------------------------------- helpers
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };
  function duty(p) {
    var o = "";
    if (p.pen === 1 || p.pen === 2) o += '<span class="sp pen">PEN' + (p.pen === 1 ? "" : "2") + "</span>";
    return o;
  }
  function fixOf(id, gw) {
    var legs = P[id].gw[gw] || [];
    if (!legs.length) return "blank";
    return legs.map(function (l) { return l.opp + " (" + (l.h ? "H" : "A") + ")"; }).join(", ");
  }

  window.FPLDesk = { get squad() { return state ? state.squad : []; }, simulate: simulate, P: P };

  // -------------------------------------------------------------- rendering
  function armbands(w) {
    // a captain or vice chosen on the pitch overrides the planner's pick
    if (captains[w.gw] && w.xi.indexOf(captains[w.gw]) >= 0) w.cap = captains[w.gw];
    if (vices[w.gw] && w.xi.indexOf(vices[w.gw]) >= 0 && vices[w.gw] !== w.cap) w.vice = vices[w.gw];
    else if (w.vice === w.cap || w.xi.indexOf(w.vice) < 0) {
      w.vice = w.xi.filter(function (x) { return x !== w.cap; })
                   .sort(function (a, b) { return ep(b, w.gw) - ep(a, w.gw); })[0];
    }
    w.total = w.xi.reduce(function (t, id) { return t + ep(id, w.gw); }, 0) + (w.cap ? ep(w.cap, w.gw) : 0);
  }

  function pitchHTML(w) {
    var base = {}; state.squad.forEach(function (i) { base[i] = 1; });
    function chip(id) {
      var arm = id === w.cap ? '<span class="arm">C</span>' : (id === w.vice ? '<span class="arm v">V</span>' : "");
      var nw = base[id] ? "" : '<span class="new">IN</span>';
      return '<button class="chip" type="button" data-id="' + id + '" data-gw="' + w.gw +
        '" aria-label="' + esc(P[id].n) + '">' + nw + arm + '<span class="nm">' + esc(P[id].n) +
        '</span><span class="fx">' + esc(fixOf(id, w.gw)) + '</span><span class="pt">' +
        ep(id, w.gw).toFixed(1) + "</span></button>";
    }
    var lines = [1, 2, 3, 4].map(function (et) {
      return '<div class="pline">' + w.xi.filter(function (id) { return P[id].et === et; })
        .map(chip).join("") + "</div>";
    }).join("");
    var bench = '<div class="pbench"><span class="lbl">BENCH</span>' + w.bench.map(chip).join("") + "</div>";
    return '<div class="pitch">' + lines + bench + '</div><div class="actHost" data-gw="' + w.gw + '"></div>';
  }

  function renderWeeks(plan) {
    var host = $("#weekHost");
    if (!host) return;
    plan.forEach(armbands);
    var prev = host.querySelector('[role="tab"][aria-selected="true"]');
    var keepGw = prev ? +prev.id.replace("tb", "") : null;
    var vmax = 1;
    plan.forEach(function (w) {
      w.squad.forEach(function (id) { vmax = Math.max(vmax, ep(id, w.gw)); });
    });
    var tabs = ['<div class="tabs" role="tablist" aria-label="Gameweek plan">'];
    plan.forEach(function (w, i) {
      tabs.push('<button class="tab" role="tab" id="tb' + w.gw + '" aria-controls="tp' + w.gw +
        '" aria-selected="' + (i === 0) + '" tabindex="' + (i === 0 ? 0 : -1) + '" type="button">GW' +
        w.gw + '<span class="sub">' + (w.ftUsed ? w.ftUsed + " transfer" + (w.ftUsed === 1 ? "" : "s") : "bank") +
        "</span></button>");
    });
    tabs.push("</div>");

    plan.forEach(function (w, i) {
      var o = ['<div class="panel" role="tabpanel" id="tp' + w.gw + '" aria-labelledby="tb' + w.gw +
               '"' + (i === 0 ? "" : " hidden") + "><div>"];
      o.push('<div class="act' + (w.moves.length ? "" : " bank") + '"><div class="hd">' +
        (w.moves.length ? "Make " + w.ftUsed + " transfer" + (w.ftUsed === 1 ? "" : "s") : "Bank the transfer") +
        '</div><div class="sm">' +
        (w.moves.length ? "Free &mdash; you have " + w.ftBefore + " banked."
                        : "Nothing clears the bar this week.") + "</div>");
      w.moves.forEach(function (m) {
        o.push('<div class="mv"><span class="o">' + esc(P[m.out].n) + '</span><span>&rarr;</span>' +
          '<span class="pname">' + esc(P[m.inn].n) + '</span><span class="tm">' + esc(P[m.inn].t) +
          '</span><span class="g">+' + m.gain.toFixed(0) + "</span></div>");
      });
      o.push("</div>");

      o.push(pitchHTML(w));
      o.push('<div class="xi">');
      [[1, "Goalkeeper"], [2, "Defenders"], [3, "Midfielders"], [4, "Forwards"]].forEach(function (g) {
        var members = w.xi.filter(function (id) { return P[id].et === g[0]; })
          .map(function (id) { return [id, false]; })
          .concat(w.bench.filter(function (id) { return P[id].et === g[0]; })
            .map(function (id) { return [id, true]; }));
        if (!members.length) return;
        o.push('<div class="grp">' + g[1] + "</div>");
        members.forEach(function (mm) {
          var id = mm[0], benched = mm[1], pts = ep(id, w.gw);
          var arm = id === w.cap ? '<span class="arm c">C</span>'
                  : (id === w.vice ? '<span class="arm v">V</span>' : "");
          o.push('<div class="pl' + (benched ? " benched" : "") + '"><span><span class="pname">' +
            esc(P[id].n) + '</span><span class="tm">' + esc(P[id].t) + "</span>" + duty(P[id]) + " " + arm +
            '</span><span class="fx">' + esc(fixOf(id, w.gw)) + '</span>' +
            '<span class="mini"><span style="width:' + Math.min(100, pts / vmax * 100).toFixed(0) +
            '%"></span></span><span class="pt">' + pts.toFixed(1) + "</span></div>");
        });
      });
      o.push("</div></div>");

      var d = w.dist, lo = w.distLo, hi = w.distHi, span = Math.max(hi - lo, 1);
      var x = function (v) { return Math.max(0, Math.min(100, (v - lo) / span * 100)); };
      o.push('<div class="rail"><div class="card"><h3>Simulated GW' + w.gw + '</h3><div class="big">' +
        d.median + '</div><div class="sm">median &middot; 80% land between ' + d.p10 + " and " + d.p90 +
        '</div><div class="spread"><span class="b" style="left:' + x(d.p10).toFixed(1) + "%;width:" +
        (x(d.p90) - x(d.p10)).toFixed(1) + '%"></span><span class="m" style="left:' +
        x(d.median).toFixed(1) + '%"></span></div></div>');
      o.push('<div class="card"><h3>Transfer balance</h3>');
      [["Free transfers", w.ftBefore], ["Used", w.ftUsed], ["Into GW" + (w.gw + 1), w.ftNext],
       ["In the bank", "£" + w.bank.toFixed(1)],
       ["Captain", w.cap ? P[w.cap].n : "-"],
       ["Formation", w.f ? w.f.join("-") : "-"]].forEach(function (kv) {
        o.push('<div class="kv"><span>' + esc(kv[0]) + "</span><b>" + esc(kv[1]) + "</b></div>");
      });
      o.push("</div></div></div>");
      tabs.push(o.join(""));
    });
    host.innerHTML = tabs.join("");
    wireTabs(host);
    if (keepGw !== null) { var kt = host.querySelector("#tb" + keepGw); if (kt) kt.click(); }
    wirePitch(host, plan);
  }

  // ---------------------------------------------------------- pitch actions
  function wirePitch(host, plan) {
    host.querySelectorAll(".chip").forEach(function (ch) {
      ch.addEventListener("click", function () {
        host.querySelectorAll(".chip.sel").forEach(function (x) { x.classList.remove("sel"); });
        ch.classList.add("sel");
        showActions(host, plan, +ch.dataset.gw, +ch.dataset.id);
      });
    });
  }

  function showActions(host, plan, gw, id) {
    var w = plan.filter(function (x) { return x.gw === gw; })[0];
    var ah = host.querySelector('.actHost[data-gw="' + gw + '"]');
    if (!w || !ah) return;
    var inBase = state.squad.indexOf(id) >= 0, inXI = w.xi.indexOf(id) >= 0;
    var last = GWS[GWS.length - 1];
    var o = ['<div class="actp"><div class="who"><b>' + esc(P[id].n) + '</b><span class="tm">' +
      esc(P[id].t) + '</span><span class="pos">' + P[id].pos + '</span><span class="fx">' +
      esc(fixOf(id, gw)) + " &middot; " + ep(id, gw).toFixed(1) + " pts &middot; &pound;" +
      P[id].pr.toFixed(1) + "</span></div>"];
    o.push('<div class="btns">');
    if (inXI) {
      o.push('<button class="tg" type="button" data-act="cap">Captain for GW' + gw + "</button>");
      o.push('<button class="tg" type="button" data-act="vice">Vice for GW' + gw + "</button>");
    }
    o.push('<button class="tg" type="button" data-act="close">Close</button></div>');

    if (inBase) {
      var budget = P[id].pr + state.bank, counts = clubCounts(state.squad), own = {};
      state.squad.forEach(function (i) { own[i] = 1; });
      var rest = GWS.slice(GWS.indexOf(gw)), baseV = horizon(state.squad, rest);
      var alts = BYPOS[P[id].et].filter(function (c) {
        if (own[c] || P[c].pr > budget + 1e-9) return false;
        if (P[c].t !== P[id].t && (counts[P[c].t] || 0) >= CLUB_CAP) return false;
        return true;
      }).slice(0, 40).map(function (c) {
        var trial = state.squad.map(function (x) { return x === id ? c : x; });
        return { id: c, gain: horizon(trial, rest) - baseV };
      }).sort(function (a, b) { return b.gain - a.gain; }).slice(0, 24);
      o.push('<div style="font-size:12px;color:var(--ink-3)">Swap for &mdash; gain over GW' + gw +
        "&ndash;" + last + ", within &pound;" + budget.toFixed(1) + "</div>");
      o.push('<div class="alts">' + alts.map(function (a) {
        return '<button class="alt" type="button" data-act="swap" data-in="' + a.id + '"><span class="pname">' +
          esc(P[a.id].n) + '</span><span class="tm">' + esc(P[a.id].t) + '</span><span class="p">&pound;' +
          P[a.id].pr.toFixed(1) + '</span><span class="d">' + (a.gain >= 0 ? "+" : "") + a.gain.toFixed(0) +
          "</span></button>";
      }).join("") + "</div>");
    } else {
      o.push('<div style="font-size:12px;color:var(--ink-3)">Brought in by a planned transfer. Swaps act on ' +
        "the squad you hold today &mdash; pick a player without the IN tag, or edit the squad above.</div>");
    }
    o.push("</div>");
    ah.innerHTML = o.join("");
    ah.querySelectorAll("[data-act]").forEach(function (b) {
      b.addEventListener("click", function () {
        var act = b.dataset.act;
        if (act === "close") {
          ah.innerHTML = "";
          host.querySelectorAll(".chip.sel").forEach(function (x) { x.classList.remove("sel"); });
        } else if (act === "cap") {
          captains[gw] = id; if (vices[gw] === id) delete vices[gw]; recompute();
        } else if (act === "vice") {
          vices[gw] = id; if (captains[gw] === id) delete captains[gw]; recompute();
        } else if (act === "swap") {
          var inn = +b.dataset["in"], i = state.squad.indexOf(id);
          if (i >= 0) {
            state.squad[i] = inn;
            state.bank = +(state.bank + P[id].pr - P[inn].pr).toFixed(1);
            captains = {}; vices = {}; save(); wireSwap(); recompute();
          }
        }
      });
    });
    ah.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function renderPlayers(res, ids) {
    var host = $("#playerHost");
    if (!host) return;
    var vmax = 1;
    ids.forEach(function (id) {
      GWS.forEach(function (g) { vmax = Math.max(vmax, res.players[id].gw[g].p90); });
    });
    var rows = ids.slice().sort(function (a, b) {
      return P[a].et - P[b].et || res.players[b].total.median - res.players[a].total.median;
    });
    var o = ['<div class="tw"><table class="pgrid"><thead><tr><th>Player</th><th>Pos</th>' +
             '<th class="n">&pound;</th>'];
    GWS.forEach(function (g) { o.push('<th style="text-align:center">GW' + g + "</th>"); });
    o.push('<th class="n">5&#8209;GW</th><th class="n">Per &pound;m</th></tr></thead><tbody>');
    rows.forEach(function (id) {
      var d = res.players[id];
      o.push("<tr><td><span class='pname'>" + esc(P[id].n) + "</span><span class='tm'>" +
        esc(P[id].t) + "</span>" + duty(P[id]) + "</td><td><span class='pos'>" + P[id].pos +
        "</span></td><td class='n'>" + P[id].pr.toFixed(1) + "</td>");
      GWS.forEach(function (g) {
        var c = d.gw[g];
        if (!c || c.p90 <= 0) { o.push('<td><div class="pcell zero"><b>0</b></div></td>'); return; }
        var w = function (v) { return Math.max(0, Math.min(100, v / vmax * 100)); };
        o.push('<td><div class="pcell"><span class="rng" style="left:' + w(c.p10).toFixed(1) +
          "%;width:" + Math.max(w(c.p90) - w(c.p10), 1.5).toFixed(1) + '%"></span>' +
          '<span class="med" style="left:' + w(c.median).toFixed(1) + '%"></span><b>' +
          c.median + "</b></div></td>");
      });
      o.push("<td class='n'>" + d.total.median + "</td><td class='vpm'>" +
        (d.total.median / P[id].pr).toFixed(1) + "</td></tr>");
    });
    o.push("</tbody></table></div>");
    host.innerHTML = o.join("");
  }

  function renderDist(res) {
    var host = $("#liveRows");
    if (!host) return;
    var lo = Infinity, hi = -Infinity;
    GWS.forEach(function (g) { lo = Math.min(lo, res.perGW[g].p10); hi = Math.max(hi, res.perGW[g].p90); });
    lo -= 4; hi += 4;
    var span = Math.max(hi - lo, 1), x = function (v) { return Math.max(0, Math.min(100, (v - lo) / span * 100)); };
    host.innerHTML = GWS.map(function (g) {
      var d = res.perGW[g], sel = res.plan[g];
      var cap = captains[g] || (sel.xi.length ? sel.xi.reduce(function (a, b) {
        return ep(b, g) > ep(a, g) ? b : a; }) : null);
      var opts = sel.xi.slice().sort(function (a, b) { return ep(b, g) - ep(a, g); })
        .map(function (id) {
          return '<option value="' + id + '"' + (id === cap ? " selected" : "") + ">" + esc(P[id].n) + "</option>";
        }).join("");
      return '<div class="drow"><span class="gwlab">GW' + g + '</span><div class="track">' +
        '<span class="axis"></span><span class="band" style="left:' + x(d.p10).toFixed(1) + "%;width:" +
        (x(d.p90) - x(d.p10)).toFixed(1) + '%"></span><span class="iqr" style="left:' +
        x(d.p25).toFixed(1) + "%;width:" + (x(d.p75) - x(d.p25)).toFixed(1) + '%"></span>' +
        '<span class="med" style="left:' + x(d.median).toFixed(1) + '%"></span>' +
        '<span class="cap" style="left:' + x(d.p10).toFixed(1) + '%">' + d.p10 + "</span>" +
        '<span class="cap" style="left:' + Math.min(x(d.p90), 94).toFixed(1) + '%">' + d.p90 +
        '</span></div><span class="dnum"><b>' + d.median + "</b> ±" + d.sd + "</span>" +
        '<select class="capsel" data-gw="' + g + '" aria-label="Captain for gameweek ' + g + '">' +
        opts + "</select></div>";
    }).join("");
    host.querySelectorAll(".capsel").forEach(function (s) {
      s.addEventListener("change", function () { captains[+s.dataset.gw] = +s.value; recompute(); });
    });
  }

  function wireTabs(scope) {
    (scope || document).querySelectorAll('[role="tablist"]').forEach(function (bar) {
      var tabs = [].slice.call(bar.querySelectorAll('[role="tab"]'));
      function show(i) {
        tabs.forEach(function (t, j) {
          var on = i === j, pnl = document.getElementById(t.getAttribute("aria-controls"));
          t.setAttribute("aria-selected", String(on));
          t.tabIndex = on ? 0 : -1;
          if (pnl) pnl.hidden = !on;
        });
      }
      tabs.forEach(function (t, i) {
        t.addEventListener("click", function () { show(i); });
        t.addEventListener("keydown", function (e) {
          var n = null;
          if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
          else if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
          else if (e.key === "Home") n = 0;
          else if (e.key === "End") n = tabs.length - 1;
          if (n !== null) { e.preventDefault(); show(n); tabs[n].focus(); }
        });
      });
    });
  }

  // ------------------------------------------------------------- recompute
  function recompute() {
    var btn = $("#liveRun");
    document.body.classList.add("busy");
    if (btn) { btn.disabled = true; btn.textContent = "Working…"; }
    setTimeout(function () {
      var ids = state.squad;
      var res = simulate(ids, runs);
      renderDist(res);
      renderPlayers(res, ids);

      var plan = rollingPlan(ids, state.bank, state.ft);
      var lo = Infinity, hi = -Infinity;
      plan.forEach(function (w) {
        var s = simulate(w.squad, 600);
        w.dist = s.perGW[w.gw];
        lo = Math.min(lo, w.dist.p10); hi = Math.max(hi, w.dist.p90);
      });
      plan.forEach(function (w) { w.distLo = lo - 4; w.distHi = hi + 4; });
      renderWeeks(plan);

      var t = res.total, caps = GWS.map(function (g) { return Math.round(res.capRet[g] * 100); });
      set("liveHead", t.median, "median over GW" + GWS[0] + "&ndash;" + GWS[GWS.length - 1]);
      set("liveRange", t.p10 + "&ndash;" + t.p90, "80% of " + res.n.toLocaleString() + " runs");
      set("liveCap", Math.min.apply(null, caps) + "&ndash;" + Math.max.apply(null, caps) + "%",
          "captain returns 6+");
      set("liveSubs", res.subs.toFixed(1), "auto-subs per five weeks");
      var rt = plan.reduce(function (s, w) { return s + w.total; }, 0);
      var hdr = $("#planSummary");
      if (hdr) hdr.innerHTML = "Following this route projects <b>" + rt.toFixed(0) +
        " points</b> across GW" + GWS[0] + "&ndash;" + GWS[GWS.length - 1] +
        ", against <b>" + horizon(ids, GWS).toFixed(0) + "</b> for standing still.";
      if (btn) { btn.disabled = false; btn.textContent = "Re-run"; }
      document.body.classList.remove("busy");
    }, 10);
  }
  function set(id, v, s) {
    var e = document.getElementById(id);
    if (e) e.innerHTML = '<span class="v">' + v + '</span><span class="s">' + s + "</span>";
  }

  // ------------------------------------------------------------- onboarding
  function startScreen() {
    var o = $("#startScreen");
    if (!o) return;
    o.hidden = false;
    $("#appBody").hidden = true;
    $("#usePublished").addEventListener("click", function () {
      state = { squad: DATA.squad.slice(), bank: DATA.bank, ft: DATA.ft,
                teamId: DATA.provenance.team_id, source: "published" };
      save(); boot();
    });
    $("#startBuild").addEventListener("click", function () { openBuilder(); });
    $("#startById").addEventListener("click", function () { openById(); });
  }

  // ------------------------------------------------------- load by team id
  function picksUrl(id) {
    return "https://fantasy.premierleague.com/api/entry/" + id + "/event/" +
           (DATA.current_gw || 1) + "/picks/";
  }

  function openById(fromApp) {
    var st = $("#startScreen"), bd = $("#builder"), by = $("#byId");
    if (st) st.hidden = false;
    if (bd) bd.hidden = true;
    if (fromApp) $("#appBody").hidden = true;
    by.hidden = false;
    by.scrollIntoView({ block: "center", behavior: "smooth" });

    var input = $("#tidInput"), link = $("#tidLink"), msg = $("#tidMsg");
    function syncLink() {
      var id = (input.value || "").replace(/[^0-9]/g, "");
      if (id) {
        link.href = picksUrl(id);
        link.setAttribute("aria-disabled", "false");
      } else {
        link.href = "#";
        link.setAttribute("aria-disabled", "true");
      }
    }
    input.oninput = syncLink;
    syncLink();
    input.focus();

    $("#tidBack").onclick = function () {
      by.hidden = true;
      msg.className = "msg";
      if (state) { $("#startScreen").hidden = true; $("#appBody").hidden = false; }
    };
    $("#tidLoad").onclick = function () { loadPasted(input, msg); };
  }

  function say(msg, text, ok) {
    msg.className = "msg show " + (ok ? "ok" : "err");
    msg.innerHTML = text;
  }

  function loadPasted(input, msg) {
    var id = (input.value || "").replace(/[^0-9]/g, "");
    var raw = ($("#tidPaste").value || "").trim();
    if (!raw) return say(msg, "Nothing pasted yet. Open your team data, select it all, and paste it in.", false);

    var data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      // tolerate a page copied with surrounding text
      var a = raw.indexOf("{"), b = raw.lastIndexOf("}");
      if (a < 0 || b <= a) return say(msg, "That does not look like team data. Paste everything from the tab that opened.", false);
      try { data = JSON.parse(raw.slice(a, b + 1)); }
      catch (e2) { return say(msg, "That did not parse. Make sure you copied the whole thing.", false); }
    }

    if (data && data.picks === undefined && data.summary_overall_points !== undefined) {
      return say(msg, "That is your team's summary, not its squad. Use the <b>Open my team data</b> " +
                      "button, which points at the picks for GW" + (DATA.current_gw || 1) + ".", false);
    }
    if (!data || !Array.isArray(data.picks) || !data.picks.length) {
      return say(msg, "No squad found in that. It should start with <code>{\"active_chip\"</code> " +
                      "and contain a <code>picks</code> list.", false);
    }

    var ids = data.picks.map(function (x) { return x.element; });
    var missing = ids.filter(function (i) { return !P[i]; });
    if (ids.length !== 15) {
      return say(msg, "Found " + ids.length + " players, expected 15. Paste the whole thing.", false);
    }
    if (missing.length) {
      return say(msg, missing.length + " of those players are not in this build&rsquo;s pool " +
                      "(they may have left the league). Try again after the next refresh, or build the squad by hand.", false);
    }

    var bank = 0;
    if (data.entry_history && typeof data.entry_history.bank === "number") {
      bank = data.entry_history.bank / 10;
    }
    // free transfers are not in this payload; assume one and let the user adjust by re-planning
    state = { squad: ids, bank: bank, ft: 1, teamId: id || null, source: "pasted" };
    captains = {}; vices = {};
    save();
    say(msg, "Loaded 15 players" + (id ? " for team " + id : "") + ", &pound;" + bank.toFixed(1) +
             " in the bank. Building your plan&hellip;", true);
    setTimeout(function () {
      $("#byId").hidden = true;
      $("#tidPaste").value = "";
      msg.className = "msg";
      boot();
    }, 700);
  }

  function openBuilder() {
    $("#startScreen").hidden = true;
    $("#builder").hidden = false;
    var picked = [], filterEt = 1, search = "", sort = "ep";

    function counts() {
      var c = { 1: 0, 2: 0, 3: 0, 4: 0 };
      picked.forEach(function (id) { c[P[id].et]++; });
      return c;
    }
    function spend() { return picked.reduce(function (s, id) { return s + P[id].pr; }, 0); }
    function clubs() { return clubCounts(picked); }

    function paint() {
      var c = counts(), sp = spend(), left = BUDGET - sp;
      $("#bStats").innerHTML =
        [["Budget left", "£" + left.toFixed(1)], ["Picked", picked.length + "/15"],
         ["GK", c[1] + "/2"], ["DEF", c[2] + "/5"], ["MID", c[3] + "/5"], ["FWD", c[4] + "/3"]]
        .map(function (k) {
          return '<div class="kpi"><span class="eyebrow">' + k[0] + '</span><span class="v" style="font-size:20px">' +
                 k[1] + "</span></div>";
        }).join("");
      var ok = picked.length === 15 && left >= -1e-9 &&
               c[1] === 2 && c[2] === 5 && c[3] === 5 && c[4] === 3;
      var go = $("#bDone");
      go.disabled = !ok;
      go.textContent = ok ? "Use this squad" : "Pick " + (15 - picked.length) + " more";

      var cl = clubs();
      var list = BYPOS[filterEt].filter(function (id) {
        return !search || P[id].n.toLowerCase().indexOf(search) >= 0 ||
               P[id].t.toLowerCase().indexOf(search) >= 0;
      });
      if (sort === "price") list = list.slice().sort(function (a, b) { return P[b].pr - P[a].pr; });
      else if (sort === "value") list = list.slice().sort(function (a, b) { return P[b].ep / P[b].pr - P[a].ep / P[a].pr; });
      $("#bList").innerHTML = list.slice(0, 120).map(function (id) {
        var on = picked.indexOf(id) >= 0;
        var full = !on && (c[P[id].et] >= SLOTS[P[id].et] || P[id].pr > left + 1e-9 ||
                           (cl[P[id].t] || 0) >= CLUB_CAP);
        return '<button class="prow' + (on ? " on" : "") + '" type="button" data-id="' + id + '"' +
          (full ? " disabled" : "") + '><span class="pname">' + esc(P[id].n) +
          '</span><span class="tm">' + esc(P[id].t) + "</span>" + duty(P[id]) +
          '<span class="bp">£' + P[id].pr.toFixed(1) + '</span><span class="be">' +
          P[id].ep.toFixed(0) + "</span></button>";
      }).join("") || '<p class="note">Nothing matches.</p>';
      $("#bList").querySelectorAll(".prow").forEach(function (b) {
        b.addEventListener("click", function () {
          var id = +b.dataset.id, i = picked.indexOf(id);
          if (i >= 0) picked.splice(i, 1); else picked.push(id);
          paint();
        });
      });
    }

    $("#builder").querySelectorAll("[data-et]").forEach(function (b) {
      b.addEventListener("click", function () {
        filterEt = +b.dataset.et;
        $("#builder").querySelectorAll("[data-et]").forEach(function (x) {
          x.setAttribute("aria-pressed", String(x === b));
        });
        paint();
      });
    });
    $("#bSearch").addEventListener("input", function (e) { search = e.target.value.toLowerCase(); paint(); });
    $("#bSort").addEventListener("change", function (e) { sort = e.target.value; paint(); });
    $("#bAuto").addEventListener("click", function () {
      picked = autoPick(); paint();
    });
    $("#bClear").addEventListener("click", function () { picked = []; paint(); });
    $("#bDone").addEventListener("click", function () {
      state = { squad: picked.slice(), bank: +(BUDGET - spend()).toFixed(1), ft: 1, source: "custom" };
      save();
      $("#builder").hidden = true;
      boot();
    });
    paint();
  }

  function autoPick() {
    // greedy on points per million, leaving room for the cheapest remaining slots
    var need = { 1: 2, 2: 5, 3: 5, 4: 3 }, have = { 1: 0, 2: 0, 3: 0, 4: 0 };
    var floor = {}; for (var et in need) floor[et] = Math.min.apply(null, BYPOS[et].map(function (i) { return P[i].pr; }));
    var order = Object.keys(P).map(Number).sort(function (a, b) { return P[b].ep / P[b].pr - P[a].ep / P[a].pr; });
    var out = [], spent = 0, cl = {};
    order.forEach(function (id) {
      var et = P[id].et;
      if (have[et] >= need[et] || (cl[P[id].t] || 0) >= CLUB_CAP) return;
      var rest = 0;
      for (var q in need) rest += (need[q] - have[q]) * floor[q];
      rest -= floor[et];
      if (spent + P[id].pr + rest > BUDGET) return;
      out.push(id); have[et]++; spent += P[id].pr; cl[P[id].t] = (cl[P[id].t] || 0) + 1;
    });
    for (var et2 in need) {
      while (have[et2] < need[et2]) {
        var added = false;
        var pool = BYPOS[et2].slice().sort(function (a, b) { return P[a].pr - P[b].pr; });
        for (var i = 0; i < pool.length; i++) {
          var id2 = pool[i];
          if (out.indexOf(id2) >= 0 || (cl[P[id2].t] || 0) >= CLUB_CAP) continue;
          if (spent + P[id2].pr > BUDGET) continue;
          out.push(id2); have[et2]++; spent += P[id2].pr;
          cl[P[id2].t] = (cl[P[id2].t] || 0) + 1; added = true; break;
        }
        if (!added) break;
      }
    }
    return out;
  }

  // ------------------------------------------------------------------- boot
  function boot() {
    $("#startScreen").hidden = true;
    $("#builder").hidden = true;
    $("#appBody").hidden = false;
    var badge = $("#teamBadge");
    if (badge) {
      if (state.source === "published") {
        badge.innerHTML = "Showing FPL team <b>" + esc(state.teamId) + "</b>, synced server-side.";
      } else if (state.source === "pasted") {
        badge.innerHTML = "Showing FPL team <b>" + esc(state.teamId || "?") +
          "</b>, loaded from data you pasted. Saved in this browser &mdash; paste again after you " +
          "make a transfer.";
      } else {
        badge.innerHTML = "Showing a squad you built here. Saved in this browser only.";
      }
    }
    wireTabs(document);
    var rs = $("#liveRuns");
    if (rs) rs.onchange = function () { runs = +rs.value; recompute(); };
    var br = $("#liveRun"); if (br) br.onclick = recompute;
    var lb = $("#loadById");
    if (lb) lb.onclick = function () { openById(true); };
    var rb = $("#rebuildTeam");
    if (rb) rb.onclick = function () { openBuilder(); };
    var sw = $("#switchTeam");
    if (sw) sw.onclick = function () {
      try { localStorage.removeItem(KEY); } catch (e) {}
      state = null; $("#appBody").hidden = true; startScreen();
    };
    wireSwap();
    recompute();
  }

  function wireSwap() {
    var outSel = $("#swapOut"), inSel = $("#swapIn"), go = $("#liveSwap"), reset = $("#liveReset");
    if (!outSel) return;
    function fill() {
      outSel.innerHTML = state.squad.map(function (id) {
        return '<option value="' + id + '">' + esc(P[id].n) + " (" + P[id].pos + ")</option>";
      }).join("");
      var etOut = P[+outSel.value].et, own = {};
      state.squad.forEach(function (i) { own[i] = 1; });
      inSel.innerHTML = BYPOS[etOut].filter(function (id) { return !own[id]; }).slice(0, 60)
        .map(function (id) {
          return '<option value="' + id + '">' + esc(P[id].n) + " · £" +
                 P[id].pr.toFixed(1) + " · " + P[id].ep.toFixed(0) + "</option>";
        }).join("");
    }
    fill();
    outSel.onchange = fill;
    go.onclick = function () {
      var i = state.squad.indexOf(+outSel.value);
      if (i >= 0 && inSel.value) {
        state.squad[i] = +inSel.value;
        state.bank = +(state.bank + P[+outSel.value].pr - P[+inSel.value].pr).toFixed(1);
        captains = {}; save(); fill(); recompute();
      }
    };
    if (reset) reset.onclick = function () {
      state.squad = DATA.squad.slice(); state.bank = DATA.bank; captains = {};
      save(); fill(); recompute();
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (state) boot(); else startScreen();
  });
})();
