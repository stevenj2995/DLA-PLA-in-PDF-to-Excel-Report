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
const API = backendUrl();

const $ = (id) => document.getElementById(id);

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ESCAPES[c]);

function humanSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

// ---- backend ----
let limits = { files: 250, size: 15 };
let needsCode = false;

async function checkBackend() {
  const pill = $("status"), text = $("status-text");
  try {
    const r = await fetch(API + "/api/status", { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error("status " + r.status);
    const d = await r.json();

    limits = { files: d.max_files, size: d.max_file_mb };
    if (d.session_minutes) {
      document.querySelectorAll(".session-minutes")
        .forEach((el) => { el.textContent = d.session_minutes; });
    }
    needsCode = Boolean(d.needs_code);
    $("code-row").classList.toggle("hidden", !needsCode);

    pill.className = "status-pill status-live";
    text.textContent = "Siap";
    $("offline-notice").classList.add("hidden");
    updateSubmit();
    return true;
  } catch (e) {
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
    if (!f.name.toLowerCase().endsWith(".pdf")) { rejected.push(f.name + " (bukan PDF)"); continue; }
    if (f.size > limits.size * 1024 * 1024) {
      rejected.push(f.name + " (lebih dari " + limits.size + " MB)"); continue;
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
code.addEventListener("input", updateSubmit);

function updateSubmit() {
  const hasFiles = chosen.length > 0;
  const hasCode = !needsCode || code.value.trim().length > 0;
  submit.disabled = !(hasFiles && hasCode);
  if (!hasFiles) submitHint.textContent = "Pilih minimal satu PDF.";
  else if (!hasCode) submitHint.textContent = "Masukkan kode akses.";
  else submitHint.textContent = chosen.length + " PDF siap diproses";
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
  fd.append("on_mismatch", document.querySelector('input[name="mismatch"]:checked').value);
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

  $("block-preview").innerHTML = renderPreview(d);

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
