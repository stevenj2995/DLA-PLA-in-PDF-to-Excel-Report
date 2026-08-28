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
