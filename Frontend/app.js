"use strict";

// Alamat backend: ?api=<url> menang dan diingat browser, lalu localStorage,
// lalu nilai bawaan di config.js.
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
function esc(t) {
  return String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function humanSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

// ------------------------------------------------------------- cek backend
let limits = { files: 10, size: 15 };
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
    updateSubmit();

    pill.className = "status-pill status-live";
    text.textContent = "Siap";
    $("offline-notice").classList.add("hidden");

    if (!d.ocr) {
      banner("amber",
        "OCR tidak aktif di server — PDF hasil pindaian tidak bisa dibaca isinya.");
    }
    return true;
  } catch (e) {
    pill.className = "status-pill status-down";
    text.textContent = "Tidak aktif";
    $("offline-notice").classList.remove("hidden");
    return false;
  }
}

function banner(color, message) {
  let box = $("startup-banner");
  if (!box) {
    box = document.createElement("div");
    box.id = "startup-banner";
    $("offline-notice").after(box);
  }
  box.innerHTML = '<div class="notice notice-' + color + '">' + esc(message) + "</div>";
}

// ---------------------------------------------------------------- pilih PDF
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
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      rejected.push(f.name + " (bukan PDF)"); continue;
    }
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
    b.addEventListener("click", () => {
      chosen.splice(Number(b.dataset.i), 1);
      renderFileList();
    }));
  updateSubmit();
}

// ------------------------------------------------------------------- tombol
const email = $("email"), submit = $("submit"), submitHint = $("submit-hint");
const code = $("code");
email.addEventListener("input", updateSubmit);
code.addEventListener("input", updateSubmit);

function updateSubmit() {
  const hasEmail = email.value.trim().length > 0 && email.value.includes("@");
  const hasFiles = chosen.length > 0;
  const hasCode = !needsCode || code.value.trim().length > 0;
  submit.disabled = !(hasEmail && hasFiles && hasCode);

  if (!hasFiles) submitHint.textContent = "Pilih minimal satu PDF.";
  else if (!hasEmail) submitHint.textContent = "Isi email Anda terlebih dahulu.";
  else if (!hasCode) submitHint.textContent = "Masukkan kode akses.";
  else submitHint.textContent = chosen.length + " PDF siap diproses";
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.classList.remove("hidden");
}
function hideError() { $("error").classList.add("hidden"); }

// ------------------------------------------------------------------- proses
submit.addEventListener("click", async () => {
  hideError();
  $("results").classList.add("hidden");
  $("loading").classList.remove("hidden");
  submit.disabled = true;

  const fd = new FormData();
  fd.append("email", email.value.trim());
  if (needsCode) fd.append("code", code.value.trim());
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

// -------------------------------------------------------------------- hasil
let currentSession = null;
let hasDownloaded = false;

function renderResults(d) {
  currentSession = d.session;
  hasDownloaded = false;
  $("finish-result").classList.add("hidden");
  $("finish-btn").disabled = false;
  $("finish-btn").textContent = "Saya sudah selesai — hapus data saya sekarang";

  const s = d.summary;
  $("stats").innerHTML = [
    ["PDF diproses", s.pdfs, "var(--blue)"],
    ["Baris jadi", s.ok, "var(--green)"],
    ["Perlu ditinjau", s.review, "var(--amber)"],
    ["Dilewati", s.skipped, "var(--red)"],
  ].map((x) =>
    '<div class="stat" style="border-left-color:' + x[2] + '">' +
    '<div class="value" style="color:' + x[2] + '">' + x[1] + "</div>" +
    '<div class="label">' + x[0] + "</div></div>").join("");

  let notes = "";
  (d.notes || []).forEach((t) => {
    notes += '<div class="notice notice-blue">' + esc(t) + "</div>";
  });
  if ((d.new_companies || []).length) {
    notes += '<div class="notice notice-green">Perusahaan baru dikenali: ' +
             d.new_companies.map(esc).join(", ") + "</div>";
  }
  $("block-notes").innerHTML = notes;

  $("block-excel").innerHTML = (d.excel || []).length
    ? "<h3>File Excel yang dihasilkan</h3>" + d.excel.map((e) =>
        '<div class="excel-row"><div class="excel-info">' +
        '<div class="excel-company">' + esc(e.company) + "</div>" +
        '<div class="excel-detail">' + e.rows + " baris &middot; " + esc(e.file_name) +
        (e.dropdowns_intact ? "" :
          ' &middot; <span style="color:var(--red)">dropdown tidak utuh (' +
          e.dropdowns_after + "/" + e.dropdowns_before + ")</span>") +
        "</div></div>" +
        '<a class="download" href="' + API + "/api/download/" +
        encodeURIComponent(d.session) + "/" + encodeURIComponent(e.id) +
        '">&#8595; Unduh Excel</a></div>').join("")
    : '<div class="notice notice-amber">Tidak ada Excel yang dihasilkan.</div>';

  $("block-review").innerHTML = (d.review || []).length
    ? "<h3>Perlu ditinjau</h3>" + d.review.map((h) =>
        "<details><summary>&#9888; " + esc(h.file) + " — " + esc(h.company) +
        " (keyakinan " + h.confidence + ')</summary><div class="details-body"><ul>' +
        h.warnings.map((w) => "<li>" + esc(w) + "</li>").join("") +
        "</ul></div></details>").join("")
    : "";

  $("block-skipped").innerHTML = (d.skipped || []).length
    ? "<h3>Dilewati</h3>" + d.skipped.map((h) =>
        '<div class="notice notice-amber">' + esc(h.file) + " — " +
        esc(h.reason) + "</div>").join("")
    : "";

  document.querySelectorAll(".download").forEach((a) =>
    a.addEventListener("click", () => { hasDownloaded = true; }));

  $("results").classList.remove("hidden");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// -------------------------------------------------------- selesai & hapus
$("finish-btn").addEventListener("click", async () => {
  if (!currentSession) return;

  const warning = hasDownloaded
    ? `Hapus semua data Anda dari server sekarang?

Yang dihapus: file Excel hasil, profil sementara, dan laporan proses.
Tautan unduhan di atas akan berhenti berfungsi.`
    : `Anda BELUM mengunduh file Excel-nya.

Kalau dihapus sekarang, hasilnya ikut hilang dan PDF harus diproses ulang
dari awal. Lanjutkan?`;
  if (!confirm(warning)) return;

  const btn = $("finish-btn");
  btn.disabled = true;
  btn.textContent = "Menghapus…";

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
    box.innerHTML = '<div class="notice notice-green"><strong>' + esc(d.message) +
      "</strong>" + (d.files ? "<p>" + d.files +
      " berkas sementara dihapus dari server.</p>" : "") + "</div>";
    box.classList.remove("hidden");
    btn.classList.add("hidden");
    currentSession = null;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Coba hapus lagi";
    showError(e.message === "Failed to fetch"
      ? "Tidak bisa menghubungi backend untuk menghapus. Data tetap akan " +
        "terhapus otomatis saat waktunya habis."
      : e.message);
  }
});

// Menutup tab juga menghapus sesi. Harus sendBeacon: fetch dibatalkan browser
// begitu halaman ditutup, jadi permintaannya tidak pernah sampai.
window.addEventListener("pagehide", () => {
  if (currentSession && navigator.sendBeacon) {
    navigator.sendBeacon(API + "/api/finish/" + encodeURIComponent(currentSession));
  }
});

checkBackend();
setInterval(checkBackend, 30000);
updateSubmit();
