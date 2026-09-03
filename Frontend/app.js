"use strict";

function backendUrl() {
  const fromQuery = new URLSearchParams(location.search).get("api");
  if (fromQuery) {
    try { localStorage.setItem("backend_url", fromQuery); } catch (e) {}
    return fromQuery.replace(/\/+$/, "");
  }
  let saved = null;
  try { saved = localStorage.getItem("backend_url"); } catch (e) {}
  return (saved || window.BACKEND_URL || "").replace(/\/+$/, "");
}
let API = backendUrl();

// A tunnel address is remembered from the ?api= link, but it dies when run.py
// is restarted. Rather than sit there saying "tidak aktif" forever, the page
// drops the stale one and falls back to the built-in address once.
let triedFallback = false;

const $ = (id) => document.getElementById(id);

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ESCAPES[c]);

function humanSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

// ---- backend ----
let limits = { files: 250, size: 15, zip: 200 };
let needsCode = false;

async function checkBackend() {
  const pill = $("status"), text = $("status-text");
  try {
    const r = await fetch(API + "/api/status", { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error("status " + r.status);
    const d = await r.json();

    limits = { files: d.max_files, size: d.max_file_mb, zip: d.max_zip_mb };
    if (d.session_minutes) {
      document.querySelectorAll(".session-minutes")
        .forEach((el) => { el.textContent = d.session_minutes; });
    }
    needsCode = Boolean(d.needs_code);
    $("code-row").classList.toggle("hidden", !needsCode);
    fillCompanies(d.companies || [], d.drafts || []);

    pill.className = "status-pill status-live";
    text.textContent = "Siap";
    $("offline-notice").classList.add("hidden");
    updateSubmit();
    return true;
  } catch (e) {
    const fallback = (window.BACKEND_URL || "").replace(/\/+$/, "");
    if (!triedFallback && fallback && fallback !== API) {
      triedFallback = true;
      try { localStorage.removeItem("backend_url"); } catch (_) {}
      API = fallback;
      return checkBackend();
    }
    pill.className = "status-pill status-down";
    text.textContent = "Tidak aktif";
    $("offline-notice").classList.remove("hidden");
    return false;
  }
}

// ---- pilih berkas ----
let chosen = [];
const dropzone = $("dropzone"), fileInput = $("file-input");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
["dragenter", "dragover"].forEach((n) =>
  dropzone.addEventListener(n, (e) => { e.preventDefault(); dropzone.classList.add("is-over"); }));
["dragleave", "drop"].forEach((n) =>
  dropzone.addEventListener(n, (e) => { e.preventDefault(); dropzone.classList.remove("is-over"); }));

dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });

function addFiles(list) {
  const rejected = [];
  for (const f of list) {
    const isZip = f.name.toLowerCase().endsWith(".zip");
    if (!isZip && !f.name.toLowerCase().endsWith(".pdf")) {
      rejected.push(f.name + " (bukan ZIP atau PDF)"); continue;
    }
    const ceiling = isZip ? limits.zip : limits.size;
    if (f.size > ceiling * 1024 * 1024) {
      rejected.push(f.name + " (lebih dari " + ceiling + " MB)"); continue;
    }
    if (chosen.some((x) => x.name === f.name && x.size === f.size)) continue;
    if (chosen.length >= limits.files) {
      rejected.push(f.name + " (melebihi " + limits.files + " berkas)"); continue;
    }
    chosen.push(f);
  }
  if (rejected.length) showError("Tidak bisa ditambahkan: " + rejected.join(", "));
  else hideError();
  renderFileList();
}

// A batch runs to a couple of hundred files, and listing them all buries the
// rest of the page. Only the first few are shown until asked otherwise, and the
// full list is a box that scrolls on its own rather than stretching the page.
const PREVIEW_FILES = 5;
let showAllFiles = false;

