# Hal yang belum diputuskan

Kode ini dibangun sebelum semua pertanyaan terjawab. Tiap poin di bawah
menunjuk **baris config yang harus diubah** begitu jawabannya ada — semuanya
satu baris, tidak perlu bongkar kode.

---

## 1. Tanggal kaki surat masuk kolom mana — PENGHAMBAT

PDF punya kaki surat seperti `Jakarta, 22 Agustus 2026`. Belum jelas tanggal
itu isi kolom mana.

Masalahnya: kolom **C** `Time of Loss` dan **T** `Notification Time` berlabel
`(HH:MM)` — minta jam, bukan tanggal. Menaruh tanggal di situ kemungkinan
ditolak sistem. Dugaan yang lebih masuk akal adalah kolom **S**
`Notification Date (YYYY-MM-DD)`, karena tanggal surat = tanggal pelaporan.

**Asumsi yang dipakai sekarang:** kolom S, format `2026-08-22`.

```python
# src/config.py
KOLOM_TANGGAL_SURAT = "S"        # "S" | "C" | "T" | None
FORMAT_TANGGAL_SURAT = "iso"     # "iso" -> 2026-08-22 | "asli" -> 22 Agustus 2026
```

---

## 2. Pencocokan nilai ke daftar tertutup

11 kolom terikat dropdown dengan daftar nilai yang sah (`CauseOfLoss` 149 item,
`InsuranceCoverage` 374 item, dst).

**Fakta yang perlu diketahui:** dropdown hanya menghalangi orang yang mengetik
manual. Nilai yang **ditulis program tetap diterima Excel diam-diam**, walau
tidak ada dalam daftar. Jadi kalau PDF menulis `Tabrakan` dan daftar sahnya
`Collision/Contact`, filenya tetap jadi — dan baru ketahuan salah saat upload.

**Kondisi sekarang:** nilai ditulis apa adanya dari PDF, belum dicocokkan ke
daftar. Lapisan ini belum dibuat karena menunggu penjelasan.

Kalau nanti diperlukan, sheet lookup-nya sudah tersedia di file standar dan
tinggal dibaca — tidak perlu bikin daftar baru.

---

## 3. Share AAB (kolom BT)

Nilainya mengikuti nomor polis, bukan dari isi PDF:

| Policy No. | Share |
|---|---|
| 092500072623, 092300058448, 09240006885x | 3,50% |
| 092500072727, 092400067129, 092600080783 | 6,00% |
| 042412488601 | 25,00% |

**Kondisi sekarang:** BT dikosongkan, dan tidak diisi `N/A` (sengaja, karena
ini penundaan — bukan ketiadaan data).

**Akibatnya:** kolom AM mencetak `AAB Share = 0`, dan kolom AR tidak ditulis
sama sekali karena persentasenya tidak diketahui.

Begitu tabelnya ada, isi di sini dan AR ikut hidup sendiri:

```python
# src/config.py
SHARE_PER_POLIS = {"092500072623": 0.035, "092500072727": 0.06}
```

---

## 4. Kolom Monitoring (BN–BS)

Enam kolom: Status, Claim No., SCS No., SCS Type, Current Stage, Error Message.
Terlihat diisi setelah upload, bukan dari PDF. Di file standar isinya juga
campur aduk — BN `Status` berisi nomor seri mesin, BO ada yang berisi teks
`regist manual`.

**Kondisi sekarang:** dikosongkan. Diatur di `KOLOM_MONITORING`.

---

## 5. 25 kolom yang selalu kosong

Kosong di seluruh 107 baris contoh. Beberapa ditandai `Mandatory` tapi tetap
kosong — P `Contact Person Name` dan R `Contact Person Email Address` kosong
karena O `Same as Reported` = `Y`. Jadi penanda Mandatory bersifat bersyarat.

**Kondisi sekarang:** tetap ditulis sebagai kolom kosong, sesuai keputusan
"ikuti saja semua yang ada di sheet MosyClaimTask".

---

## 6. Kode pos

Batch pertama di file standar seluruhnya `99999` (isian asal), batch lain pakai
kode asli.

**Kondisi sekarang:** pakai kode pos asli yang terbaca dari PDF.

---

## 7. 12 kolom konstan

`CPM - Heavy Equipment - CPM`, `MGQ`, `CASC - Casco`, `Reinstate`, `IDR` —
semuanya khas alat berat. Kalau masuk PDF dari lini bisnis lain, nilai ini
salah semua.

Ubah di `KOLOM_KONSTAN` (src/config.py). Isi `None` untuk mengosongkan.

---

## 8. Identitas perusahaan — SELESAI

Dalam satu PDF biasanya ada tiga nama perusahaan:

- **Penerbit** — adjuster/broker pembuat laporan, ada di kop surat atau blok tanda tangan
- **Tertanggung** — pemilik polis yang mengalami kerugian (contoh: Pelindo)
- **Tujuan** — PT Asuransi Astra Buana, selalu dicoret

**Diputuskan 26 Agustus 2026: selalu tertanggung.** Yang pada akhirnya harus
diambil adalah data pemilik polis, bukan pembuat laporannya. Pilihan
`IDENTITAS_PERUSAHAAN` dan radio button di panel kiri sudah dihapus — tidak
ada lagi yang perlu dipilih.

Ini menentukan dua hal: profil memory disimpan atas nama siapa, dan folder
output dipecah berdasarkan apa.

### Cara kerjanya sekarang: baca labelnya, jangan menebak

