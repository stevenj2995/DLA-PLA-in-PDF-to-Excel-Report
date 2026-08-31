# Otomasi Pembacaan PDF ke Excel

Membaca PDF laporan klaim dari berbagai perusahaan, lalu menghasilkan file
Excel yang mengikuti standar `MosyClaimTask` — satu file per perusahaan.

Berjalan **sepenuhnya offline**. Tidak ada data yang dikirim ke mana pun.

---

## Cara kerja

```
PDF di INPUT/  →  baca isi  →  deteksi perusahaan  →  sortir ke folder
                                      ↓
                          (sekalian ambil profil memory perusahaan itu)
                                      ↓
                          susun baris  →  Excel di folder perusahaan
```

**Memory per perusahaan.** Waktu perusahaan baru pertama kali muncul, sistem
mencocokkan nama parameter di PDF dengan kolom Excel standar, lalu menyimpan
hasilnya. PDF berikutnya dari perusahaan yang sama langsung memakai peta itu
tanpa mencocokkan ulang.

Urutan pencocokan:

| Kondisi | Tindakan |
|---|---|
| Nama parameter sama persis | Langsung dipakai, tetap disimpan ke memory |
| Beda tulisan tapi sama arti | Dicocokkan lewat kamus / analisis makna, lalu disimpan |
| Tidak ada yang cocok | Diisi `N/A: <alasan>` |

Contoh lintas bahasa: PDF menulis `Date of Loss`, standar menulis
`Tanggal Kejadian` — nol persen mirip secara tulisan, tapi tetap tersambung
lewat kamus padanan.

---

## Pemasangan

```bash
pip install -r requirements.txt
```

**OCR (untuk PDF hasil scan).** Pasang terpisah dari
<https://github.com/UB-Mannheim/tesseract/wiki>, sertakan paket bahasa `ind`
dan `eng`. Tanpa ini, PDF hasil scan tidak bisa dibaca.

**Model makna (opsional).** `pip install sentence-transformers` — perlu
internet sekali di awal, setelah itu offline selamanya. Tanpa ini program
tetap jalan lewat jalur cadangan (kamus + kemiripan kata), hanya lebih sering
meleset untuk istilah yang tidak terdaftar.

---

## Menjalankan

**Lewat tampilan web:**

```bash
streamlit run app.py
```

**Lewat terminal:**

```bash
python run.py --email nama@asuransiastra.com
python run.py --email nama@asuransiastra.com --folder "D:/laporan"
python run.py --batalkan          # kembalikan PDF yang telanjur dipindah
```

**Memeriksa tanpa memproses apa pun:**

```bash
python cek.py kolom                    # 72 kolom standar beserta perannya
python cek.py pdf "laporan.pdf"        # isi yang terbaca dari satu PDF
python cek.py cocok "Nilai Kerugian"   # uji satu nama parameter
python cek.py audit "laporan.pdf"      # cari data PDF yang tercecer
```

---

## Menguji ketepatan

Dua lapis, dan bedanya penting:

| | Menjawab | Butuh | Biaya |
|---|---|---|---|
| **Baca PDF** | Ada data yang tercecer? | tidak ada | detik per PDF |
| **PDF → Excel** | Nilainya benar? | Excel isian manual | jam, sekali di awal |

**Lapis 1 — `python cek.py audit`.** Tidak perlu kunci jawaban: PDF-nya sendiri
yang jadi acuan. Perintah ini menyandingkan tiap baris mentah PDF dengan
pasangan yang berhasil ditangkap, lalu menandainya:

```
ok   Policy Number : 15022325000001-000275      D
--   Interest Insured : Port & Terminal Op...   (ditolak)
!!   : Nett Amount IDR 2,644,476,650.00         TIDAK TERTANGKAP
```

Yang dibaca cuma baris `!!`. Kalau isinya terlihat seperti data klaim, berarti
ada yang tercecer. Kop surat, alamat, dan nomor izin wajar muncul di situ.

Jalankan setiap kali ada **penerbit baru** — format yang belum pernah dilihat
adalah tempat pembacaan jebol, bukan berkas ke-20 dari format yang sudah dikenal.