function renderFileList() {
  const ul = $("file-list"), summary = $("file-summary"), more = $("file-more");
  const total = chosen.length;

  if (!total) {
    ul.innerHTML = "";
    summary.classList.add("hidden");
    more.classList.add("hidden");
    showAllFiles = false;
    updateSubmit();
    return;
  }

  const bytes = chosen.reduce((sum, f) => sum + f.size, 0);
  summary.classList.remove("hidden");
  summary.innerHTML =
    "<span><strong>" + total + " berkas</strong> &middot; " + humanSize(bytes) + "</span>" +
    '<button type="button" class="link-btn" id="clear-files">Kosongkan</button>';

  const shown = showAllFiles ? chosen : chosen.slice(0, PREVIEW_FILES);
  ul.classList.toggle("is-scrollable", showAllFiles && total > PREVIEW_FILES);
  ul.innerHTML = shown.map((f) => {
    const i = chosen.indexOf(f);
    return '<li><span class="file-name">' + esc(f.name) + "</span>" +
      '<span class="file-size">' + humanSize(f.size) + "</span>" +
      '<button class="remove" data-i="' + i + '" title="Buang" aria-label="Buang ' +
      esc(f.name) + '">&times;</button></li>';
  }).join("");

  if (total > PREVIEW_FILES) {
    more.classList.remove("hidden");
    more.innerHTML = '<button type="button" class="link-btn" id="toggle-files">' +
      (showAllFiles ? "Tampilkan " + PREVIEW_FILES + " saja"
                    : "Tampilkan semua (" + total + " berkas)") + "</button>";
    $("toggle-files").addEventListener("click", () => {
      showAllFiles = !showAllFiles;
      renderFileList();
    });
  } else {
    more.classList.add("hidden");
  }

  $("clear-files").addEventListener("click", () => {
    chosen = [];
    hideError();
    renderFileList();
  });
  ul.querySelectorAll(".remove").forEach((b) =>
    b.addEventListener("click", () => { chosen.splice(Number(b.dataset.i), 1); renderFileList(); }));
  updateSubmit();
}

// ---- tombol ----
const submit = $("submit"), submitHint = $("submit-hint"), code = $("code");
const company = $("company");
code.addEventListener("input", updateSubmit);

// Drawn as cards rather than a dropdown: there are only a handful of companies,
// and the ones not in service yet are worth showing as such instead of being
// invisible.
function fillCompanies(list, drafts) {
  const grid = $("company-grid");
  if (grid.dataset.filled === "1") return;

  const face = (c, sub) =>
    '<span class="badge">' + esc(initials(c.name)) + "</span>" +
    '<span class="text"><span class="name">' + esc(c.name) + "</span>" +
    '<span class="sub">' + sub + "</span></span>";

  const cards = list.map((c) =>
    '<button type="button" class="company-card" data-key="' + esc(c.key) + '">' +
    face(c, "Siap dipakai") + "</button>").join("");
  const off = (drafts || []).map((c) =>
    '<span class="company-card is-off" title="Daftar kolomnya belum ditinjau">' +
    face(c, "Belum aktif") + "</span>").join("");

  grid.innerHTML = (cards + off) ||
    '<div class="company-card is-loading">Belum ada perusahaan yang didukung</div>';
  grid.dataset.filled = "1";

  grid.querySelectorAll(".company-card[data-key]").forEach((card) =>
    card.addEventListener("click", () => pickCompany(card.dataset.key)));

  if (list.length === 1) pickCompany(list[0].key);
  updateSubmit();
}

function initials(name) {
  const letters = String(name || "").replace(/[^A-Za-z]/g, "");
  return letters.slice(0, 3).toUpperCase() || "?";
}

function pickCompany(key) {
  company.value = key;
  $("company-grid").querySelectorAll(".company-card[data-key]").forEach((card) =>
    card.classList.toggle("is-on", card.dataset.key === key));
  updateSubmit();
}

