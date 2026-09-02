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

function renderFileList() {
  const ul = $("file-list");
  ul.innerHTML = chosen.map((f, i) =>
    '<li><span class="file-name">' + esc(f.name) + "</span>" +
    '<span class="file-size">' + humanSize(f.size) + "</span>" +
    '<button class="remove" data-i="' + i + '" title="Buang" aria-label="Buang ' +
    esc(f.name) + '">&times;</button></li>').join("");
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
    ["Kolom", s.columns, "var(--cyan)"],
    ["Dilewati", s.skipped, s.skipped ? "var(--red)" : "var(--text-faint)"],
  ].map((x) =>
    '<div class="stat" style="border-left-color:' + x[2] + '">' +
    '<div class="value" style="color:' + x[2] + '">' + (x[1] == null ? 0 : x[1]) + "</div>" +
    '<div class="label">' + x[0] + "</div></div>").join("");

  let notes = "";
  if (d.company) {
    notes += '<div class="company-tag">Perusahaan terdeteksi: ' + esc(d.company) + "</div>";
  }
  if (d.rejected) {
    notes += '<div class="notice notice-red">' + esc(d.rejected) + "</div>";
  }
  (d.notes || []).forEach((t) => {
    notes += '<div class="notice notice-blue">' + esc(t) + "</div>";
  });
  $("block-notes").innerHTML = notes;

  $("block-excel").innerHTML = d.excel
    ? '<div class="excel-row"><div class="excel-info">' +
      '<div class="excel-company">' + esc(d.excel.file_name) + "</div>" +
      '<div class="excel-detail">' + d.excel.rows + " baris &middot; " +
      d.excel.columns + " kolom</div></div>" +
      '<a class="download" href="' + API + "/api/download/" +
      encodeURIComponent(d.session) + "/" + encodeURIComponent(d.excel.id) +
      '">&#8595; Unduh Excel</a></div>'
    : (d.rejected ? "" : '<div class="notice notice-amber">Tidak ada Excel yang dihasilkan.</div>');

  $("block-decision").innerHTML = d.needs_decision ? renderDecision(d) : "";
  if (d.needs_decision) {
    $("decide-merge").addEventListener("click", () => decide("merge"));
    $("decide-reject").addEventListener("click", () => decide("reject"));
  }
  $("cleanup").classList.toggle("hidden", !d.excel);

  $("block-preview").innerHTML = renderPreview(d);

  $("block-scanned").innerHTML = (d.scanned || []).length
    ? '<div class="notice notice-amber"><strong>Dibaca lewat OCR: ' +
      d.scanned.map(esc).join(", ") + "</strong>" +
      "<p>Berkas ini tidak punya lapisan teks, jadi isinya dikenali dari gambar. " +
      "Satu huruf atau angka bisa salah baca tanpa terlihat keliru - mohon " +
      "cocokkan barisnya dengan dokumen asli.</p></div>"
    : "";

  $("block-deviating").innerHTML = (d.deviating || []).length
    ? "<h3>Parameternya menyimpang</h3>" + d.deviating.map((f) =>
        "<details><summary>&#9888; " + esc(f.file) + "</summary>" +
        '<div class="details-body"><ul>' +
        (f.missing.length ? "<li>Tidak ada: " + f.missing.map(esc).join(", ") + "</li>" : "") +
        (f.extra.length ? "<li>Tambahan: " + f.extra.map(esc).join(", ") + "</li>" : "") +
        "</ul></div></details>").join("")
    : "";

  $("block-skipped").innerHTML = (d.skipped || []).length
    ? "<h3>Dilewati</h3>" + d.skipped.map((f) =>
        '<div class="notice notice-amber">' + esc(f.file) + " - " + esc(f.reason) + "</div>").join("")
    : "";

  $("results").classList.remove("hidden");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Only ever shown when a batch actually turned out uneven. One company's DLAs
// are supposed to be identical, so this is a signal that something is wrong
// with the batch rather than a setting to pick beforehand.
function renderDecision(d) {
  const files = (d.deviating || []).map((f) =>
    "<li><strong>" + esc(f.file) + "</strong>" +
    (f.missing.length ? "<br>tidak ada: " + f.missing.map(esc).join(", ") : "") +
    (f.extra.length ? "<br>tambahan: " + f.extra.map(esc).join(", ") : "") +
    "</li>").join("");
  return '<div class="notice notice-amber"><strong>' + d.summary.deviating +
    " dari " + d.summary.rows + " berkas parameternya tidak sama dengan yang lain." +
    "</strong><p>Satu perusahaan seharusnya seragam, jadi ini tanda ada berkas " +
    "yang salah masuk atau gagal terbaca:</p><ul>" + files + "</ul></div>" +
    '<div class="action-row">' +
    '<button id="decide-merge">Gabungkan semua &amp; buat Excel</button>' +
    '<button id="decide-reject" class="btn-danger">Batalkan batch ini</button>' +
    "</div>" +
    '<p class="field-note">Gabungkan: parameter tambahan jadi kolom baru, yang ' +
    "tidak ada dikosongkan, tidak ada data yang hilang. Batalkan: tidak ada " +
    "Excel yang dibuat dan datanya langsung dihapus.</p>";
}

async function decide(keep) {
  if (!currentSession) return;
  $("block-decision").innerHTML = '<div class="loading"><span class="spinner"></span>' +
    "<span>Menyelesaikan…</span></div>";
  const fd = new FormData();
  fd.append("keep", keep);
  try {
    const r = await fetch(API + "/api/decide/" + encodeURIComponent(currentSession),
                          { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Gagal (HTTP " + r.status + ")");
    renderResults(d);
  } catch (e) {
    $("block-decision").innerHTML = "";
    showError(e.message);
  }
}

function renderPreview(d) {
  const rows = d.preview || [], headers = d.headers || [];
  if (!rows.length) return "";
  const head = "<tr>" + headers.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr>";
  const body = rows.map((r) =>
    "<tr>" + headers.map((_, i) => "<td>" + esc(r[i]) + "</td>").join("") + "</tr>").join("");
  const more = d.summary.rows > rows.length
    ? '<p class="preview-note">Menampilkan ' + rows.length + " dari " +
      d.summary.rows + " baris. Selengkapnya ada di Excel.</p>"
    : "";
  return '<h3>Pratinjau</h3><div class="preview-wrap"><table class="preview"><thead>' +
         head + "</thead><tbody>" + body + "</tbody></table></div>" + more;
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
