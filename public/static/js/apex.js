/* APEX client-side enhancements (progressive; every form works without JS). */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root = document.documentElement;
  var signedIn = root.getAttribute("data-prefs") === "server";
  var csrf = ($('meta[name="csrf-token"]') || {}).content || "";

  function api(url, body) {
    return fetch(url, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  /* ---------- appearance ---------- */
  function setAttr(key, value) {
    root.setAttribute("data-" + key, value);
    try { localStorage.setItem("apex-" + key, value); } catch (e) { /* ignore */ }
  }
  $$("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      setAttr("theme", mode);
      var radio = $('input[name="mode"][value="' + mode + '"]');
      if (radio) radio.checked = true;
      if (signedIn) api("/api/preferences", { mode: mode }).catch(function () {});
    });
  });

  /* Settings page: live preview; the Save button persists to Supabase. */
  var settingsForm = $("[data-settings-form]");
  if (settingsForm) {
    $$("[data-pref]", settingsForm).forEach(function (input) {
      input.addEventListener("change", function () {
        var key = input.dataset.pref;
        setAttr(key, key === "electric" ? (input.checked ? "on" : "off") : input.value);
      });
    });
  }

  /* ---------- login tabs ---------- */
  var tabs = $("[data-tabs]");
  if (tabs) {
    var portalInput = $("[data-portal-input]");
    var portalLabel = $("[data-portal-label]");
    var select = function (portal) {
      tabs.dataset.active = portal;
      portalInput.value = portal;
      portalLabel.textContent = portal === "admin" ? "Sign in as Admin" : "Sign in as Associate";
      $$(".tab", tabs).forEach(function (t) {
        var on = t.dataset.portal === portal;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", String(on));
      });
    };
    $$(".tab", tabs).forEach(function (t) { t.addEventListener("click", function () { select(t.dataset.portal); }); });
    select(portalInput.value);
  }

  /* ---------- password reveal + rules ---------- */
  $$("[data-reveal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var field = btn.parentElement.querySelector("input");
      var show = field.type === "password";
      field.type = show ? "text" : "password";
      btn.classList.toggle("on", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
  var strength = $("[data-strength]");
  if (strength) {
    var tests = { length: /.{8,}/, upper: /[A-Z]/, lower: /[a-z]/, number: /\d/ };
    var confirmField = $("[data-confirm]");
    var check = function () {
      Object.keys(tests).forEach(function (k) { $('[data-rule="' + k + '"]').classList.toggle("ok", tests[k].test(strength.value)); });
      if (confirmField.value) confirmField.setCustomValidity(confirmField.value === strength.value ? "" : "Passwords do not match");
    };
    strength.addEventListener("input", check);
    confirmField.addEventListener("input", check);
  }

  /* ---------- company email (accepted domain is enforced on the server too) ---------- */
  $$("[data-company-email]").forEach(function (email) {
    var err = $("[data-email-error]", email.form);
    var re = /^[a-z][a-z'-]*(?:\.[a-z0-9][a-z0-9'-]*)+@carelon\.com$/;
    email.form.addEventListener("submit", function (e) {
      var v = email.value.trim().toLowerCase();
      if (!re.test(v) || v.indexOf("..") > -1) { e.preventDefault(); if (err) err.hidden = false; email.focus(); }
    });
    email.addEventListener("input", function () { if (err) err.hidden = true; });
  });

  /* ---------- prevent double submit ---------- */
  $$("form[data-busy]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      if (f.dataset.submitting) { e.preventDefault(); return; }
      f.dataset.submitting = "1";
      setTimeout(function () { f.classList.add("is-busy"); }, 0);
    });
  });

  /* ---------- flash messages ---------- */
  $$("[data-flash]").forEach(function (el) {
    var close = function () { el.classList.add("out"); setTimeout(function () { el.remove(); }, 350); };
    $("[data-dismiss]", el).addEventListener("click", close);
    setTimeout(close, 7000);
  });

  /* ---------- mobile / portrait sidebar ---------- */
  var shell = $("[data-shell]");
  if (shell) {
    var toggleNav = function (open) { shell.classList.toggle("nav-open", open); };
    $("[data-menu]").addEventListener("click", function () { toggleNav(!shell.classList.contains("nav-open")); });
    $("[data-scrim]").addEventListener("click", function () { toggleNav(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") toggleNav(false); });
  }

  /* ---------- greeting & counters ---------- */
  var greet = $("[data-greeting]");
  if (greet) {
    var h = new Date().getHours();
    greet.textContent = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }
  $$("[data-count]").forEach(function (el) {
    var target = parseInt(el.dataset.count, 10);
    if (!target) return;
    var start = performance.now();
    var step = function (t) {
      var p = Math.min((t - start) / 900, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))).toLocaleString();
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });

  /* ---------- table filter (admin) ---------- */
  $$("[data-table-filter]").forEach(function (input) {
    var rows = $$(input.dataset.tableFilter + " tbody tr");
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      rows.forEach(function (r) { r.hidden = q && r.textContent.toLowerCase().indexOf(q) === -1; });
    });
  });

  /* ---------- program selection ---------- */
  var programForm = $("[data-program-form]");
  if (programForm) {
    var cont = $("[data-program-continue]", programForm);
    var options = $$("[data-program-option]", programForm);
    var sync = function () {
      if (cont.hasAttribute("data-locked")) return;
      cont.disabled = !options.some(function (o) { return o.checked; });
    };
    if (cont.disabled) cont.setAttribute("data-locked", "");
    options.forEach(function (o) { o.addEventListener("change", sync); });
    sync();
  }

  /* ---------- task entry: remarks counter ---------- */
  $$("[data-counter]").forEach(function (ta) {
    var out = ta.parentElement.querySelector("[data-counter-out]");
    var max = ta.getAttribute("maxlength");
    var upd = function () { if (out) out.textContent = ta.value.length + " / " + max; };
    ta.addEventListener("input", upd);
    upd();
  });
  $$("[data-clear]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var form = btn.form;
      $$("input:not([readonly]):not([type=hidden]), textarea", form).forEach(function (el) {
        el.value = el.dataset.default || "";
        el.dispatchEvent(new Event("input"));
      });
      var first = $("input:not([readonly]):not([type=hidden])", form);
      if (first) first.focus();
    });
  });

  /* ---------- notifications ---------- */
  var notif = $("[data-notif]");
  if (notif) {
    var btn = $("[data-notif-toggle]", notif);
    var panel = $("[data-notif-panel]", notif);
    var list = $("[data-notif-list]", notif);
    var count = $("[data-notif-count]", notif);
    var esc = function (s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; };
    var render = function (data) {
      count.hidden = !data.unread;
      count.textContent = data.unread > 99 ? "99+" : data.unread;
      btn.classList.toggle("has-unread", data.unread > 0);
      btn.setAttribute("aria-label", "Notifications (" + data.unread + " unread)");
      list.innerHTML = data.items.length ? data.items.map(function (n) {
        return '<li class="kind-' + esc(n.kind) + (n.is_read ? "" : " unread") + '" data-id="' + esc(n.id) + '">' +
          '<span class="notif-dot"></span><div><p><strong>' + esc(n.title) + "</strong></p>" +
          (n.message ? '<p class="muted">' + esc(n.message) + "</p>" : "") +
          '<small class="muted">' + esc(n.when) + "</small></div></li>";
      }).join("") : '<li class="notif-empty muted">You\'re all caught up.</li>';
    };
    var load = function () { api(notif.dataset.endpoint).then(render).catch(function () {}); };
    var open = function (show) {
      panel.hidden = !show;
      btn.setAttribute("aria-expanded", String(show));
      if (show) load();
    };
    btn.addEventListener("click", function (e) { e.stopPropagation(); open(panel.hidden); });
    document.addEventListener("click", function (e) { if (!notif.contains(e.target)) open(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") open(false); });
    list.addEventListener("click", function (e) {
      var li = e.target.closest("li[data-id]");
      if (!li || !li.classList.contains("unread")) return;
      api(notif.dataset.readEndpoint, { id: Number(li.dataset.id) }).then(load).catch(function () {});
    });
    load();
    setInterval(function () { if (!document.hidden) load(); }, 60000);
    $$("[data-notif-readall]").forEach(function (b) {
      b.addEventListener("click", function () {
        api(notif.dataset.readEndpoint, {}).then(function () {
          if (b.hasAttribute("data-reload")) window.location.reload(); else load();
        }).catch(function () {});
      });
    });
  }

  /* ---------- charts (dependency-free SVG) ---------- */
  var chartData = $("#chart-data");
  if (chartData) {
    var data = JSON.parse(chartData.textContent);
    var NS = "http://www.w3.org/2000/svg";
    var tip = document.createElement("div");
    tip.className = "chart-tip"; tip.hidden = true; document.body.appendChild(tip);
    var el = function (name, attrs, parent) {
      var n = document.createElementNS(NS, name);
      Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
      if (parent) parent.appendChild(n);
      return n;
    };
    var hover = function (node, text) {
      node.addEventListener("mousemove", function (e) { tip.hidden = false; tip.textContent = text; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 30 + "px"; });
      node.addEventListener("mouseleave", function () { tip.hidden = true; });
    };
    var gradients = function (svg) {
      var defs = el("defs", {}, svg);
      var bar = el("linearGradient", { id: "bar-grad", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      el("stop", { offset: "0%", "stop-color": "var(--e1)" }, bar).style.stopColor = "var(--e1)";
      el("stop", { offset: "100%", "stop-color": "var(--e3)" }, bar).style.stopColor = "var(--e3)";
      var area = el("linearGradient", { id: "area-grad", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      var s1 = el("stop", { offset: "0%" }, area); s1.style.stopColor = "var(--e1)"; s1.style.stopOpacity = ".35";
      var s2 = el("stop", { offset: "100%" }, area); s2.style.stopColor = "var(--e1)"; s2.style.stopOpacity = "0";
    };
    var frame = function (host, series, kind) {
      var W = 640, H = 220, P = { l: 34, r: 10, t: 12, b: 28 };
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H }, host);
      gradients(svg);
      var max = Math.max.apply(null, series.map(function (d) { return d.count; }).concat([1]));
      var nice = Math.ceil(max / 4) * 4 || 4;
      var iw = W - P.l - P.r, ih = H - P.t - P.b;
      for (var g = 0; g <= 4; g++) {
        var y = P.t + ih - (ih * g) / 4;
        el("line", { x1: P.l, x2: W - P.r, y1: y, y2: y, class: g ? "grid-line" : "axis" }, svg);
        el("text", { x: P.l - 6, y: y + 4, "text-anchor": "end" }, svg).textContent = Math.round((nice * g) / 4);
      }
      var step = iw / series.length;
      var labelEvery = Math.ceil(series.length / 8);
      var pts = [];
      series.forEach(function (d, i) {
        var x = P.l + step * i + step / 2;
        var h = (d.count / nice) * ih;
        var bw = Math.min(step * 0.62, 38);
        if (kind === "bar") {
          var r = el("rect", { x: x - bw / 2, y: P.t + ih - h, width: bw, height: Math.max(h, d.count ? 2 : 0), rx: 6, class: "bar grow-in" }, svg);
          r.style.animationDelay = i * 40 + "ms";
          hover(r, d.label + ": " + d.count);
        } else if (kind === "stacked") {
          var hv = (d.valid / nice) * ih, hi = (d.invalid / nice) * ih;
          var g2 = el("g", { class: "grow-in" }, svg);
          g2.style.animationDelay = i * 30 + "ms";
          if (d.valid) el("rect", { x: x - bw / 2, y: P.t + ih - hv, width: bw, height: hv, rx: 4, class: "bar-valid" }, g2);
          if (d.invalid) el("rect", { x: x - bw / 2, y: P.t + ih - hv - hi, width: bw, height: hi, rx: 4, class: "bar-invalid" }, g2);
          var hit = el("rect", { x: x - step / 2, y: P.t, width: step, height: ih, class: "bar-hit" }, svg);
          hover(hit, d.label + " — Valid: " + d.valid + ", Invalid: " + d.invalid);
        }
        pts.push([x, P.t + ih - h, d]);
        if (i % labelEvery === 0) el("text", { x: x, y: H - 8, "text-anchor": "middle" }, svg).textContent = d.label;
      });
      if (kind === "line") {
        var path = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
        el("path", { d: path + " L" + pts[pts.length - 1][0] + " " + (P.t + ih) + " L" + pts[0][0] + " " + (P.t + ih) + " Z", class: "area" }, svg);
        var line = el("path", { d: path, class: "line draw" }, svg);
        line.style.setProperty("--len", Math.ceil(line.getTotalLength ? line.getTotalLength() : 2000));
        pts.forEach(function (p) {
          var c = el("circle", { cx: p[0], cy: p[1], r: p[2].count ? 4 : 2.5, class: "pt" }, svg);
          hover(c, p[2].label + ": " + p[2].count);
        });
      }
    };
    var donut = function (host, d) {
      var total = d.valid + d.invalid;
      var svg = el("svg", { viewBox: "0 0 160 160", width: 170, height: 170 }, host);
      var R = 62, C = 2 * Math.PI * R;
      el("circle", { cx: 80, cy: 80, r: R, class: "donut-ring donut-track" }, svg);
      var offset = 0;
      [["valid", "#10b981"], ["invalid", "#ef4444"]].forEach(function (s) {
        var len = total ? (d[s[0]] / total) * C : 0;
        var seg = el("circle", { cx: 80, cy: 80, r: R, class: "donut-ring donut-seg", stroke: s[1], transform: "rotate(-90 80 80)",
          "stroke-dasharray": "0 " + C, "stroke-dashoffset": -offset }, svg);
        requestAnimationFrame(function () { setTimeout(function () { seg.setAttribute("stroke-dasharray", Math.max(len - (len > 6 ? 4 : 0), 0) + " " + C); }, 60); });
        hover(seg, s[0][0].toUpperCase() + s[0].slice(1) + ": " + d[s[0]]);
        offset += len;
      });
      el("text", { x: 80, y: 84, "text-anchor": "middle", class: "donut-total" }, svg).textContent = total;
      el("text", { x: 80, y: 104, "text-anchor": "middle" }, svg).textContent = "reviewed";
      var pct = function (n) { return total ? Math.round((n / total) * 100) + "%" : "0%"; };
      var legend = document.createElement("ul");
      legend.className = "legend";
      legend.innerHTML =
        '<li><i class="lg-valid"></i>Valid <strong>' + d.valid + '</strong> <span class="muted">' + pct(d.valid) + "</span></li>" +
        '<li><i class="lg-invalid"></i>Invalid <strong>' + d.invalid + '</strong> <span class="muted">' + pct(d.invalid) + "</span></li>" +
        (d.unreviewed === undefined ? "" : '<li><i class="lg-none"></i>Not reviewed <strong>' + d.unreviewed + "</strong></li>");
      host.appendChild(legend);
    };
    var legendList = function (items, cls) {
      var ul = document.createElement("ul");
      ul.className = cls || "legend";
      items.forEach(function (it) {
        var li = document.createElement("li");
        var sw = document.createElement("i");
        sw.style.background = it.color;
        li.appendChild(sw);
        li.appendChild(document.createTextNode(it.label + " "));
        if (it.value !== undefined) {
          var b = document.createElement("strong"); b.textContent = it.value; li.appendChild(b);
          if (it.pct !== undefined) { var m = document.createElement("span"); m.className = "muted"; m.textContent = " " + it.pct; li.appendChild(m); }
        }
        ul.appendChild(li);
      });
      return ul;
    };
    /* Generic donut: segments = [{label, value, color}] */
    var donutSegments = function (host, segments) {
      var total = segments.reduce(function (s, x) { return s + x.value; }, 0);
      var svg = el("svg", { viewBox: "0 0 160 160", width: 170, height: 170 }, host);
      var R = 62, C = 2 * Math.PI * R, offset = 0;
      el("circle", { cx: 80, cy: 80, r: R, class: "donut-ring donut-track" }, svg);
      segments.forEach(function (s) {
        var len = total ? (s.value / total) * C : 0;
        var seg = el("circle", { cx: 80, cy: 80, r: R, class: "donut-ring donut-seg", stroke: s.color, transform: "rotate(-90 80 80)",
          "stroke-dasharray": "0 " + C, "stroke-dashoffset": -offset }, svg);
        requestAnimationFrame(function () { setTimeout(function () { seg.setAttribute("stroke-dasharray", Math.max(len - (len > 6 ? 4 : 0), 0) + " " + C); }, 60); });
        hover(seg, s.label + ": " + s.value);
        offset += len;
      });
      el("text", { x: 80, y: 84, "text-anchor": "middle", class: "donut-total" }, svg).textContent = total;
      el("text", { x: 80, y: 104, "text-anchor": "middle" }, svg).textContent = host.dataset.center || "total";
      host.appendChild(legendList(segments.map(function (s) {
        return { label: s.label, value: s.value, color: s.color, pct: total ? Math.round((s.value / total) * 100) + "%" : "0%" };
      })));
    };
    /* Manager performance: per manager a status bar (pending+completed) and a review bar (valid+invalid). */
    var hbars = function (host, rows) {
      if (!rows.length) { host.textContent = "No data for the current filters."; host.classList.add("muted"); return; }
      var W = 640, L = 150, R = 16, rowH = 38, H = rows.length * rowH + 8;
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H }, host);
      var max = Math.max.apply(null, rows.map(function (r) { return Math.max(r.pending + r.completed, r.valid + r.invalid); }).concat([1]));
      var scale = (W - L - R) / max;
      rows.forEach(function (r, i) {
        var y = 6 + i * rowH;
        var name = r.label.length > 20 ? r.label.slice(0, 19) + "…" : r.label;
        el("text", { x: L - 10, y: y + 17, "text-anchor": "end", class: "hb-name" }, svg).textContent = name;
        el("rect", { x: L, y: y + 2, width: W - L - R, height: 12, rx: 6, class: "hb-track" }, svg);
        el("rect", { x: L, y: y + 18, width: W - L - R, height: 12, rx: 6, class: "hb-track" }, svg);
        var g = el("g", { class: "grow-in" }, svg);
        g.style.animationDelay = i * 50 + "ms";
        g.style.transformOrigin = "left";
        var x = L;
        [["pending", 2], ["completed", 2], ["valid", 18], ["invalid", 18]].forEach(function (p, j) {
          if (j === 2) x = L;
          var w = r[p[0]] * scale;
          if (w > 0) el("rect", { x: x, y: y + p[1], width: w, height: 12, rx: 6, class: "hb-" + p[0] }, g);
          x += w;
        });
        var hit = el("rect", { x: 0, y: y, width: W, height: rowH - 4, class: "bar-hit" }, svg);
        hover(hit, r.label + " — Pending " + r.pending + " · Completed " + r.completed + " · Valid " + r.valid + " · Invalid " + r.invalid);
      });
      host.appendChild(legendList([{ label: "Pending", color: "#f97316" }, { label: "Completed", color: "#22c55e" },
        { label: "Valid", color: "#10b981" }, { label: "Invalid", color: "#ef4444" }], "legend legend-inline"));
    };
    $$("[data-chart]").forEach(function (host) {
      var key = host.dataset.chart;
      if (host.dataset.kind === "donut") donutSegments(host, data[key]);
      else if (host.dataset.kind === "hbars") hbars(host, data[key]);
      else if (key === "review") donut(host, data.review);
      else {
        var kind = host.dataset.kind || (key === "monthly" ? "bar" : "line");
        frame(host, data[key], kind);
        if (kind === "stacked") {
          var lg = document.createElement("ul");
          lg.className = "legend legend-inline";
          lg.innerHTML = '<li><i class="lg-valid"></i>Valid</li><li><i class="lg-invalid"></i>Invalid</li>';
          host.appendChild(lg);
        }
      }
    });
  }

  /* ---------- admin: auto-submit view toggle, export menu ---------- */
  $$("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () {
      var form = input.form;
      $$('input[type="date"]', form).forEach(function (d) { d.value = ""; });
      form.submit();
    });
  });
  document.addEventListener("click", function (e) {
    $$("details.export[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });

  /* ---------- executive dashboard: refresh as soon as a filter changes ---------- */
  $$("form[data-auto-refresh]").forEach(function (form) {
    $$("select, input[type=date]", form).forEach(function (input) {
      input.addEventListener("change", function () {
        if (input.type === "date" && input.value && !/^\d{4}-\d{2}-\d{2}$/.test(input.value)) return;
        form.classList.add("is-busy");
        form.submit();
      });
    });
  });
})();