function updateSubmit() {
  const hasFiles = chosen.length > 0;
  const hasCompany = Boolean(company.value);
  const hasCode = !needsCode || code.value.trim().length > 0;
  submit.disabled = !(hasFiles && hasCompany && hasCode);
  if (!hasCompany) submitHint.textContent = "Pilih perusahaannya dulu.";
  else if (!hasFiles) submitHint.textContent = "Pilih berkas ZIP atau PDF.";
  else if (!hasCode) submitHint.textContent = "Masukkan kode akses.";
  else submitHint.textContent = chosen.length + " berkas siap diproses";
}

function showError(m) { const b = $("error"); b.textContent = m; b.classList.remove("hidden"); }
function hideError() { $("error").classList.add("hidden"); }

// ---- proses ----
submit.addEventListener("click", async () => {
  hideError();
  $("results").classList.add("hidden");
  $("loading").classList.remove("hidden");
  submit.disabled = true;

  const fd = new FormData();
  if (needsCode) fd.append("code", code.value.trim());
  fd.append("company", company.value);
  chosen.forEach((f) => fd.append("files", f, f.name));

  try {
    const r = await fetch(API + "/api/process", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Gagal memproses (HTTP " + r.status + ")");
    renderResults(d);
  } catch (e) {
    showError(e.message === "Failed to fetch"
      ? "Tidak bisa menghubungi backend. Komputer pemroses mungkin sedang mati."
      : e.message);
    checkBackend();
  } finally {
    $("loading").classList.add("hidden");
    updateSubmit();
  }
});

// ---- hasil ----
let currentSession = null;

function renderResults(d) {
  currentSession = d.session;
  $("finish-result").classList.add("hidden");
  $("finish-btn").classList.remove("hidden");
  $("finish-btn").disabled = false;
  $("finish-btn").textContent = "Saya sudah selesai - hapus data saya sekarang";

  const s = d.summary || {};
  $("stats").innerHTML = [
    ["PDF dibaca", s.pdfs, "var(--blue)"],
    ["Baris jadi", s.rows, "var(--green)"],
    ["Tabel", s.tables, "var(--cyan)"],
    ["Dilewati", s.skipped, s.skipped ? "var(--amber)" : "var(--text-faint)"],
  ].map((x) =>
    '<div class="stat" style="border-left-color:' + x[2] + '">' +
    '<div class="value" style="color:' + x[2] + '">' + (x[1] == null ? 0 : x[1]) + "</div>" +
    '<div class="label">' + x[0] + "</div></div>").join("");

  let head = "";
  if (d.company) {
    head += '<div class="company-tag">Perusahaan: ' + esc(d.company) + "</div>";
  }
  if (d.rejected) {
    head += '<div class="notice notice-red">' + esc(d.rejected) + "</div>";
  }
  $("block-notes").innerHTML = head + renderNotes(d.notes || []);

  $("block-excel").innerHTML = d.excel
    ? '<div class="excel-row"><div class="excel-info">' +
      '<div class="excel-company">' + esc(d.excel.file_name) + "</div>" +
      '<div class="excel-detail">' + d.excel.rows + " baris" +
      (d.excel.tables > 1 ? " &middot; " + d.excel.tables + " tabel" : "") + "</div></div>" +
      '<a class="download" href="' + API + "/api/download/" +
      encodeURIComponent(d.session) + "/" + encodeURIComponent(d.excel.id) +
      '">&#8595; Unduh Excel</a></div>'
    : (d.rejected ? "" : '<div class="notice notice-amber">Tidak ada Excel yang dihasilkan.</div>');

  $("block-skipped").innerHTML = renderSkipped(d.skipped || []);
  $("block-preview").innerHTML = renderPreview(d);

  $("results").classList.remove("hidden");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Every note is one line. The list behind it -- which can run to seventy file
// names -- stays folded until asked for, so the page reads at a glance.
function renderNotes(notes) {
  if (!notes.length) return "";
  return '<div class="panel note-panel"><h3 class="panel-title">Catatan</h3><ul class="note-list">' +
    notes.map((n) =>
      '<li class="note note-' + esc(n.level || "info") + '">' +
      "<span>" + esc(n.text) + "</span>" +
      ((n.detail || []).length
        ? "<details><summary>Lihat " + n.detail.length + " rincian</summary>" +
          '<ul class="detail-list">' +
          n.detail.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul></details>"
        : "") +
      "</li>").join("") + "</ul></div>";
}

// Skipped files are grouped by why, so twenty files sharing a reason are one
// line instead of twenty cards.
function renderSkipped(groups) {
  if (!groups.length) return "";
  const total = groups.reduce((n, g) => n + g.files.length, 0);
  return '<div class="panel note-panel"><h3 class="panel-title">Dilewati (' + total +
    " berkas)</h3><ul class=\"note-list\">" +
    groups.map((g) =>
      '<li class="note note-warn"><span>' + g.files.length + " berkas &mdash; " +
      esc(g.reason) + "</span><details><summary>Lihat daftarnya</summary>" +
      '<ul class="detail-list">' + g.files.map((f) => "<li>" + esc(f) + "</li>").join("") +
      "</ul></details></li>").join("") + "</ul></div>";
}

// One table per set of parameters, each in its own card so the caption stays
// readable against the page behind it.
function renderPreview(d) {
  const groups = d.groups || [];
  if (!groups.length) return "";
  return '<h2 class="section-heading">Pratinjau</h2>' + groups.map((g, n) => {
    const head = "<tr>" + g.headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr>";
    const body = (g.preview || []).map((r) =>
      "<tr>" + g.headers.map((_, i) => "<td>" + esc(r[i]) + "</td>").join("") + "</tr>").join("");
    const shown = (g.preview || []).length;
    return '<div class="panel table-card">' +
      '<h3 class="panel-title">' + (groups.length > 1 ? "Tabel " + (n + 1) + " &middot; " : "") +
      esc(g.caption) + "</h3>" +
      '<div class="preview-wrap"><table class="preview"><thead>' + head +
      "</thead><tbody>" + body + "</tbody></table></div>" +
      (g.rows > shown
        ? '<p class="preview-note">Menampilkan ' + shown + " dari " + g.rows +
          " baris. Selengkapnya ada di Excel.</p>"
        : "") + "</div>";
  }).join("");
}

// ---- hapus data ----
const CONFIRM_TEXT =
  "Excel hasil akan dihapus dari server sekarang juga. Pastikan Anda sudah mengunduhnya. Lanjutkan?";

$("finish-btn").addEventListener("click", async () => {
  if (!currentSession) return;
  if (!confirm(CONFIRM_TEXT)) return;

  const btn = $("finish-btn");
  btn.disabled = true;
  btn.textContent = "Menghapus...";

  try {
    const r = await fetch(API + "/api/finish/" + encodeURIComponent(currentSession),
                          { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Gagal menghapus (HTTP " + r.status + ")");

    document.querySelectorAll(".download").forEach((a) => {
      a.removeAttribute("href");
      a.classList.add("download-off");
      a.textContent = "Sudah dihapus";
    });
    const box = $("finish-result");
    box.innerHTML = '<div class="notice notice-green"><strong>' + esc(d.message) + "</strong>" +
      (d.files ? "<p>" + d.files + " berkas sementara dihapus dari server.</p>" : "") + "</div>";
    box.classList.remove("hidden");
    btn.classList.add("hidden");
    currentSession = null;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Coba hapus lagi";
    showError(e.message === "Failed to fetch"
      ? "Backend sedang offline. Data tetap terhapus otomatis saat waktunya habis."
      : e.message);
  }
});

window.addEventListener("pagehide", () => {
  if (currentSession && navigator.sendBeacon) {
    navigator.sendBeacon(API + "/api/finish/" + encodeURIComponent(currentSession));
  }
});

checkBackend();
setInterval(checkBackend, 30000);
updateSubmit();
