/* Creator Program Directory: client-side finder. No dependencies, no tracking of its own.
   Reads assets/programs.json (built from data/programs.json) and filters it in the browser. */
(function () {
  "use strict";
  var root = document.getElementById("finder");
  var embed = document.getElementById("embed-list");
  if (!root && !embed) return;
  var base = (document.querySelector('meta[name="site-base"]') || {}).content || "";
  var PAGE = 48;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmtDate(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
  }
  function followers(n) {
    return n >= 1000000 ? (n / 1000000).toFixed(n % 1000000 ? 1 : 0) + "M" : n >= 1000 ? (n / 1000).toFixed(n % 1000 ? 1 : 0) + "K" : String(n);
  }
  function mentions(f, labels) {
    var out = [];
    if (f.commission_pct) out.push(f.commission_pct + "% commission");
    if (f.free_product) out.push("free or gifted products");
    if (f.paid) out.push("paid work");
    if (f.discount_pct) out.push("a " + f.discount_pct + "% discount");
    if (f.followers_min) out.push(followers(f.followers_min) + "+ followers");
    if (f.no_follower_minimum) out.push("no follower minimum");
    if (f.residents) out.push("open to " + (labels.residents[f.residents] || f.residents));
    if (f.min_age) out.push("applicants must be " + f.min_age + "+");
    if (f.platforms && f.platforms.length) {
      out.push(f.platforms.map(function (p) { return labels.socials[p] || p; }).join(", "));
    }
    return out;
  }
  function how(p) {
    if (p.m === "platform") return "Apply through " + esc(p.v) + " (linked from the page)";
    if (p.m === "external_form") return esc(p.v) + " linked from the page";
    return esc(p.v);
  }
  function card(p, labels, target) {
    var m = mentions(p.f || {}, labels);
    var chips = p.t.map(function (t) { return '<li class="chip type">' + esc(labels.types[t] || t) + "</li>"; }).join("") +
      '<li class="chip">' + esc(labels.categories[p.c] || p.c) + "</li>" + (p.r ? '<li class="chip">' + esc(p.r) + "</li>" : "") +
      (p.l && labels.langs[p.l] && p.l !== "en" ? '<li class="chip">' + esc(labels.langs[p.l]) + " page</li>" : "");
    return '<li class="card" id="' + esc(p.id) + '"><h3>' + esc(p.b) + '</h3><div class="host">' + esc(p.h) + "</div>" +
      '<ul class="chips">' + chips + "</ul>" + '<p class="how">' + how(p) + "</p>" +
      (m.length ? '<p class="mentions"><b>The page mentions:</b> ' + esc(m.join(" · ")) + "</p>" : "") +
      (p.s ? '<p class="ships">' + esc(p.s) + "</p>" : "") +
      '<div class="foot"><small>Verified <time datetime="' + esc(p.d) + '">' + fmtDate(p.d) + "</time></small>" +
      '<a class="btn primary" data-out="' + esc(p.id) + '" href="' + esc(p.u) + '" rel="noopener nofollow"' + (target ? ' target="_blank"' : "") +
      ">Open the page<span aria-hidden=\"true\"> ↗</span><span class=\"visually-hidden\"> on " + esc(p.h) + "</span></a></div></li>";
  }
  function track(e) {
    var a = e.target.closest && e.target.closest("a[data-out]");
    if (a && window.goatcounter && window.goatcounter.count) {
      window.goatcounter.count({ path: "out-" + a.getAttribute("data-out"), title: "Outbound: application page", event: true });
    }
  }
  document.addEventListener("click", track);

  fetch(base + "/assets/programs.json").then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (data) {
    if (embed) return runEmbed(data);
    runFinder(data);
  }).catch(function () {
    var el = document.getElementById("results") || embed;
    if (el) el.innerHTML = '<li class="empty">The list could not be loaded. Use the category pages instead.</li>';
  });

  function runEmbed(data) {
    var q = new URLSearchParams(location.search);
    var cat = q.get("category") || "", type = q.get("type") || "", n = Math.min(parseInt(q.get("n") || "8", 10) || 8, 25);
    var list = data.programs.filter(function (p) { return (!cat || p.c === cat) && (!type || p.t.indexOf(type) >= 0); });
    list.sort(function (a, b) { return a.d < b.d ? 1 : a.d > b.d ? -1 : a.b.localeCompare(b.b); });
    embed.innerHTML = list.slice(0, n).map(function (p) { return card(p, data.labels, true); }).join("") ||
      '<li class="empty">No programs match.</li>';
  }

  function runFinder(data) {
    var L = data.labels, all = data.programs;
    var els = { q: root.querySelector("[name=q]"), cat: root.querySelector("[name=cat]"), type: root.querySelector("[name=type]"),
      via: root.querySelector("[name=via]"), perk: root.querySelector("[name=perk]"), ship: root.querySelector("[name=ship]") };
    var results = document.getElementById("results"), count = document.getElementById("count"), more = document.getElementById("more");
    var shown = PAGE;

    function fill(sel, counts, labels) {
      Object.keys(counts).sort(function (a, b) { return (labels[a] || a).localeCompare(labels[b] || b); }).forEach(function (k) {
        var o = document.createElement("option");
        o.value = k; o.textContent = (labels[k] || k) + " (" + counts[k] + ")";
        sel.appendChild(o);
      });
    }
    var cc = {}, tc = {}, vc = {}, sc = {};
    all.forEach(function (p) {
      cc[p.c] = (cc[p.c] || 0) + 1;
      p.t.forEach(function (t) { tc[t] = (tc[t] || 0) + 1; });
      var v = p.v;
      p._via = v; vc[v] = (vc[v] || 0) + 1;
      (p.k || []).forEach(function (k) { if (k !== "*") sc[k] = (sc[k] || 0) + 1; });
      p._text = (p.b + " " + p.h + " " + (L.categories[p.c] || "") + " " + (p.r || "") + " " + p.t.map(function (t) { return L.types[t]; }).join(" ") + " " + v).toLowerCase();
    });
    var world = all.filter(function (p) { return (p.k || []).indexOf("*") >= 0; }).length;
    Object.keys(sc).forEach(function (k) { sc[k] += world; });
    fill(els.cat, cc, L.categories); fill(els.type, tc, L.types); fill(els.via, vc, {}); fill(els.ship, sc, L.countries);

    var params = new URLSearchParams(location.search);
    ["q", "cat", "type", "via", "perk", "ship"].forEach(function (k) { if (params.get(k)) els[k].value = params.get(k); });

    function matches(p) {
      var q = els.q.value.trim().toLowerCase();
      if (q && q.split(/\s+/).some(function (w) { return p._text.indexOf(w) < 0; })) return false;
      if (els.cat.value && p.c !== els.cat.value) return false;
      if (els.type.value && p.t.indexOf(els.type.value) < 0) return false;
      if (els.via.value && p._via !== els.via.value) return false;
      if (els.ship.value && (p.k || []).indexOf(els.ship.value) < 0 && (p.k || []).indexOf("*") < 0) return false;
      var f = p.f || {}, k = els.perk.value;
      if (k === "free" && !f.free_product) return false;
      if (k === "commission" && !f.commission_pct) return false;
      if (k === "paid" && !f.paid) return false;
      if (k === "small" && !(f.no_follower_minimum || (f.followers_min && f.followers_min <= 5000))) return false;
      return true;
    }
    function render() {
      var list = all.filter(matches);
      count.textContent = list.length + (list.length === 1 ? " program" : " programs") + (list.length === all.length ? "" : " of " + all.length);
      results.innerHTML = list.slice(0, shown).map(function (p) { return card(p, L, false); }).join("") ||
        '<li class="empty">Nothing matches. Clear a filter or try a broader word.</li>';
      more.hidden = list.length <= shown;
      var s = new URLSearchParams();
      ["q", "cat", "type", "via", "perk", "ship"].forEach(function (k) { if (els[k].value) s.set(k, els[k].value); });
      var qs = s.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    }
    var timer;
    Object.keys(els).forEach(function (k) {
      els[k].addEventListener("input", function () { shown = PAGE; clearTimeout(timer); timer = setTimeout(render, 80); });
    });
    more.addEventListener("click", function () { shown += PAGE * 2; render(); });
    document.getElementById("reset").addEventListener("click", function () {
      Object.keys(els).forEach(function (k) { els[k].value = ""; }); shown = PAGE; render(); els.q.focus();
    });
    var copy = document.getElementById("copy");
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "Link copied"; setTimeout(function () { copy.textContent = "Copy link to this search"; }, 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(done, function () { prompt("Copy this link", location.href); });
      else prompt("Copy this link", location.href);
      if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: "share-search", title: "Share: search link", event: true });
    });
    root.hidden = false;
    render();
  }
})();
