/* ============================================================
   Source Agent — frontend logic
   Talks to the real API (same origin): /api/v1/candidates, /api/v1/discovery.
   No build step, no framework — matches the dependency-light backend.
   ============================================================ */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  const money = (v) =>
    v == null ? "—" : (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(2);
  const pct = (v) => (v == null ? "—" : v.toFixed(1) + "%");
  const num = (v) => (v == null ? "—" : Number(v).toLocaleString());

  async function api(path, { method = "POST", json, form } = {}) {
    const opts = { method };
    if (form) {
      opts.body = form;
    } else if (json !== undefined) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(json);
    }
    const res = await fetch(path, opts);
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      const msg = data && data.detail ? data.detail : `HTTP ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  // ---- state chip ----
  const stateEl = $("#state"), stateT = $("#state-t");
  function setState(kind, text) {
    stateEl.className = "agent-state" + (kind ? " " + kind : "");
    stateT.textContent = text;
  }

  // ---- theme ----
  $("#theme").addEventListener("click", () => {
    let cur = root.getAttribute("data-theme");
    if (!cur) cur = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    root.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
  });

  // ---- view router ----
  // Hash-based on purpose: StaticFiles is mounted at /app with no SPA fallback,
  // so /app/batches would 404. hashchange also gives back/forward for free.
  const VIEWS = {
    evaluate: {
      sel: "#view-evaluate",
      title: "Evaluate a product",
      desc: "Run a candidate through the sourcing graph — identity, live Amazon data, mode research, deterministic profit math, verdict.",
    },
    batches: {
      sel: "#view-batches",
      title: "Batch upload",
      desc: "Validate a CSV of candidates before enqueuing — no row is dropped silently, every reject carries a reason.",
    },
    discovery: {
      sel: "#view-discovery",
      title: "Discover from a location",
      desc: "Start from a place, not a product — expand categories, sweep stores, filter against your per-user “seen” memory.",
    },
  };

  function showView(name) {
    const key = VIEWS[name] ? name : "evaluate";
    Object.entries(VIEWS).forEach(([k, v]) =>
      $(v.sel).classList.toggle("hidden", k !== key)
    );
    document.querySelectorAll("[data-view]").forEach((b) =>
      b.classList.toggle("on", b.dataset.view === key)
    );
    $("#page-title").textContent = VIEWS[key].title;
    $("#page-desc").textContent = VIEWS[key].desc;
    // The chip is shared; a stale "report ready · BUY" must not follow you.
    setState("", "agent idle");
    if (location.hash.slice(1) !== key) location.hash = key;
  }

  $(".rail nav").addEventListener("click", (e) => {
    const b = e.target.closest("[data-view]");
    if (b) showView(b.dataset.view);
  });
  addEventListener("hashchange", () => showView(location.hash.slice(1)));
  showView(location.hash.slice(1));

  // ---- segmented toggles ----
  function seg(id, cb) {
    const wrap = $("#" + id);
    let val = wrap.querySelector(".on")?.dataset.val;
    wrap.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      wrap.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      val = b.dataset.val;
      if (cb) cb(val);
    });
    return () => val;
  }

  // channel: text | barcode  (csv is its own view now)
  const qInput = $("#q");
  const placeholders = {
    text: "Type a product name or description…",
    barcode: "Scan or paste a UPC / EAN…",
  };
  const getChannel = seg("channel", (v) => {
    qInput.placeholder = placeholders[v] || "";
  });

  // mode: retail_arb | wholesale | artisan — local price only matters for retail arb
  const getMode = seg("mode", (v) => {
    $("#price-mini").style.display = v === "retail_arb" ? "" : "none";
    const label = { retail_arb: "retail_arb_research", wholesale: "wholesale_research", artisan: "artisan_research" };
    $("#research-name").textContent = label[v];
  });

  // batches view has its own sourcing-mode control (seg() binds by id)
  const getCsvMode = seg("csv-mode");

  // ---- pipeline trace ----
  const nodes = Array.from(document.querySelectorAll("[data-node]"));
  function resetTrace() {
    nodes.forEach((n) => {
      n.className = "pnode";
      $(".pmeta", n).textContent = "";
    });
  }
  let ticker = null;
  function rollTrace() {
    if (reduce) return;
    let i = 0;
    ticker = setInterval(() => {
      if (i > 0) nodes[i - 1].classList.remove("active"), nodes[i - 1].classList.add("ok");
      if (i < nodes.length) nodes[i].classList.add("active");
      else i = 0; // loop until the response lands
      i++;
    }, 380);
  }
  function stopTrace() {
    if (ticker) clearInterval(ticker), (ticker = null);
  }
  function finishTrace(r) {
    stopTrace();
    const aborted = (r.errors && r.errors.length) || r.est_profit == null;
    const meta = [
      r.identity_confidence != null ? "confidence " + r.identity_confidence.toFixed(2) : "identified",
      r.bsr != null ? "BSR #" + num(r.bsr) + " · " + num(r.offer_count) + " offers" : "no listing",
      (r.findings ? r.findings.length : 0) + " findings · " + (r.sources ? r.sources.length : 0) + " sources",
      r.est_profit != null ? "profit " + money(r.est_profit) : "no profit math",
      "verdict: " + (r.verdict || "—"),
    ];
    nodes.forEach((n, idx) => {
      n.classList.remove("active");
      const routeSkipped = aborted && (idx === 2 || idx === 3);
      n.classList.add(routeSkipped ? "skip" : "ok");
      $(".pmeta", n).textContent = routeSkipped ? "skipped (abort)" : meta[idx];
    });
  }

  // ---- verdict mapping ----
  const VERDICT = {
    strong: { label: "BUY", cls: "buy" },
    marginal: { label: "WATCH", cls: "watch" },
    avoid: { label: "AVOID", cls: "avoid" },
  };

  // ---- build candidate payload ----
  function buildCandidate() {
    const channel = getChannel();
    const mode = getMode();
    const raw = qInput.value.trim();
    const c = {
      sourcing_mode: mode,
      input_channel: channel,
      currency: "CAD",
      source_location: $("#region").value,
      source_name: "Local retailer",
    };
    if (channel === "barcode") {
      // Scanners and pasted GTINs routinely carry spaces/hyphens.
      const digits = raw.replace(/[\s-]/g, "");
      // Fail loudly. Silently falling back to a name search turns an intended
      // 0.85-confidence UPC match into a 0.45 one, and the verdict looks just
      // as authoritative either way.
      if (!/^\d{8,14}$/.test(digits))
        throw new Error("That doesn’t look like a UPC/EAN — switch to Text to search by name.");
      c.upc = digits;
    } else {
      c.name = raw;
    }
    if (mode === "retail_arb") {
      const p = parseFloat($("#price").value);
      if (!isNaN(p)) c.local_price = p;
    }
    return c;
  }

  // ---- render report ----
  const reportEl = $("#report");
  function renderReport(r) {
    const v = VERDICT[r.verdict] || { label: (r.verdict || "—").toUpperCase(), cls: "avoid" };
    const L = r.ledger;
    const conf = r.identity_confidence != null ? r.identity_confidence : 0;

    const chips = [
      `<span class="chip mode">${esc((r.sourcing_mode || "").replace("_", " ").toUpperCase())}</span>`,
      r.bsr != null ? `<span class="chip">BSR <b>#${num(r.bsr)}</b></span>` : "",
      r.offer_count != null ? `<span class="chip">Offers <b>${num(r.offer_count)}</b></span>` : "",
      L ? `<span class="chip">Sell <b>${money(L.sale_price)}</b></span>` : "",
    ].join("");

    const tiles = L
      ? `
      <div class="tiles">
        <div class="tile"><p class="caps">Net profit / unit</p><div class="v ${L.profit >= 0 ? "pos" : "neg"} num">${money(L.profit)}</div><div class="d">after fees &amp; landed cost</div></div>
        <div class="tile"><p class="caps">Margin</p><div class="v num">${pct(r.est_margin_pct)}</div><div class="d">of ${money(L.sale_price)} sale</div></div>
        <div class="tile"><p class="caps">ROI</p><div class="v num">${pct(L.roi_pct)}</div><div class="d">on ${money(L.cost_basis)} invested</div></div>
        <div class="tile"><p class="caps">Break-even</p><div class="v num">${money(L.breakeven)}</div><div class="d">min. viable sale price</div></div>
      </div>`
      : `<div class="note"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg><span>No profit math — the candidate could not be priced or identified. ${esc((r.errors || []).join("; "))}</span></div>`;

    const ledger = L
      ? `
      <div class="card ledger">
        <h3><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h16v14H4z"/><path d="M4 10h16M9 5v14"/></svg> Profit ledger · deterministic</h3>
        <div class="lrow"><span class="lk">Amazon sale price</span><span class="lv num">${money(L.sale_price)}</span></div>
        <div class="lrow"><span class="lk">Referral fee <small>${L.referral_fee_pct != null ? L.referral_fee_pct.toFixed(0) + "%" : ""}</small></span><span class="lv neg num">${money(-L.referral_fee)}</span></div>
        <div class="lrow"><span class="lk">FBA fulfillment</span><span class="lv neg num">${money(-L.fba_fee)}</span></div>
        <div class="lrow"><span class="lk">Net proceeds</span><span class="lv num">${money(L.net_proceeds)}</span></div>
        <div class="lrow"><span class="lk">Cost basis <small>landed</small></span><span class="lv neg num">${money(L.cost_basis == null ? null : -L.cost_basis)}</span></div>
        <div class="lrow sum"><span class="lk">Net profit / unit</span><span class="lv ${L.profit >= 0 ? "pos" : "num"} num">${(L.profit >= 0 ? "+" : "") + money(L.profit).replace("−", "-")}</span></div>
        <p class="det-note"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>Computed in <code>compute_profit</code> with <code>Decimal</code> — never LLM-estimated.</p>
      </div>`
      : "";

    const findings = (r.findings || [])
      .map(
        (f) => `
      <div class="finding">
        <div class="fhead"><span class="stage">${esc(f.kind)}</span></div>
        <p>${esc(f.summary)}</p>
        ${f.source_url ? `<div class="src"><a href="${esc(f.source_url)}" target="_blank" rel="noopener">${esc(f.source_url)}</a></div>` : ""}
      </div>`
      )
      .join("");
    const sources = (r.sources || [])
      .map((s) => `<span>${esc(s.used_for || s.title || s.url)}</span>`)
      .join("");
    const risks = (r.risk_flags || [])
      .map((x) => `<span class="risk-flag">${esc(x)}</span>`)
      .join("");

    reportEl.innerHTML = `
      <div class="report-grid">
        <div class="card verdict">
          <div class="verdict-top">
            <div>
              <p class="prod-title">${esc(r.resolved_title || "Unidentified product")}</p>
              <p class="prod-sub">${esc(r.resolved_category || "—")}${r.resolved_asin ? " · ASIN " + esc(r.resolved_asin) : ""}</p>
              <div class="chips">${chips}</div>
            </div>
            <div class="verdict-badge ${v.cls}"><span class="big">${esc(v.label)}</span><span class="caps">verdict</span></div>
          </div>
          <div class="confidence">
            <div class="conf-row"><span class="caps">Identity confidence</span><span class="num" style="font-weight:700">${conf.toFixed(2)}</span></div>
            <div class="conf-track"><div class="conf-fill" style="width:0"></div></div>
          </div>
        </div>
        ${tiles}
        ${ledger}
        <div class="card evidence">
          <h3><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z"/></svg> Evidence trail — cited findings &amp; sources</h3>
          <div class="findings">${findings || '<div class="finding"><p>No findings recorded for this run.</p></div>'}</div>
          ${sources ? `<div class="src" style="margin-top:16px">${sources}</div>` : ""}
          ${risks ? `<div class="risks">${risks}</div>` : ""}
          <p class="det-note" style="margin-top:16px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4M12 16h.01"/><circle cx="12" cy="12" r="9"/></svg>${esc(r.reasoning || "")}</p>
        </div>
      </div>`;
    reportEl.classList.remove("hidden");
    requestAnimationFrame(() =>
      setTimeout(() => {
        const fill = $(".conf-fill", reportEl);
        if (fill) fill.style.width = Math.round(conf * 100) + "%";
      }, 60)
    );
  }

  const csvReportEl = $("#csv-report");
  function renderCsv(s) {
    const mapped = Object.entries(s.header_mapping || {})
      .map(([k, val]) => `<span class="chip"><b>${esc(k)}</b>→${esc(val)}</span>`)
      .join(" ");
    const rejects = (s.rejects || [])
      .map(
        (r) =>
          `<div class="lrow"><span class="lk">row ${r.row_number}</span><span class="lv ${r.duplicate ? "" : "neg"}">${r.duplicate ? "duplicate" : esc(r.error)}</span></div>`
      )
      .join("");
    csvReportEl.innerHTML = `
      <div class="card">
        <h3 style="margin:0 0 16px;font-size:.9rem">CSV validated — phase 1 preview</h3>
        <div class="tiles" style="grid-template-columns:repeat(4,1fr)">
          <div class="tile"><p class="caps">Rows</p><div class="v num">${s.total_rows}</div></div>
          <div class="tile"><p class="caps">Valid</p><div class="v pos num">${s.valid}</div></div>
          <div class="tile"><p class="caps">Rejected</p><div class="v ${s.skipped ? "neg" : ""} num">${s.skipped}</div></div>
          <div class="tile"><p class="caps">Duplicates</p><div class="v num">${s.duplicates}</div></div>
        </div>
        <div class="chips" style="margin-top:16px">${mapped || '<span class="chip">no columns mapped</span>'}</div>
        ${rejects ? `<div style="margin-top:16px">${rejects}</div>` : ""}
        <p class="det-note" style="margin-top:16px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4M12 16h.01"/><circle cx="12" cy="12" r="9"/></svg>No row is dropped silently — every reject carries a reason. Phase 2 (async enqueue) is not yet wired.</p>
      </div>`;
    csvReportEl.classList.remove("hidden");
  }

  // ---- run: evaluate one product ----
  const runBtn = $("#run");
  // `candidate` is supplied when the run originates from a discovery card;
  // otherwise the console inputs are read. Bound below as () => runEvaluate()
  // so the click Event is never mistaken for a candidate.
  async function runEvaluate(candidate) {
    runBtn.disabled = true;
    runBtn.classList.add("busy");
    try {
      const payload = candidate || buildCandidate();
      if (!payload.name && !payload.upc) throw new Error("Enter a product name or barcode.");
      resetTrace();
      rollTrace();
      setState("run", "running graph…");
      const r = await api("/api/v1/candidates/evaluate", { json: payload });
      finishTrace(r);
      renderReport(r);
      const v = VERDICT[r.verdict];
      setState("done", "report ready · " + (v ? v.label : r.verdict));
    } catch (e) {
      stopTrace();
      setState("err", "failed");
      showError(reportEl, e.message);
    } finally {
      runBtn.disabled = false;
      runBtn.classList.remove("busy");
    }
  }
  runBtn.addEventListener("click", () => runEvaluate());

  // Bridge: evaluate a product discovered from a location.
  function evaluateDiscovered(c) {
    showView("evaluate");
    // Reflect the candidate in the console so the form matches what actually ran.
    $(`#channel button[data-val="${c.upc ? "barcode" : "text"}"]`).click();
    qInput.value = c.upc || c.name || "";
    const modeBtn = $(`#mode button[data-val="${c.sourcing_mode}"]`);
    if (modeBtn) modeBtn.click();
    if (c.local_price != null) $("#price").value = c.local_price;
    // Send the discovered candidate WHOLE rather than rebuilding it from those
    // inputs: retyping through #q would drop the UPC (identity confidence
    // 0.85 → 0.45), the brand, the source context, and input_channel
    // "discovery" — which is the provenance record for where this came from.
    runEvaluate(c);
  }

  // ---- run: validate a CSV batch ----
  const csvRunBtn = $("#csv-run");
  csvRunBtn.addEventListener("click", async () => {
    csvRunBtn.disabled = true;
    csvRunBtn.classList.add("busy");
    try {
      const file = $("#csv-file").files && $("#csv-file").files[0];
      if (!file) throw new Error("Choose a CSV file first.");
      setState("run", "validating csv…");
      const form = new FormData();
      form.append("file", file);
      form.append("sourcing_mode", getCsvMode());
      const s = await api("/api/v1/candidates/csv/validate", { form });
      renderCsv(s);
      setState("done", `csv ready · ${s.valid} valid`);
    } catch (e) {
      setState("err", "failed");
      showError(csvReportEl, e.message);
    } finally {
      csvRunBtn.disabled = false;
      csvRunBtn.classList.remove("busy");
    }
  });

  function showError(host, msg) {
    host.innerHTML = `<div class="note err"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg><span><b>Request failed.</b> ${esc(msg)}</span></div>`;
    host.classList.remove("hidden");
  }

  // ---- discovery ----
  const expl = $("#expl"), explV = $("#expl-v");
  expl.addEventListener("input", () => (explV.textContent = (expl.value / 100).toFixed(2)));

  // Candidates from the last run, kept so a card can be evaluated whole.
  let discovered = [];
  // Delegated once on the container — #cands is re-rendered on every run.
  $("#cands").addEventListener("click", (e) => {
    const b = e.target.closest(".evalbtn");
    if (!b) return;
    const c = discovered[Number(b.dataset.idx)];
    if (c) evaluateDiscovered(c);
  });

  $("#disc-run").addEventListener("click", async () => {
    const btn = $("#disc-run");
    btn.disabled = true;
    const meta = $("#disc-meta"), cands = $("#cands");
    meta.textContent = "discovering stores & products…";
    cands.innerHTML = "";
    try {
      const body = {
        province: $("#disc-region").value,
        seed: $("#disc-seed").value.trim() || null,
        exploration: expl.value / 100,
        category_count: 4,
      };
      const r = await api("/api/v1/discovery/run", { json: body });
      meta.innerHTML =
        `Categories <b>${r.categories.map(esc).join(", ")}</b> · ` +
        `${r.stores_found} stores · ${r.products_seen} seen · <b>${r.products_new} fresh</b>`;
      discovered = r.candidates || [];
      cands.innerHTML =
        discovered
          .map(
            (c, i) => `
        <div class="cand">
          <div class="cn">${esc(c.name || c.upc || "candidate")}</div>
          <div class="cmeta">${esc(c.category_hint || "—")}${c.source_name ? " · " + esc(c.source_name) : ""}</div>
          <div class="cfoot"><span class="badge fresh">Fresh</span><button class="evalbtn" data-idx="${i}">Evaluate →</button></div>
        </div>`
          )
          .join("") || '<div class="note"><span>No fresh candidates — all discovered products were seen recently (TTL not yet expired).</span></div>';
    } catch (e) {
      meta.innerHTML = "";
      cands.innerHTML = `<div class="note err" style="grid-column:1/-1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg><span><b>Discovery needs the database.</b> ${esc(e.message)} — check Postgres is up <em>and</em> that migrations are applied (<code>alembic upgrade head</code>); a running DB with no tables fails exactly like this. The Evaluate view needs no DB at all.</span></div>`;
    } finally {
      btn.disabled = false;
    }
  });

  // ---- footer: provider status from /health ----
  $("#stamp").textContent = "rendered " + new Date().toISOString().slice(0, 10);
  fetch("/health")
    .then((r) => r.json())
    .then((h) => {
      $("#providers").textContent = `llm: ${h.llm_provider} · amazon: ${h.amazon_provider}`;
      if (h.env) $("#tier").textContent = h.env === "prod" ? "Premium" : "Free";
    })
    .catch(() => ($("#providers").textContent = "providers: offline"));
})();