**Lapis 2 — kunci jawaban.** Isi Excel manual untuk 10–15 DLA dari penerbit
yang berbeda-beda, jalankan sistem atas PDF yang sama, lalu bandingkan sel per
sel. Hitung **per kolom**, bukan satu angka total — yang berguna adalah
mengetahui kolom mana yang sering meleset.

> Angka keyakinan di laporan **bukan** akurasi. Skor `0.80` berarti "model
> menilai dua istilah ini mirip artinya", bukan "80% kemungkinan benar".

---

## Struktur folder

```
STANDAR/           file Excel standar (acuan struktur, jangan dihapus)
INPUT/             taruh PDF di sini
OUTPUT/
  <Grup>/<Perusahaan>/PDF/                 PDF asli setelah disortir
  <Grup>/<Perusahaan>/<Perusahaan>_YYYYMMDD.xlsx
  _TIDAK_TERDETEKSI/                       PDF yang perusahaannya tidak dikenali
  _LAPORAN_*.txt                           ringkasan tiap proses
  _catatan_pemindahan.jsonl                catatan agar pemindahan bisa dibatalkan
MEMORY/            profil per perusahaan (JSON, boleh diedit manual)
src/               kode
```

---

## Isi kode

Tujuh modul, mengikuti urutan kerjanya:

| Berkas | Isinya |
|---|---|
| `src/config.py` | Semua pengaturan dan asumsi. Tidak ada logika di sini. |
| `src/pdf_reader.py` | **1.** Membuka PDF, menyusun ulang baris dari posisi kata, OCR kalau hasil scan |
| `src/teks.py` | **2.** Mengupas teks: tanggal, jam, uang, persen — dan nama perusahaan tertanggung |
| `src/matcher.py` | **3.** Mencocokkan nama parameter di PDF dengan kolom Excel standar |
| `src/memori.py` | **4.** Profil memory per perusahaan + memindahkan PDF ke folder tujuannya |
| `src/excel.py` | **5.** Membaca struktur file standar, lalu menulis hasil tanpa merusak dropdown |
| `src/pipeline.py` | Perekat: menjalankan langkah 1–5 secara berurutan |

Ditambah dua berkas tampilan — `src/tampilan.py` (potongan HTML) dan
`src/styles.css` (warna dan tata letak) — yang hanya dipakai oleh `app.py`.

Pintu masuknya tiga: `app.py` (web), `run.py` (terminal), `cek.py` (alat
pemeriksa, tidak ikut jalan saat proses normal).

PDF asli **dipindah**, bukan disalin. Semua pemindahan tercatat, jadi bisa
dikembalikan dengan `python run.py --batalkan` kalau ada yang nyasar.

---

## Tiga tingkat keyakinan

| Tingkat | Perlakuan |
|---|---|
| Yakin | Masuk folder perusahaannya, tanpa warning |
| Ragu | Tetap masuk folder tebakan terbaik, **diberi warning** |
| Tidak tahu | Masuk `_TIDAK_TERDETEKSI`, tidak dipaksa menebak |

---

## Kalau tebakan folder salah

Pindahkan foldernya manual, lalu perbaiki file profil di `MEMORY/`. Ubah
`grup` atau `folder` di file JSON-nya. Tanpa itu, proses berikutnya akan
membuat folder salah yang sama lagi.

---

## Catatan teknis

**Excel dibuat dengan menyalin file standar**, bukan dibangun dari nol. File
standar punya 11 dropdown lintas-sheet yang tersimpan sebagai `<extLst>`, dan
`openpyxl` menghapus semuanya begitu file disimpan ulang. Jadi setelah data
ditulis, blok itu dipasang kembali. Setiap file hasil diperiksa otomatis —
kalau jumlah dropdown tidak utuh, muncul peringatan.

**Tanggal ditulis sebagai teks**, bukan tipe tanggal Excel. Kalau ditulis
sebagai tanggal asli, Excel mengubah tampilannya dan format `YYYY-MM-DD` yang
diminta sistem tujuan bisa rusak.

---

## Yang belum diputuskan

Lihat [CONCERNS.md](CONCERNS.md) — 14 poin, masing-masing menunjuk baris config
yang perlu diubah begitu jawabannya ada.

Yang paling menghambat: **tanggal kaki surat masuk kolom S atau kolom C/T.**

---

## Website publik (Vercel + backend di laptop)

