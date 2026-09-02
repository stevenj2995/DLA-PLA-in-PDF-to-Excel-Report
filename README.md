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

Lalu buka **http://localhost:8000**. Halaman dan pemrosesan ada di alamat yang
sama, jadi tidak ada yang perlu disetel dan tidak ada urusan CORS.

Semuanya berjalan di laptop ini saja. Server mendengarkan di `127.0.0.1`, bukan
`0.0.0.0`, jadi komputer lain di jaringan kantor pun tidak bisa menghubunginya.
Tidak ada terowongan, tidak ada backend di internet, dan dokumen klaim tidak
pernah keluar dari mesin ini.

## Isi folder

```
run.py                     menyalakan backend di localhost
Backend/server.py          menerima unggahan, mengatur sesi, menghapus jejak
Backend/pipeline.py        alur dari PDF sampai Excel
Backend/profiles.py        aturan per perusahaan: kolom apa, diambil dari mana
Backend/extract/           membaca PDF jadi baris, lalu jadi pasangan label-nilai
Backend/build/excel.py     menulis sheet hasil
Frontend/                  halaman yang disajikan backend di localhost
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

## PDF hasil pindaian

Halaman yang tidak punya lapisan teks dibaca dengan Tesseract (`ind+eng`) pada
300 dpi. Barisnya dibentuk dari posisi kata, sama seperti jalur PDF digital,
supaya hasilnya sebangun.

Diuji dengan menjadikan DLA JRP sebagai gambar lalu membacanya ulang: 23 dari 24
kolom sama persis dengan hasil PDF aslinya. Yang berbeda satu, `Jl.` terbaca
`JI.` -- batas OCR yang tidak bisa dihilangkan. Karena itu setiap berkas yang
dibaca lewat OCR ditandai di halaman hasil supaya dicocokkan manual.

## Privasi

Semua pemrosesan terjadi di laptop ini. Tidak ada layanan pihak ketiga yang
menyentuh isi dokumen.

PDF yang diunggah dihapus begitu selesai dibaca. Excel hasil tersimpan sementara
di folder temporary maksimal 15 menit, dan bisa dihapus lebih cepat lewat tombol
di halaman hasil.

Repo ini publik di GitHub, tetapi `.gitignore` menahan `*.pdf`, `*.xlsx`,
`PDF Files/`, dan `Output/`. Riwayat git sudah diperiksa: tidak pernah ada satu
pun dokumen klaim yang ikut masuk.

`vercel.json` dan `.vercelignore` sengaja ditinggalkan meski deployment tidak
dipakai. Keduanya membatasi Vercel hanya menyajikan `Frontend/`; kalau dihapus
sementara integrasi GitHub masih tersambung, Vercel justru akan menerbitkan
seluruh repo termasuk kode Python. Untuk benar-benar melepasnya, hapus
project-nya dari dasbor Vercel.
