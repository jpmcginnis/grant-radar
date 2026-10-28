// Grant Radar dashboard. Pure vanilla JS; no build step.
// Reads data/opportunities.json; status edits persist to localStorage.

const STATE = {
  all: [],
  filtered: [],
  sort: { key: "fit_score", dir: "desc" },
  view: "table",
};

const STATUSES = ["new", "interested", "drafting", "submitted", "declined", "dismissed"];

// --- storage ---------------------------------------------------------------

function loadLocalEdits() {
  try { return JSON.parse(localStorage.getItem("grant-radar-edits") || "{}"); }
  catch { return {}; }
}
function saveLocalEdits(edits) {
  localStorage.setItem("grant-radar-edits", JSON.stringify(edits));
}
function applyLocalEdits(opps) {
  const edits = loadLocalEdits();
  for (const o of opps) {
    if (edits[o.id]) {
      Object.assign(o, edits[o.id]);
    }
  }
  return opps;
}
function recordEdit(id, patch) {
  const edits = loadLocalEdits();
  edits[id] = Object.assign(edits[id] || {}, patch);
  saveLocalEdits(edits);
}

// --- date helpers ----------------------------------------------------------

const TODAY = new Date();
TODAY.setHours(0, 0, 0, 0);

function parseISO(s) {
  if (!s) return null;
  const d = new Date(s + "T00:00:00");
  return isNaN(d) ? null : d;
}
function daysOut(dateStr) {
  const d = parseISO(dateStr);
  if (!d) return null;
  return Math.round((d - TODAY) / 86400000);
}
function fmtDue(opp) {
  const due = opp.loi_due || opp.app_due;
  if (!due) return { text: "—", kls: "far" };
  const n = daysOut(due);
  const kind = opp.loi_due === due ? "LOI" : "App";
  let kls = "far";
  if (n === null) kls = "far";
  else if (n < 0) kls = "far";
  else if (n <= 30) kls = "urgent";
  else if (n <= 90) kls = "soon";
  return { text: `${due} <em>${kind}${n !== null ? ` · ${n}d` : ""}</em>`, kls };
}

// --- load ------------------------------------------------------------------

async function load() {
  try {
    const r = await fetch("data/opportunities.json?v=" + Date.now());
    const data = await r.json();
    STATE.all = applyLocalEdits(data);
  } catch {
    STATE.all = [];
  }
  const updated = STATE.all.reduce(
    (max, o) => (o.last_seen && o.last_seen > max ? o.last_seen : max),
    ""
  );
  document.getElementById("updated").textContent = updated ? `· updated ${updated}` : "";
  applyFilters();
  renderDrafts();
}

// --- filters & sort --------------------------------------------------------

function applyFilters() {
  const q = document.getElementById("search").value.toLowerCase().trim();
  const bucket = document.getElementById("bucket").value;
  const status = document.getElementById("status").value;
  const onlyOpen = document.getElementById("only-open").checked;
  const minFit = document.getElementById("min-fit").checked;

  STATE.filtered = STATE.all.filter((o) => {
    if (q) {
      const hay = `${o.title} ${o.sponsor} ${o.mechanism} ${o.purpose || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (bucket && o.bucket !== bucket) return false;
    if (status && (o.status || "new") !== status) return false;
    if (onlyOpen) {
      const due = o.loi_due || o.app_due;
      if (!due) return true; // rolling
      const n = daysOut(due);
      if (n === null || n < 0) return false;
    }
    if (minFit && (o.fit_score || 0) < 50) return false;
    return true;
  });

  STATE.filtered.sort((a, b) => {
    const k = STATE.sort.key;
    const dir = STATE.sort.dir === "asc" ? 1 : -1;
    const va = a[k] ?? (k === "fit_score" ? -1 : "");
    const vb = b[k] ?? (k === "fit_score" ? -1 : "");
    if (va < vb) return -1 * dir;
    if (va > vb) return 1 * dir;
    return 0;
  });

  renderTable();
  renderCalendar();
}

// --- renders ---------------------------------------------------------------

function renderTable() {
  const tbody = document.querySelector("#opps-table tbody");
  tbody.innerHTML = "";
  for (const o of STATE.filtered) {
    const due = fmtDue(o);
    const fitKls = o.fit_score >= 65 ? "high" : o.fit_score >= 40 ? "mid" : "low";
    const status = o.status || "new";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="num fit-cell ${fitKls}">${(o.fit_score || 0).toFixed(0)}</td>
      <td class="due-cell ${due.kls}">${due.text}</td>
      <td>${escapeHtml(o.title)}</td>
      <td>${escapeHtml(o.sponsor)}</td>
      <td>${escapeHtml(o.mechanism)}</td>
      <td><span class="status-chip ${status}">${status}</span></td>
    `;
    tr.addEventListener("click", () => showDetail(o));
    tbody.appendChild(tr);
  }
  document.getElementById("count").textContent =
    `${STATE.filtered.length} of ${STATE.all.length} opportunities`;
}

function renderCalendar() {
  const cal = document.getElementById("calendar");
  cal.innerHTML = "";
  const buckets = new Map();
  for (const o of STATE.filtered) {
    const due = o.loi_due || o.app_due;
    if (!due) continue;
    const d = parseISO(due);
    if (!d) continue;
    if (d < TODAY) continue;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push({ opp: o, date: d, due, kind: o.loi_due === due ? "LOI" : "App" });
  }
  const keys = [...buckets.keys()].sort();
  for (const key of keys) {
    const [y, m] = key.split("-");
    const label = new Date(Number(y), Number(m) - 1, 1).toLocaleString("default", {
      month: "long",
      year: "numeric",
    });
    const items = buckets.get(key).sort((a, b) => a.date - b.date);
    const col = document.createElement("div");
    col.className = "cal-month";
    col.innerHTML = `<h3>${label}</h3>` + items.map((i) => {
      const day = String(i.date.getDate()).padStart(2, "0");
      return `<div class="cal-item" data-id="${i.opp.id}">
        <span class="cal-date">${day} ${i.kind}</span> ${escapeHtml(i.opp.title)}
      </div>`;
    }).join("");
    cal.appendChild(col);
  }
  cal.querySelectorAll(".cal-item").forEach((el) => {
    el.addEventListener("click", () => {
      const o = STATE.all.find((x) => x.id === el.dataset.id);
      if (o) showDetail(o);
    });
  });
}

function renderDrafts() {
  const list = document.getElementById("drafts-list");
  const withAims = STATE.all.filter((o) => o.aims_skeleton);
  withAims.sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0));
  list.innerHTML = withAims.length
    ? withAims
        .map(
          (o) =>
            `<li><a href="#" data-id="${o.id}">${escapeHtml(o.title)}</a> — ${escapeHtml(
              o.sponsor
            )} · fit ${(o.fit_score || 0).toFixed(0)}</li>`
        )
        .join("")
    : "<li>No drafts yet. Attach aims to the top new opportunities each week.</li>";
  list.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const o = STATE.all.find((x) => x.id === a.dataset.id);
      if (o) showDetail(o);
    });
  });
}

