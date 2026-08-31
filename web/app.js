"use strict";

// ---------------------------------------------------------- alamat backend
// Urutan: ?api=... di URL  ->  yang pernah dipakai (localStorage)  ->  config.js
function alamatBackend() {
  const dariUrl = new URLSearchParams(location.search).get("api");
  if (dariUrl) {
    try { localStorage.setItem("alamat_backend", dariUrl); } catch (e) {}
    return dariUrl.replace(/\/+$/, "");
  }
  let tersimpan = null;
  try { tersimpan = localStorage.getItem("alamat_backend"); } catch (e) {}
  return (tersimpan || window.ALAMAT_BACKEND || "").replace(/\/+$/, "");
}
const API = alamatBackend();

const $ = (id) => document.getElementById(id);

// Isi PDF datang dari luar dan ikut ditampilkan di halaman ini (nama perusahaan,
// nama berkas, teks peringatan). Semuanya harus dilewatkan fungsi ini dulu,
// kalau tidak PDF yang dirancang jahat bisa menyuntikkan HTML ke halaman.
const LOLOS = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function aman(t) {
  return String(t == null ? "" : t).replace(/[&<>"']/g, (c) => LOLOS[c]);
}

function ukuranTerbaca(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

// ------------------------------------------------------------- cek backend
let batas = { berkas: 10, ukuran: 15 };
let perluKode = false;

async function cekBackend() {
  const lampu = $("lampu"), teks = $("lampu-teks");
  try {
    const r = await fetch(API + "/api/status", { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error("status " + r.status);
    const d = await r.json();

    batas = { berkas: d.maks_berkas, ukuran: d.maks_ukuran_mb };
    $("maks-berkas").textContent = d.maks_berkas;
    $("maks-ukuran").textContent = d.maks_ukuran_mb;
    if (d.umur_sesi_menit) $("umur-sesi").textContent = d.umur_sesi_menit;

    perluKode = Boolean(d.perlu_kode);
    $("baris-kode").classList.toggle("tersembunyi", !perluKode);
    perbaruiTombol();

    lampu.className = "lampu lampu-hidup";
    teks.textContent = "Siap";
    $("peringatan-mati").classList.add("tersembunyi");

    if (!d.ocr) {
      kabarAwal("kuning",
        "OCR tidak aktif di server — PDF hasil pindaian tidak bisa dibaca isinya.");
    }
    return true;
  } catch (e) {
    lampu.className = "lampu lampu-mati";
    teks.textContent = "Tidak aktif";
    $("peringatan-mati").classList.remove("tersembunyi");
    return false;
  }
}

function kabarAwal(warna, pesan) {
  let w = $("kabar-awal");
  if (!w) {
    w = document.createElement("div");
    w.id = "kabar-awal";
    $("peringatan-mati").after(w);
  }
  w.innerHTML = '<div class="kabar kabar-' + warna + '">' + aman(pesan) + "</div>";
}

// --------------------------------------------------------------- pilih PDF
let terpilih = [];

const jatuhkan = $("jatuhkan"), inputBerkas = $("berkas");

jatuhkan.addEventListener("click", () => inputBerkas.click());
jatuhkan.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputBerkas.click(); }
});
["dragenter", "dragover"].forEach((n) =>
  jatuhkan.addEventListener(n, (e) => { e.preventDefault(); jatuhkan.classList.add("siap"); }));
["dragleave", "drop"].forEach((n) =>
  jatuhkan.addEventListener(n, (e) => { e.preventDefault(); jatuhkan.classList.remove("siap"); }));

jatuhkan.addEventListener("drop", (e) => tambah(e.dataTransfer.files));
inputBerkas.addEventListener("change", () => { tambah(inputBerkas.files); inputBerkas.value = ""; });

function tambah(daftar) {
  const ditolak = [];
  for (const f of daftar) {
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      ditolak.push(f.name + " (bukan PDF)"); continue;
    }
    if (f.size > batas.ukuran * 1024 * 1024) {
      ditolak.push(f.name + " (lebih dari " + batas.ukuran + " MB)"); continue;
    }
    if (terpilih.some((x) => x.name === f.name && x.size === f.size)) continue;
    if (terpilih.length >= batas.berkas) {
      ditolak.push(f.name + " (melebihi " + batas.berkas + " berkas)"); continue;
    }
    terpilih.push(f);
  }
  if (ditolak.length) galat("Tidak bisa ditambahkan: " + ditolak.join(", "));
  else sembunyikanGalat();
  gambarDaftar();
}

function gambarDaftar() {
  const ul = $("daftar-berkas");
  ul.innerHTML = terpilih.map((f, i) =>
    '<li><span class="nama">' + aman(f.name) + "</span>" +
    '<span class="ukuran">' + ukuranTerbaca(f.size) + "</span>" +
    '<button class="buang" data-i="' + i + '" title="Buang" aria-label="Buang ' +
    aman(f.name) + '">&times;</button></li>').join("");

  ul.querySelectorAll(".buang").forEach((b) =>
    b.addEventListener("click", () => {
      terpilih.splice(Number(b.dataset.i), 1);
      gambarDaftar();
    }));
  perbaruiTombol();
}

// ------------------------------------------------------------------ tombol
const email = $("email"), tombol = $("tombol"), alasan = $("tombol-alasan");
const kode = $("kode");
email.addEventListener("input", perbaruiTombol);
kode.addEventListener("input", perbaruiTombol);

function perbaruiTombol() {
  const adaEmail = email.value.trim().length > 0 && email.value.includes("@");
  const adaBerkas = terpilih.length > 0;
  const adaKode = !perluKode || kode.value.trim().length > 0;
  tombol.disabled = !(adaEmail && adaBerkas && adaKode);

  if (!adaBerkas) alasan.textContent = "Pilih minimal satu PDF.";
  else if (!adaEmail) alasan.textContent = "Isi email Anda terlebih dahulu.";
  else if (!adaKode) alasan.textContent = "Masukkan kode akses.";
  else alasan.textContent = terpilih.length + " PDF siap diproses";
}

function galat(p) {
  const g = $("galat");
  g.textContent = p;
  g.classList.remove("tersembunyi");
}
function sembunyikanGalat() { $("galat").classList.add("tersembunyi"); }

// ------------------------------------------------------------------ proses
tombol.addEventListener("click", async () => {
  sembunyikanGalat();
  $("hasil").classList.add("tersembunyi");
  $("memuat").classList.remove("tersembunyi");
  tombol.disabled = true;

  const fd = new FormData();
  fd.append("email", email.value.trim());
  if (perluKode) fd.append("kode", kode.value.trim());
  terpilih.forEach((f) => fd.append("berkas", f, f.name));

  try {
    const r = await fetch(API + "/api/proses", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Gagal memproses (HTTP " + r.status + ")");
    gambarHasil(d);
  } catch (e) {
    galat(e.message === "Failed to fetch"
      ? "Tidak bisa menghubungi backend. Komputer pemroses mungkin sedang mati."
      : e.message);
    cekBackend();
  } finally {
    $("memuat").classList.add("tersembunyi");
    perbaruiTombol();
  }
});

// ------------------------------------------------------------------- hasil
function gambarHasil(d) {
  const s = d.ringkasan;
  $("statistik").innerHTML = [
    ["PDF diproses", s.pdf, "var(--biru)"],
    ["Baris jadi", s.berhasil, "var(--hijau)"],
    ["Perlu ditinjau", s.ditinjau, "var(--kuning)"],
    ["Dilewati", s.dilewati, "var(--merah)"],
  ].map((x) =>
    '<div class="stat" style="border-left-color:' + x[2] + '">' +
    '<div class="angka" style="color:' + x[2] + '">' + x[1] + "</div>" +
    '<div class="label">' + x[0] + "</div></div>").join("");

  let c = "";
  (d.catatan || []).forEach((t) => {
    c += '<div class="kabar kabar-biru">' + aman(t) + "</div>";
  });
  if ((d.perusahaan_baru || []).length) {
    c += '<div class="kabar kabar-hijau">Perusahaan baru dikenali: ' +
         d.perusahaan_baru.map(aman).join(", ") + "</div>";
  }
  $("blok-catatan").innerHTML = c;

  $("blok-excel").innerHTML = (d.excel || []).length
    ? "<h3>File Excel yang dihasilkan</h3>" + d.excel.map((e) =>
        '<div class="baris-excel"><div class="keterangan">' +
        '<div class="prsh">' + aman(e.perusahaan) + "</div>" +
        '<div class="rinci">' + e.baris + " baris &middot; " + aman(e.nama_file) +
        (e.dropdown_utuh ? "" :
          ' &middot; <span style="color:var(--merah)">dropdown tidak utuh (' +
          e.dropdown_hasil + "/" + e.dropdown_asli + ")</span>") +
        "</div></div>" +
        '<a class="unduh" href="' + API + "/api/unduh/" +
        encodeURIComponent(d.sesi) + "/" + encodeURIComponent(e.id) +
        '">&#8595; Unduh Excel</a></div>').join("")
    : '<div class="kabar kabar-kuning">Tidak ada Excel yang dihasilkan.</div>';

  $("blok-tinjau").innerHTML = (d.ditinjau || []).length
    ? "<h3>Perlu ditinjau</h3>" + d.ditinjau.map((h) =>
        "<details><summary>&#9888; " + aman(h.nama) + " — " + aman(h.perusahaan) +
        " (keyakinan " + h.keyakinan + ')</summary><div class="isi"><ul>' +
        h.peringatan.map((w) => "<li>" + aman(w) + "</li>").join("") +
        "</ul></div></details>").join("")
    : "";

  $("blok-lewat").innerHTML = (d.dilewati || []).length
    ? "<h3>Dilewati</h3>" + d.dilewati.map((h) =>
        '<div class="kabar kabar-kuning">' + aman(h.nama) + " — " +
        aman(h.alasan) + "</div>").join("")
    : "";

  $("hasil").classList.remove("tersembunyi");
  $("hasil").scrollIntoView({ behavior: "smooth", block: "start" });
}

// -------------------------------------------------------------------- mulai
cekBackend();
setInterval(cekBackend, 30000);
perbaruiTombol();
