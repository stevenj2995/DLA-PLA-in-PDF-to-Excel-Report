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

Lalu buka **http://localhost:8000**. Halaman dan API disajikan dari alamat yang
sama, jadi tidak ada yang perlu disetel dan tidak ada urusan CORS.

Kalau `cloudflared` terpasang, `run.py` juga membuka terowongan dan mencetak satu
alamat https yang menyajikan halaman sekaligus API, supaya bisa dibuka dari
device lain. Alamat itu berubah setiap kali dijalankan.

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

## PDF hasil pindaian

Halaman yang tidak punya lapisan teks dibaca dengan Tesseract (`ind+eng`) pada
300 dpi. Barisnya dibentuk dari posisi kata, sama seperti jalur PDF digital,
supaya hasilnya sebangun.

Diuji dengan menjadikan DLA JRP sebagai gambar lalu membacanya ulang: 23 dari 24
kolom sama persis dengan hasil PDF aslinya. Yang berbeda satu, `Jl.` terbaca
`JI.` -- batas OCR yang tidak bisa dihilangkan. Karena itu setiap berkas yang
dibaca lewat OCR ditandai di halaman hasil supaya dicocokkan manual.

## Hosting backend

Vercel hanya menyajikan isi `Frontend/`. Kode Python tidak pernah ikut ke sana,
dan memang tidak bisa: OCR butuh Tesseract yang merupakan program native, batch
ratusan PDF makan waktu jauh melewati batas fungsi serverless, dan Excel hasil
perlu tetap ada sampai diunduh.

Backend punya `Dockerfile` sendiri berisi Python dan Tesseract lengkap dengan
paket bahasa `eng` dan `ind`. `render.yaml` menyiapkannya untuk Render, tapi
Dockerfile itu jalan di mana pun yang menerima container -- Railway, Fly.io,
atau VPS biasa.

Langkahnya:

1. Deploy repo ini ke Render sebagai **Docker** service. `render.yaml` sudah
   menunjuk `Dockerfile` dan memakai `/api/status` sebagai health check.
2. Pasang `ACCESS_CODE` lewat dasbor. Backend ini terbuka di internet, jadi
   tanpa kode akses siapa pun yang punya alamatnya bisa mengunggah.
3. Isi alamat hasil deploy ke `window.BACKEND_URL` di `Frontend/config.js`, lalu
   push. Vercel akan deploy ulang sendiri.

Setelah itu halaman Vercel jalan tanpa laptop siapa pun menyala. Alamat hasil
deploy juga menyajikan halamannya sendiri, jadi Vercel sebetulnya jadi opsional.

Yang perlu disadari sebelum melangkah: PDF klaim asli akan diunggah ke server
pihak ketiga dan diproses di sana, bukan lagi di laptop sendiri.

## Privasi

PDF yang diunggah dihapus dari server begitu selesai dibaca. Excel hasil
tersimpan sementara maksimal 15 menit, dan pengunjung bisa menghapusnya sendiri
lebih cepat lewat tombol di halaman hasil.