Kesebelas DLA yang ada semuanya menulis tertanggungnya secara eksplisit. Jadi
nama tidak lagi ditebak lewat skor — kalau dokumen menulis
`Name of Insured : X`, maka **X adalah tertanggungnya**, titik.

Label dicocokkan **utuh** dengan tulisan di kiri titik dua, lewat daftar
`LABEL_NAMA_TERTANGGUNG` di `src/config.py`:

| Diterima | Ditolak |
|---|---|
| `Insured`, `Insured Name`, `THE INSURED` | `REINSURED`, `Name of Reinsured` |
| `Name of Insured`, `NAME OF INSURED` | `TOTAL SUM INSURED`, `INTEREST INSURED` |
| `Tertanggung`, `Nama Tertanggung` | `Insured Interest`, `Insured Period` |

Harus utuh, bukan potongan kata: enam bentuk di kolom kanan sama-sama memuat
`insured` tapi bukan nama tertanggung. `Insured Interest` dan `Insured Period`
bahkan diawali `Insured`.

Tiga hal yang ikut ditambal:

1. **Deteksi sekarang membaca baris hasil susun-posisi**, bukan teks urutan
   mentah. Sebelumnya label dan nilainya terpisah jauh di urutan baca — di
   DLA PWS, `Insured :` sama sekali tidak ada di dekat nama tertanggungnya.
2. **Nama tanpa awalan PT ikut terbaca.** DLA IBURE menulis
   `NAME OF INSURED : BUKIT MAKMUR MANDIRI UTAMA` — tanpa PT, jadi dulu tidak
   pernah dianggap kandidat dan PDF-nya jatuh ke `_TIDAK_TERDETEKSI`.
3. **Rantai `and/or` dan `QQ` diambil yang pertama.** DLA PWS menyebut 15
   perusahaan sekaligus; yang dipakai `PT. Bara Tabang` sebagai tertanggung
   utama. Ubah `RE_PIHAK_LAIN` di `src/teks.py` kalau seharusnya lain.

Bonus skor "muncul di kop surat" dihapus, dan jalur skor lama tetap ada
sebagai **cadangan** — dipakai hanya kalau tidak ada satu pun label
tertanggung, dan hasilnya selalu diberi peringatan.

**Kolom H (Reported Name) diisi dari hasil deteksi ini**, tidak lagi dari
pencocok parameter. Sebelumnya 7 dari 10 berkas berisi `Asuransi Astra Buana`
— pihak tujuan yang justru selalu dicoret di tempat lain.

**Diuji atas 11 DLA asli: 11/11 tepat**, semuanya lewat label eksplisit,
`_TIDAK_TERDETEKSI` kosong.

---

## 9. Astra Buana selalu jadi penerima?

Nama `PT Asuransi Astra Buana` selalu dibuang saat menentukan perusahaan,
karena dia pihak tujuan. Kalau ternyata ada PDF yang **diterbitkan oleh**
Astra Buana sendiri, PDF itu akan jatuh ke `_TIDAK_TERDETEKSI`.

Diatur di `PERUSAHAAN_TUJUAN`.

---

## 10. Satu PDF = satu baris

Dipakai sebagai asumsi, karena `Claim External Ref No.` unik di 106 dari 106
baris contoh. Kalau ternyata satu PDF bisa berisi tabel banyak klaim,
`_susun_baris()` di `src/pipeline.py` perlu mengembalikan beberapa baris.

---

## 11. OCR — SELESAI

Tesseract v5.4.0 terpasang di `C:\Program Files\Tesseract-OCR`, dengan paket
bahasa `eng` + `ind`. PDF hasil scan sudah bisa dibaca.

---

## 12. Jalur utama pencocokan makna — SELESAI

`sentence-transformers` terpasang, model `paraphrase-multilingual-MiniLM-L12-v2`
sudah terunduh dan tersimpan di cache (jalan offline seterusnya).

Catatan pemasangan: ada instalasi TensorFlow rusak di laptop ini yang membuat
`transformers` gagal saat impor. Ditambal di `src/matcher.py` dengan
`USE_TF=0` supaya hanya memakai torch.

Istilah tak terdaftar sekarang tertangkap: "Taksiran Nilai Ganti" -> MD Gross
Amount (0.80), "Nomor Kontrak Pertanggungan" -> Policy No. (0.80). Yang skornya
di bawah 0.85 tetap ditandai "perlu ditinjau".

---

## 13. Ketepatan angka uang — belum ada penjaganya

Kolom **AQ** `MD Gross Amount` berisi angka seperti `1.024.770.200`. Kalau OCR
salah baca satu digit, yang masuk ke sistem klaim adalah angka salah — **tanpa
tanda peringatan apa pun**, karena angka salah tetap terlihat wajar.

Untuk PDF digital risikonya kecil. Untuk PDF hasil scan, nyata.

Belum ada mekanisme penjaga. Saran: satu langkah manusia melihat kolom nilai
uang sebelum Excel diupload, minimal untuk baris yang ditandai perlu ditinjau.

---

## 14. File hasil belum diuji di Microsoft Excel

Sudah diverifikasi lewat Python: 13 sheet utuh, 11/11 dropdown selamat, format
teks tanggal dan rumus AM tetap. Tapi belum pernah dibuka di Excel sungguhan.

**Tolong buka file pertama dan klik sel `Cause of Loss` — pastikan dropdown-nya
benar-benar muncul.**
