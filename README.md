# DLA to Excel Report

Mengubah laporan DLA berbentuk PDF menjadi Excel sesuai template MosyClaimTask,
otomatis. Pengunjung membuka halaman web, mengunggah PDF, dan mengunduh Excel
yang sudah terisi.

Halaman webnya di-host di Vercel, tapi semua pemrosesan terjadi di laptop ini.
Vercel hanya menyajikan halaman statis; PDF dikirim langsung dari browser
pengunjung ke laptop lewat terowongan, tidak pernah melewati Vercel.
Konsekuensinya: website hanya hidup selama laptop menyala dan `run.py` berjalan.
Kalau ditutup, pengunjung melihat "Backend sedang tidak aktif". Itu bukan bug.


## Menjalankan

```
python run.py
```

Perintah itu menyalakan server, membuka terowongan, mencetak alamat publiknya,
dan menulis alamat itu ke `Frontend/config.js`. Karena alamat terowongan
berganti setiap kali dinyalakan, halaman Vercel perlu diberi tahu:

```
git add Frontend/config.js
git commit -m "alamat backend baru"
git push
```

Untuk mencoba tanpa deploy ulang, buka halamannya dengan tambahan
`?api=<alamat>` di URL. Alamat itu diingat browser.

Untuk mencoba sepenuhnya di laptop sendiri, jalankan `python run.py` di satu
jendela, lalu di jendela lain `cd Frontend` dan `python -m http.server 3000`,
kemudian buka `http://localhost:3000/?api=http://localhost:8000`.


## Yang perlu dipasang

```
pip install -r requirements.txt
winget install UB-Mannheim.TesseractOCR
winget install --id Cloudflare.cloudflared
```

Tesseract dipakai untuk PDF hasil pindaian; tanpa itu PDF pindaian dilewati,
bukan dibaca separuh. Cloudflared dipakai untuk membuka terowongan; tanpa itu
backend hanya bisa dihubungi dari laptop sendiri.

Kalau backend dibuka ke internet, pasang kode akses lebih dulu:
`set ACCESS_CODE=kode-anda`.


## Isi folder

```
run.py              satu-satunya perintah untuk menyalakan semuanya
Backend/            semua kode pemroses
Frontend/           halaman yang dilihat pengunjung, di-deploy ke Vercel
Template/           file Excel acuan, jangan dihapus
Memory/             profil per perusahaan (JSON, boleh diedit manual)
Output/             peninggalan jalur lama, sudah tidak ditulis siapa pun
```

Isi Backend, mengikuti urutan kerjanya:

```
Backend/server.py               menerima unggahan, mengatur sesi, menghapus jejak
Backend/pipeline.py             menjalankan seluruh alur dari PDF sampai Excel
Backend/settings.py             semua pengaturan dan asumsi
Backend/extract/pdf_reader.py   membuka PDF, menyusun ulang baris, OCR bila perlu
Backend/extract/text.py         mengupas tanggal/jam/uang, mendeteksi perusahaan
Backend/mapping/matcher.py      mencocokkan parameter PDF ke kolom Excel
Backend/mapping/memory.py       profil per perusahaan, memindahkan PDF
Backend/build/excel.py          menulis Excel tanpa merusak dropdown
```


## Cara kerjanya

Setiap PDF dibaca dengan menyusun ulang barisnya dari posisi kata, bukan dari
urutan baca mentah, supaya label dan nilainya tetap bersebelahan. Nama
perusahaan diambil dari label tertanggung ("Insured Name", "Name of Insured",
"Tertanggung"), bukan ditebak. Tiap pasangan parameter-nilai dicarikan kolomnya
secara berjenjang: profil perusahaan yang sudah ada, lalu kecocokan persis,
lalu kamus sinonim, lalu analisis makna. Yang cocok lewat analisis makna dengan
skor rendah ditandai "perlu ditinjau" dan skornya dicetak.

Hasilnya satu Excel per perusahaan per hari, ditulis di atas salinan file
template. Openpyxl membuang validasi data lintas-sheet saat menyimpan, jadi
jumlah dropdown dihitung sebelum dan sesudah menulis, dan kalau berkurang,
bloknya ditambal kembali di tingkat XML. Angka dropdown ini ikut ditampilkan di
halaman hasil supaya kalau suatu saat rusak, langsung kelihatan.

Skor yang muncul di laporan bukan akurasi. Skor 0,80 berarti dua istilah dinilai
mirip artinya, bukan 80 persen kemungkinan benar.


## Soal data pengunjung

Setiap permintaan dikerjakan di folder sementara yang terisolasi. Profil
perusahaan disalin masuk supaya deteksi tetap akurat, tapi apa pun yang
dipelajari dari PDF pengunjung ikut terhapus bersama foldernya. Memory asli di
laptop tidak pernah tersentuh.

PDF yang diunggah dihapus begitu Excel-nya jadi, dalam hitungan detik. Excel
hasil dihapus setelah 15 menit, atau saat pengunjung menekan tombol "hapus data
saya sekarang", atau saat ia menutup tab. Folder yang tertinggal karena server
mati mendadak disapu saat server berikutnya menyala.

Batas yang dipasang: maksimal 10 PDF sekali proses, 15 MB per berkas, 50 MB
total, hanya .pdf, dan satu proses pada satu waktu.

Satu hal yang tidak bisa dijamin: terowongan Cloudflare mengakhiri TLS di server
Cloudflare, jadi secara teknis isi PDF terbaca di sana sebelum sampai ke laptop.
Kalau itu tidak dapat diterima, jangan pakai terowongan publik — pakai jaringan
kantor, atau jalankan semuanya lokal seperti di bagian Menjalankan.


## Sebelum dipakai serius

Empat hal masih menunggu jawaban kantor, dan sementara ini dipakai asumsi:
tanggal kaki surat ditulis ke kolom S (`LETTER_DATE_COLUMN`), tabel share AAB
belum ada (`SHARE_BY_POLICY` kosong, jadi BT ikut isi dokumen), nilai yang tidak
ada di daftar dropdown tetap ditulis tapi diberi peringatan, dan satu PDF
dianggap selalu jadi satu baris.

Satu hal harus Anda lakukan sendiri: buka satu file hasil di Microsoft Excel dan
pastikan dropdown Cause of Loss benar-benar muncul. Semua pengujian sejauh ini
lewat Python, dan yang menentukan adalah Excel.
