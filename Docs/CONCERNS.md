# Yang masih perlu dikerjakan

Catatan ini isinya satu hal saja: apa yang masih perlu Anda lakukan supaya
sistem ini berjalan dengan baik. Ditulis biasa, tidak perlu dibaca berurutan.

Semua yang disebut di bawah cukup diubah satu baris di `Backend/settings.py`,
kecuali kalau disebutkan lain.


## Yang perlu Anda lakukan sendiri

**Buka satu file hasil di Microsoft Excel, lalu klik sel Cause of Loss.**
Pastikan dropdown-nya benar-benar muncul. Ini satu-satunya hal yang belum
pernah diuji sama sekali. Semua pengecekan sejauh ini dilakukan lewat Python:
13 sheet utuh, 11 dari 11 dropdown selamat, format tanggal dan rumus AM tetap.
Tapi Python bukan Excel, dan yang menentukan adalah Excel.

**Periksa kolom nilai uang sebelum Excel diupload.** Kolom AQ (MD Gross Amount)
berisi angka seperti 1.024.770.200. Kalau OCR salah membaca satu digit, yang
masuk ke sistem klaim adalah angka salah, tanpa peringatan apa pun, karena
angka salah tetap terlihat wajar. Untuk PDF digital risikonya kecil; untuk PDF
hasil pindaian, nyata. Belum ada mekanisme penjaga untuk ini, jadi minimal
lihat sendiri baris-baris yang ditandai "perlu ditinjau".

**Pasang kode akses kalau backend dibuka ke internet.** Tanpa itu, siapa pun
yang punya tautannya bisa mengunggah. Caranya `set ACCESS_CODE=kode-anda`
sebelum menjalankan `run.py`. Ini penting bukan cuma soal PDF yang masuk, tapi
karena setiap Excel hasil membawa 12 sheet referensi internal Astra
(CatastropheEvent, InsuranceCoverage, dan lainnya) yang tidak bisa dibuang
tanpa merusak dropdown. Memberi hasil ke orang luar berarti ikut memberikan
struktur referensi itu.

**Isi folder Memory kalau ingin deteksi makin pintar.** Sekarang folder itu
kosong, dan karena satu-satunya jalur masuk adalah web (yang selalu bekerja di
folder sementara), apa pun yang dipelajari sistem ikut terhapus setiap selesai.
Artinya tiap permintaan menebak dari nol dan tidak akan membaik sendiri. Kalau
ini mengganggu, profil per perusahaan bisa ditulis manual sebagai file JSON di
folder Memory.


## Yang menunggu jawaban dari kantor

**Tanggal kaki surat masuk kolom mana.** Ini yang paling menghambat. PDF punya
kaki surat seperti "Jakarta, 22 Agustus 2026", dan belum jelas tanggal itu
mengisi kolom apa. Kolom C (Time of Loss) dan T (Notification Time) berlabel
HH:MM, artinya minta jam bukan tanggal, jadi menaruh tanggal di situ
kemungkinan besar ditolak sistem. Dugaan yang lebih masuk akal adalah kolom S
(Notification Date), karena tanggal surat sama dengan tanggal pelaporan. Itulah
asumsi yang dipakai sekarang: `LETTER_DATE_COLUMN = "S"` dengan format ISO.
Begitu ada jawabannya, ganti satu baris itu.

**Tabel share AAB.** Nilai kolom BT mengikuti nomor polis, bukan isi PDF.
Sekarang BT sengaja dikosongkan, dan sengaja tidak diisi "N/A" karena ini
penundaan, bukan ketiadaan data. Akibatnya kolom AM mencetak "AAB Share = 0"
dan kolom AR tidak ditulis sama sekali. Begitu tabelnya ada, isi
`SHARE_BY_POLICY` seperti `{"092500072623": 0.035}` dan kolom AR hidup sendiri.
Dari catatan sebelumnya, polis 0925000726xx sekitar 3,5%, 0925000727xx sekitar
6%, dan 042412488601 sekitar 25% — tapi angka itu perlu dikonfirmasi.

**Apakah nilai perlu dicocokkan ke daftar dropdown.** Sebelas kolom terikat
daftar nilai yang sah, misalnya CauseOfLoss punya 149 pilihan. Yang perlu
diketahui: dropdown hanya menghalangi orang yang mengetik manual. Nilai yang
ditulis program tetap diterima Excel diam-diam walau tidak ada dalam daftar.
Jadi kalau PDF menulis "Tabrakan" sedangkan daftar sahnya "Collision/Contact",
filenya tetap jadi dan baru ketahuan salah saat diupload. Sekarang nilai
ditulis apa adanya. Kalau nanti perlu dicocokkan, sheet lookup-nya sudah ada di
file template dan tinggal dibaca.

