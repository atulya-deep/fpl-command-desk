/* Live Monte Carlo, run in the reader's browser.
   A direct port of fpl_sim.py: shared clean sheets per club, auto-substitutions,
   vice-captain fallback. The FPL API sends no CORS header, so the parameters are
   shipped with the page and resampled here rather than fetched live. */
(function () {
  var el = document.getElementById("simdata");
  if (!el) return;
  var DATA = JSON.parse(el.textContent);
  var SC = DATA.scoring;
  var P = DATA.players, GWS = DATA.gws;

  var squad = DATA.squad.slice();
  var captains = {};            // gw -> player id, null means "best projected"
  var runs = 3000;

  // ---- rng: seeded so a re-run with identical settings is reproducible
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

  var BOUNDS = { 2: [3, 5], 3: [2, 5], 4: [1, 3] };
  function bestXI(ids, gw) {
    var by = { 1: [], 2: [], 3: [], 4: [] };
    ids.forEach(function (id) { by[P[id].et].push(id); });
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
    if (!best) return { xi: [], bench: [], f: null };
    var inXI = {}; best.xi.forEach(function (i) { inXI[i] = 1; });
    var bench = ids.filter(function (i) { return !inXI[i]; })
                   .sort(function (a, b) { return ep(b, gw) - ep(a, gw); });
    return { xi: best.xi, bench: bench, f: best.f };
  }

  // deterministic expected points, used only for ordering the XI and bench
  function ep(id, gw) {
    var legs = P[id].gw[gw] || [], p = P[id], t = 0;
    for (var i = 0; i < legs.length; i++) {
      var s = legs[i], p60 = p.ps * 0.88;
      t += SC.long * p60 + SC.short * (p.ps - p60);
      t += s.lg * SC.goals[p.et] + s.la * SC.assist;
      t += Math.exp(-s.xga) * SC.cs[p.et] * p60;
      if (SC.conc[p.et]) t += SC.conc[p.et] * (s.xga / 2) * 0.75;
      t += s.pdc * (SC.dc[p.et] || 0) + s.bo;
    }
    return t;
  }

  function legal(c) {
    if ((c[1] || 0) !== 1) return false;
    for (var et in BOUNDS) if ((c[et] || 0) < BOUNDS[et][0] || (c[et] || 0) > BOUNDS[et][1]) return false;
    return true;
  }

  function simulate(ids, n) {
    var r = mulberry(20260905);
    var perGW = {}, totals = [], capRet = {}, subs = 0;
    GWS.forEach(function (g) { perGW[g] = []; capRet[g] = 0; });
    var plan = {};
    GWS.forEach(function (g) { plan[g] = bestXI(ids, g); });

    for (var it = 0; it < n; it++) {
      var runTotal = 0;
      for (var gi = 0; gi < GWS.length; gi++) {
        var gw = GWS[gi], sel = plan[gw];
        // one conceded draw per club per fixture, shared by team-mates
        var conc = {};
        ids.forEach(function (id) {
          (P[id].gw[gw] || []).forEach(function (s, i) {
            var key = s.tm + "|" + i;
            if (!(key in conc)) conc[key] = pois(s.xga, r);
          });
        });
        var pts = {}, mins = {};
        ids.forEach(function (id) {
          var out = playerGW(id, gw, conc, r);
          pts[id] = out[0]; mins[id] = out[1];
        });

        var active = sel.xi.filter(function (id) { return mins[id] > 0; });
        var blanks = sel.xi.filter(function (id) { return mins[id] === 0; });
        var counts = {};
        active.forEach(function (id) { counts[P[id].et] = (counts[P[id].et] || 0) + 1; });
        for (var b = 0; b < blanks.length; b++) {
          for (var s2 = 0; s2 < sel.bench.length; s2++) {
            var sub = sel.bench[s2];
            if (mins[sub] === 0 || active.indexOf(sub) >= 0) continue;
            var needGK = P[blanks[b]].et === 1;
            if (needGK !== (P[sub].et === 1)) continue;
            var trial = {}; for (var k2 in counts) trial[k2] = counts[k2];
            trial[P[sub].et] = (trial[P[sub].et] || 0) + 1;
            var total = 0; for (var k3 in trial) total += trial[k3];
            if (legal(trial) || total < 11) { active.push(sub); counts = trial; subs++; break; }
          }
        }

        var cap = captains[gw] || (sel.xi.length ? sel.xi.slice().sort(function (a, c) {
          return ep(c, gw) - ep(a, gw);
        })[0] : null);
        if (cap && mins[cap] === 0) {
          var alt = sel.xi.filter(function (id) { return id !== cap && mins[id] > 0; })
                          .sort(function (a, c) { return ep(c, gw) - ep(a, gw); })[0];
          if (alt) cap = alt;
        }
        var gwPts = active.reduce(function (s3, id) { return s3 + pts[id]; }, 0);
        if (cap && active.indexOf(cap) >= 0) {
          gwPts += pts[cap];
          if (pts[cap] >= 6) capRet[gw]++;
        }
        perGW[gw].push(gwPts);
        runTotal += gwPts;
      }
      totals.push(runTotal);
    }
    var out = { perGW: {}, capRet: {}, subs: subs / n, n: n };
    GWS.forEach(function (g) { out.perGW[g] = describe(perGW[g]); out.capRet[g] = capRet[g] / n; });
    out.total = describe(totals);
    out.plan = plan;
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

  // ---------------------------------------------------------------- rendering
  var $ = function (s) { return document.querySelector(s); };
  function render(res) {
    var lo = Infinity, hi = -Infinity;
    GWS.forEach(function (g) {
      lo = Math.min(lo, res.perGW[g].p10); hi = Math.max(hi, res.perGW[g].p90);
    });
    lo -= 4; hi += 4;
    var span = Math.max(hi - lo, 1);
    var x = function (v) { return Math.max(0, Math.min(100, (v - lo) / span * 100)); };

    var rows = GWS.map(function (g) {
      var d = res.perGW[g], sel = res.plan[g];
      var cap = captains[g] || (sel.xi.slice().sort(function (a, b) { return ep(b, g) - ep(a, g); })[0]);
      var opts = sel.xi.slice().sort(function (a, b) { return ep(b, g) - ep(a, g); })
        .map(function (id) {
          return '<option value="' + id + '"' + (id === cap ? " selected" : "") + ">" +
                 P[id].n + "</option>";
        }).join("");
      return '<div class="drow"><span class="gwlab">GW' + g + "</span>" +
        '<div class="track"><span class="axis"></span>' +
        '<span class="band" style="left:' + x(d.p10).toFixed(1) + "%;width:" + (x(d.p90) - x(d.p10)).toFixed(1) + '%"></span>' +
        '<span class="iqr" style="left:' + x(d.p25).toFixed(1) + "%;width:" + (x(d.p75) - x(d.p25)).toFixed(1) + '%"></span>' +
        '<span class="med" style="left:' + x(d.median).toFixed(1) + '%"></span>' +
        '<span class="cap" style="left:' + x(d.p10).toFixed(1) + '%">' + d.p10 + "</span>" +
        '<span class="cap" style="left:' + Math.min(x(d.p90), 94).toFixed(1) + '%">' + d.p90 + "</span></div>" +
        '<span class="dnum"><b>' + d.median + "</b> ±" + d.sd + "</span>" +
        '<select class="capsel" data-gw="' + g + '" aria-label="Captain for gameweek ' + g + '">' + opts + "</select>" +
        "</div>";
    }).join("");

    $("#liveRows").innerHTML = rows;
    var t = res.total;
    $("#liveHead").innerHTML =
      '<span class="v">' + t.median + '</span><span class="s">median over GW' + GWS[0] +
      "&ndash;" + GWS[GWS.length - 1] + "</span>";
    $("#liveRange").innerHTML =
      '<span class="v">' + t.p10 + "&ndash;" + t.p90 + '</span><span class="s">80% of ' +
      res.n.toLocaleString() + " runs</span>";
    $("#liveSubs").innerHTML =
      '<span class="v">' + res.subs.toFixed(1) + '</span><span class="s">auto-subs per five weeks</span>';
    var caps = GWS.map(function (g) { return Math.round(res.capRet[g] * 100); });
    $("#liveCap").innerHTML =
      '<span class="v">' + Math.min.apply(null, caps) + "&ndash;" + Math.max.apply(null, caps) +
      '%</span><span class="s">captain returns 6+</span>';

    document.querySelectorAll(".capsel").forEach(function (s) {
      s.addEventListener("change", function () {
        captains[+s.dataset.gw] = +s.value;
        run();
      });
    });
  }

  function run() {
    var btn = $("#liveRun");
    if (btn) { btn.disabled = true; btn.textContent = "Simulating…"; }
    setTimeout(function () {
      var res = simulate(squad, runs);
      render(res);
      if (btn) { btn.disabled = false; btn.textContent = "Re-run"; }
    }, 10);
  }

  // controls
  document.addEventListener("DOMContentLoaded", function () {
    var rs = $("#liveRuns");
    if (rs) rs.addEventListener("change", function () { runs = +rs.value; run(); });
    var btn = $("#liveRun");
    if (btn) btn.addEventListener("click", run);
    var swap = $("#liveSwap");
    if (swap) {
      var outSel = $("#swapOut"), inSel = $("#swapIn");
      var fill = function () {
        outSel.innerHTML = squad.map(function (id) {
          return '<option value="' + id + '">' + P[id].n + " (" + P[id].pos + ")</option>";
        }).join("");
        var etOut = P[+outSel.value].et;
        inSel.innerHTML = Object.keys(P)
          .filter(function (id) { return squad.indexOf(+id) < 0 && P[id].et === etOut; })
          .sort(function (a, b) { return P[b].ep - P[a].ep; })
          .slice(0, 40)
          .map(function (id) {
            return '<option value="' + id + '">' + P[id].n + " · £" + P[id].pr.toFixed(1) +
                   " · " + P[id].ep.toFixed(0) + "</option>";
          }).join("");
      };
      fill();
      outSel.addEventListener("change", fill);
      swap.addEventListener("click", function () {
        var i = squad.indexOf(+outSel.value);
        if (i >= 0 && inSel.value) {
          squad[i] = +inSel.value;
          captains = {};
          fill();
          run();
        }
      });
      var reset = $("#liveReset");
      if (reset) reset.addEventListener("click", function () {
        squad = DATA.squad.slice(); captains = {}; fill(); run();
      });
    }
    run();
  });
})();
