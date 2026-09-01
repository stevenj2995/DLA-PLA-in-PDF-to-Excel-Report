# DLA to Excel

Membaca berkas DLA satu perusahaan, lalu menyusunnya jadi satu Excel: parameter
di dalam dokumen itu sendiri yang jadi kolom, dan tiap PDF jadi satu baris.

Tidak ada template berkolom tetap dan tidak ada penebakan. Nilai diambil mentah
persis seperti tercetak di surat, jadi tidak ada tanggal atau angka yang bisa
salah ditafsirkan.

## Menjalankan

```
pip install -r requirements.txt
python run.py
```

`run.py` menyalakan backend di port 8000, lalu membuka terowongan Cloudflare
supaya halaman Vercel bisa menghubunginya, dan menulis alamat barunya ke
`Frontend/config.js`. Alamat itu berubah tiap kali dijalankan, jadi Vercel perlu
di-deploy ulang agar halaman publik menunjuk ke alamat yang baru.

Kalau backend dibuka ke internet, pasang kode akses lebih dulu:

```
set ACCESS_CODE=kode-anda
```

## Isi folder

```
run.py                     menyalakan backend dan terowongan
Backend/server.py          menerima unggahan, mengatur sesi, menghapus jejak
Backend/pipeline.py        alur dari PDF sampai Excel
Backend/profiles.py        aturan per perusahaan: kolom apa, diambil dari mana
Backend/extract/           membaca PDF jadi baris, lalu jadi pasangan label-nilai
Backend/build/excel.py     menulis sheet hasil
Frontend/                  halaman yang dilihat pengunjung, di-deploy ke Vercel
PDF Files/                 contoh DLA, tidak ikut masuk git
```

## Perusahaan yang didukung

Baru **JRP**. Askrindo dan KMDastur sudah ditulis sebagai draf di
`Backend/profiles.py` tetapi sengaja belum diaktifkan sampai daftar kolomnya
ditinjau — profil setengah jadi yang menulis kolom salah lebih berbahaya
daripada berkas yang ditolak.

Untuk JRP: halaman `DEBIT NOTE` diabaikan, hanya halaman DLA yang dibaca. Dari
blok nominal hanya nilai nett yang diambil. Mata uang dipisah jadi kolom
tersendiri di sebelah kiri tiap kolom nominal.

## Privasi

PDF yang diunggah dihapus dari server begitu selesai dibaca. Excel hasil
tersimpan sementara maksimal 15 menit, dan pengunjung bisa menghapusnya sendiri
lebih cepat lewat tombol di halaman hasil.