function showDetail(opp) {
  const body = document.getElementById("detail-body");
  const due = fmtDue(opp);
  body.innerHTML = `
    <h2>${escapeHtml(opp.title)}</h2>
    <p class="meta">${escapeHtml(opp.sponsor)} · ${escapeHtml(opp.mechanism)}</p>
    <p class="meta">Due: ${due.text}</p>
    <p class="meta">Fit score: <strong>${(opp.fit_score || 0).toFixed(1)}</strong> / 100</p>
    <p class="meta"><em>${escapeHtml(opp.fit_rationale || "")}</em></p>
    <p class="meta">Matched pillars: ${(opp.matched_pillars || []).map(escapeHtml).join(", ") || "—"}</p>
    <p><a href="${opp.source_url}" target="_blank" rel="noopener">Open full solicitation →</a></p>
    <div class="actions">
      ${STATUSES.map(
        (s) =>
          `<button class="status-btn ${
            (opp.status || "new") === s ? "active" : ""
          }" data-status="${s}">${s}</button>`
      ).join("")}
    </div>
    ${opp.purpose ? `<h3>Purpose</h3><p>${escapeHtml(opp.purpose)}</p>` : ""}
    ${opp.budget_summary ? `<h3>Budget</h3><p>${escapeHtml(opp.budget_summary)}</p>` : ""}
    ${opp.eligibility_summary ? `<h3>Eligibility</h3><p>${escapeHtml(opp.eligibility_summary)}</p>` : ""}
    ${opp.aims_skeleton ? `<h3>Draft aims skeleton</h3><pre>${escapeHtml(opp.aims_skeleton)}</pre>` : ""}
  `;
  body.querySelectorAll(".status-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const newStatus = btn.dataset.status;
      opp.status = newStatus;
      recordEdit(opp.id, { status: newStatus });
      applyFilters();
      showDetail(opp);
    });
  });
  document.getElementById("detail-pane").classList.remove("hidden");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// --- events ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      document.getElementById("view-" + t.dataset.view).classList.add("active");
      STATE.view = t.dataset.view;
    })
  );
  document.getElementById("search").addEventListener("input", applyFilters);
  document.getElementById("bucket").addEventListener("change", applyFilters);
  document.getElementById("status").addEventListener("change", applyFilters);
  document.getElementById("only-open").addEventListener("change", applyFilters);
  document.getElementById("min-fit").addEventListener("change", applyFilters);
  document.querySelectorAll("th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (STATE.sort.key === k) {
        STATE.sort.dir = STATE.sort.dir === "asc" ? "desc" : "asc";
      } else {
        STATE.sort.key = k;
        STATE.sort.dir = k === "fit_score" ? "desc" : "asc";
      }
      applyFilters();
    })
  );
  document.querySelector("#detail-pane .close").addEventListener("click", () => {
    document.getElementById("detail-pane").classList.add("hidden");
  });
  load();
});