Selain `app.py` yang dipakai sendiri, ada versi web yang bisa dibagikan ke
orang lain lewat tautan. Bentuknya dua bagian:

```
Vercel (halaman, publik)              Laptop ini (pemroses)
┌──────────────────────┐   HTTPS     ┌────────────────────────┐
│ web/index.html       │ ──────────► │ server.py (FastAPI)    │
│ web/app.js           │ terowongan  │   └─ src/pipeline.py   │
│ web/styles.css       │ ◄────────── │ Standar/ + Memory/     │
└──────────────────────┘ JSON+.xlsx  └────────────────────────┘
```

**Kenapa dipisah begini.** Vercel hanya menjalankan halaman statis; ia tidak
bisa menjalankan Python berat ini — `torch` saja 454 MB sedangkan batas Vercel
250 MB, Tesseract OCR butuh program sistem yang tidak bisa dipasang di sana,
dan `Standar/` serta `Memory/` harus tetap di disk. Jadi halamannya di Vercel,
pemrosesannya tetap di laptop.

**Konsekuensi yang harus disadari:** website hanya hidup selama laptop menyala
dan `mulai.py` berjalan. Kalau ditutup, pengunjung melihat "Backend sedang
tidak aktif". Ini bukan bug.

### Menyalakan

```bash
python mulai.py
```

Skrip itu menyalakan `server.py`, membuka terowongan, mencetak alamat publik,
dan menulis alamat itu ke `web/config.js`. Sekali saja pasang terowongannya:

```bash
winget install --id Cloudflare.cloudflared
```

Setiap kali alamat terowongan berubah, halaman Vercel perlu tahu alamat baru:

```bash
git add web/config.js && git commit -m "alamat backend baru" && git push
```

Vercel otomatis deploy ulang. Untuk uji cepat tanpa deploy, buka halamannya
dengan `?api=<alamat>` — alamat itu diingat browser.

> Alamat `trycloudflare.com` berganti tiap kali dinyalakan. Kalau ingin alamat
> tetap, pakai ngrok dengan domain statis (gratis, 1 domain per akun) atau
> Cloudflare Tunnel bernama dengan domain sendiri.

### Uji coba di laptop sendiri

```bash
python server.py                       # jendela 1
cd web && python -m http.server 3000   # jendela 2
```

Lalu buka `http://localhost:3000/?api=http://localhost:8000`.

### Yang membedakan versi web dari `app.py`

Setiap permintaan dari web dikerjakan di **folder sementara yang terisolasi**
(`ruang_terisolasi()` di `server.py`). `Output/` dan `Memory/` asli tidak
pernah disentuh: profil perusahaan disalin masuk supaya deteksi tetap akurat,
tapi apa pun yang dipelajari dari PDF pengunjung ikut terhapus. Tanpa ini, PDF
orang asing akan menumpuk di `Output/` dan mencemari profil yang sudah dilatih.

Batas yang dipasang karena backend ini terbuka ke internet: maksimal 10 PDF
sekali proses, 15 MB per berkas, 50 MB total, hanya `.pdf`, satu proses pada
satu waktu, dan hasil dihapus otomatis setelah 30 menit. Yang boleh memanggil
backend dibatasi ke domain `*.vercel.app` dan localhost — atur lewat variabel
lingkungan `ASAL_DIIZINKAN` kalau pakai domain sendiri.

### Dokumen rahasia

`.gitignore` menahan `Input/`, `Output/`, `Memory/`, `Training and Testing
Data/`, `Standar/*.xlsx`, dan semua `*.pdf`. Jangan dilonggarkan — repo ini
pernah tidak sengaja memuat DLA asli bertanda tangan saat masih publik.

---

## Ke mana data unggahan sebenarnya pergi

Ini penting dijawab jujur, karena dokumen yang diproses milik klien.

```
Browser pengunjung
   │  PDF dikirim LANGSUNG ke alamat terowongan — TIDAK lewat Vercel.
   │  Vercel hanya mengirim halaman HTML/CSS/JS, tidak pernah melihat berkas.
   ▼
Cloudflare (terowongan)        ← TLS berakhir di sini, lihat "Yang tidak bisa dijamin"
   ▼
Laptop ini — %LOCALAPPDATA%\Temp\dla_xxxx\
   ├── MASUK/          PDF unggahan      → dihapus begitu Excel jadi
   ├── OUTPUT/*.xlsx   hasil             → dihapus setelah UMUR_SESI (15 menit)
   ├── OUTPUT/_LAPORAN_*.txt             → ikut terhapus bersama foldernya
   └── MEMORY/*.json   profil sementara  → ikut terhapus, tidak ditulis balik
```