**Apakah satu PDF selalu jadi satu baris.** Ini dipakai sebagai asumsi karena
Claim External Ref No. unik di 106 dari 106 baris contoh. Kalau ternyata satu
PDF bisa berisi tabel banyak klaim, fungsi `_build_row` di `Backend/pipeline.py`
perlu diubah supaya mengembalikan beberapa baris.


## Yang sudah diputuskan, tinggal diketahui

**Nama perusahaan selalu diambil dari tertanggung.** Dalam satu PDF biasanya
ada tiga nama: penerbit laporan (adjuster atau broker), tertanggung (pemilik
polis yang mengalami kerugian), dan pihak tujuan (PT Asuransi Astra Buana).
Yang diambil selalu tertanggung. Ini menentukan dua hal sekaligus: profil
memory disimpan atas nama siapa, dan folder hasil dipecah berdasarkan apa.

Namanya tidak ditebak lewat skor, melainkan dibaca dari labelnya. Kalau dokumen
menulis "Name of Insured : X", maka X adalah tertanggungnya, titik. Labelnya
harus cocok utuh dengan tulisan di kiri titik dua, lewat daftar
`INSURED_NAME_LABELS`. Harus utuh dan bukan potongan kata, karena "Reinsured",
"Total Sum Insured", "Insured Interest", dan "Insured Period" semuanya memuat
kata insured tapi bukan nama tertanggung. Kalau dicocokkan sebagai potongan,
perusahaan yang menyerahkan risiko akan tertukar dengan pemilik polis. Ini
alasan aturan tersebut ada; jangan disederhanakan jadi pencarian substring.

Jalur skor yang lama masih ada sebagai cadangan, dipakai hanya kalau tidak ada
satu pun label tertanggung, dan hasilnya selalu diberi peringatan. Diuji atas
11 DLA asli dan tepat 11 dari 11, semuanya lewat label eksplisit.

Kalau suatu saat ada PDF yang justru diterbitkan oleh Astra Buana sendiri, PDF
itu akan jatuh ke folder `_TIDAK_TERDETEKSI`, karena nama Astra Buana selalu
dibuang saat menentukan perusahaan. Diatur di `OWN_COMPANY_NAMES`.

Rantai "and/or" dan "QQ" diambil yang pertama saja. Satu DLA menyebut 15
perusahaan sekaligus dan yang dipakai adalah yang disebut duluan sebagai
tertanggung utama. Diatur oleh `RE_OTHER_PARTIES` di `Backend/extract/text.py`.

**Dua belas kolom diisi nilai tetap.** CPM - Heavy Equipment - CPM, MGQ,
CASC - Casco, Reinstate, IDR, dan seterusnya. Semuanya khas alat berat, jadi
kalau nanti masuk PDF dari lini bisnis lain, nilai-nilai ini salah semua.
Diubah di `CONSTANT_COLUMNS`, isi `None` untuk mengosongkan.

**Enam kolom monitoring dikosongkan.** BN sampai BS (Status, Claim No., SCS No.,
SCS Type, Current Stage, Error Message) terlihat diisi setelah upload, bukan
dari PDF. Di file template isinya juga campur aduk. Diatur di
`MONITORING_COLUMNS`.

**Dua puluh lima kolom lain memang selalu kosong.** Kosong di seluruh 107 baris
contoh. Beberapa ditandai Mandatory tapi tetap kosong, misalnya Contact Person
Name dan Contact Person Email Address, karena kolom O (Same as Reported) diisi
Y. Jadi penanda Mandatory di template itu bersifat bersyarat.

**Kode pos memakai angka asli dari PDF.** Batch pertama di file template
seluruhnya berisi 99999 sebagai isian asal, batch lain memakai kode asli. Yang
dipakai sistem adalah yang asli.

**OCR sudah siap.** Tesseract 5.4.0 terpasang dengan paket bahasa Inggris dan
Indonesia, jadi PDF hasil pindaian bisa dibaca.

**Pencocokan makna sudah pakai jalur utama.** Model
paraphrase-multilingual-MiniLM-L12-v2 sudah terunduh dan tersimpan, jadi jalan
offline seterusnya. Istilah yang tidak terdaftar di kamus sekarang tertangkap,
misalnya "Taksiran Nilai Ganti" ke MD Gross Amount. Yang skornya di bawah 0,85
tetap ditandai perlu ditinjau. Catatan pemasangan: ada instalasi TensorFlow
rusak di laptop ini yang membuat transformers gagal saat impor, ditambal di
`Backend/mapping/matcher.py` dengan USE_TF=0 supaya hanya memakai torch.