`Output/` dan `Memory/` asli **tidak pernah tersentuh** — semuanya dialihkan ke
folder sementara oleh `ruang_terisolasi()`.

### Enam lapis penghapusan

Dua yang pertama dikendalikan pengunjung; empat sisanya jaring pengaman.

| Lapis | Kapan | Menangani |
|---|---|---|
| Langsung | Detik setelah Excel jadi | PDF unggahan (`_hapus_semua_pdf`) |
| **Tombol "saya sudah selesai"** | Saat pengunjung menekannya | Seluruh sesi, seketika (`/api/selesai`) |
| **Menutup halaman** | Tab ditutup / pindah halaman | Seluruh sesi, lewat `navigator.sendBeacon` |
| Penyapu latar | Tiap 1 menit | Sesi kedaluwarsa + folder yatim |
| `atexit` | Server dimatikan normal | Semua sesi yang masih hidup |
| Sapu saat menyala | Server dinyalakan | Sisa dari server yang mati mendadak |

Pengunjung melihat panel peringatan kuning bersama hasilnya: apa yang masih
tersimpan, apa yang akan dihapus, dan bahwa PDF-nya sendiri sudah hilang.
Menekan tombolnya memunculkan konfirmasi — dan kalau Excel-nya belum diunduh,
peringatannya berbeda dan lebih tegas, karena hasilnya akan ikut hilang.

`sendBeacon` dipakai, bukan `fetch`, karena permintaan `fetch` dibatalkan
browser begitu halamannya ditutup; beacon tetap terkirim. Terverifikasi jalan
saat pengunjung menutup halaman secara normal. Yang tidak tertangkap: browser
yang mati paksa (crash, baterai habis) — itu ditangani lapis keempat sampai
keenam.

Lapis keempat ada karena mati paksa (listrik putus, laptop ditutup) membuat
daftar sesi hilang bersama prosesnya — tanpa itu, PDF pengunjung tertinggal di
folder Temp selamanya. Sapu ini sengaja hanya menyentuh folder yang lebih tua
dari `UMUR_SESI`, supaya menjalankan server kedua tidak menghapus sesi yang
sedang aktif di server pertama.

### Membatasi siapa yang boleh memakai

Alamat `trycloudflare.com` bersifat publik: siapa pun yang punya tautannya bisa
mengunggah. Pasang kode akses supaya tautan yang bocor tidak cukup:

```bash
set KODE_AKSES=kode-rahasia-anda
python mulai.py
```

Halaman web otomatis menampilkan kotak kode kalau backend memintanya.

### Yang TIDAK bisa dijamin

Tiga hal yang harus disadari, bukan ditutupi:

1. **Cloudflare bisa melihat isi berkas.** Terowongan mengakhiri TLS di server
   Cloudflare, jadi secara teknis PDF terbaca di sana sebelum sampai ke laptop.
   Kalau ini tidak dapat diterima, jangan pakai terowongan publik — pakai
   jaringan kantor/VPN, atau jalankan `app.py` (Streamlit) secara lokal saja.

2. **Setiap Excel hasil membawa 12 sheet referensi internal Astra** —
   `CatastropheEvent` (register kejadian internal berikut tanggal dan lokasi),
   `InsuranceCoverage` (374 kode produk), `SectionCode`, `InsuranceInterest`,
   dan lainnya. Sheet itu **tidak bisa dibuang** karena dropdown di kolom-kolom
   `MosyClaimTask` menunjuk ke sana. Artinya: memberi hasil ke orang luar =
   memberikan struktur referensi internal Astra. Ini alasan terkuat untuk
   memakai `KODE_AKSES`.

3. **Berkas ada di folder Temp Windows** selama masa hidupnya, jadi bisa
   terbaca oleh proses lain yang berjalan sebagai pengguna yang sama, dan bisa
   ikut terjaring antivirus atau backup yang memindai folder itu.
