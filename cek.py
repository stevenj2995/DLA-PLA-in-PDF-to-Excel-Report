# Alat pengecekan cepat, dipakai waktu memeriksa atau mendemokan sistem.
# Tidak dipakai saat program berjalan normal.
#
#   python cek.py kolom              lihat 72 kolom standar beserta perannya
#   python cek.py pdf [berkas.pdf]   lihat hasil baca satu PDF
#   python cek.py cocok "Date of Loss"   uji satu nama parameter
#   python cek.py audit [berkas/folder]  periksa ada data PDF yang tercecer
from __future__ import annotations

import re
import sys
from pathlib import Path

CONTOH = Path("Training and Testing Data")


def _daftar_pdf(berkas: list[str]) -> list[str]:
    if not berkas:
        return [str(p) for p in sorted(CONTOH.glob("*.pdf"))]
    hasil: list[str] = []
    for b in berkas:
        p = Path(b)
        if p.is_dir():
            hasil.extend(str(x) for x in sorted(p.rglob("*.pdf")))
        else:
            hasil.append(str(p))
    return hasil


def kolom() -> None:
    from src.excel import muat
    s = muat()
    print(f"{len(s)} kolom -> {s.ringkasan()}\n")
    for k in s:
        print(f"  {k.huruf:3} {k.peran:11} {str(k.flag or ''):9} {k.nama_lengkap}")


def pdf(berkas: list[str]) -> None:
    from src.pdf_reader import baca, cari_tesseract
    print(f"OCR: {cari_tesseract() or 'BELUM TERPASANG'}\n")
    daftar = _daftar_pdf(berkas)
    if not daftar:
        print(f"Tidak ada PDF. Sebutkan berkasnya, atau taruh di {CONTOH}/")
        return
    for arg in daftar:
        d = baca(arg)
        gambar = sum(h.jumlah_gambar for h in d.halaman)
        print(f"=== {Path(arg).name}")
        print(f"    halaman={len(d.halaman)} scan={d.hasil_scan} gagal={d.gagal}")
        print(f"    judul={d.metadata.get('title')} gambar={gambar}")
        for w in d.peringatan:
            print(f"    ! {w}")
        kv = d.pasangan_kunci_nilai()
        print(f"    pasangan kunci-nilai: {len(kv)}")
        for k, v in list(kv.items())[:8]:
            print(f"      {k} = {v}")


def cocok(param: list[str]) -> None:
    from src.excel import muat
    from src.matcher import Pencocok
    p = Pencocok(muat())
    print(f"Jalur: {p.jalur}\n")
    for teks in param or ["Date of Loss", "Taksiran Nilai Ganti", "Nomor Polis"]:
        c = p.cocokkan(teks)
        print(f"  {teks!r}")
        print(f"    -> {c.kolom or '(tidak cocok)'} {c.header or ''} "
              f"[{c.cara}, skor {c.skor:.2f}]")
        print(f"       {c.alasan}")


# Menguji KETEPATAN BACA, bukan kebenaran nilai. Tidak perlu kunci jawaban:
# PDF-nya sendiri yang jadi acuan. Pertanyaannya bukan "nilai ini benar?"
# melainkan "ada yang tercecer?" - dan itu bisa dilihat mata.
RE_ANGKA = re.compile(r"\d[\d.,]{3,}")


def audit(berkas: list[str]) -> None:
    from src.excel import muat
    from src.matcher import Pencocok
    from src.pdf_reader import baca

    daftar = _daftar_pdf(berkas)
    if not daftar:
        print(f"Tidak ada PDF. Sebutkan berkasnya, atau taruh di {CONTOH}/")
        return

    pc = Pencocok(muat())
    jumlah = {"ok": 0, "tolak": 0, "curiga": 0, "abai": 0}

    for arg in daftar:
        d = baca(arg)
        print()
        print("=" * 78)
        print(Path(arg).name)
        if d.gagal:
            print(f"  GAGAL DIBACA: {d.gagal}")
            continue
        if any(h.dari_ocr for h in d.halaman):
            print("  ! sebagian halaman hasil OCR - teksnya lebih rawan salah baca")
        print("=" * 78)

        kv = d.pasangan_kunci_nilai()
        kolom = {}
        for label in kv:
            c = pc.cocokkan(label)
            kolom[label] = c.kolom if c.diterima else None
        nilai_tertangkap = " || ".join(kv.values())

        ini = {"ok": 0, "tolak": 0, "curiga": 0, "abai": 0}
        print(f"{'':4} {'BARIS MENTAH DARI PDF':<58} KOLOM")
        print("-" * 78)
        for b in d.baris:
            label = [k for k in kv if b.startswith(k) or f"{k} :" in b or f"{k}:" in b]
            if label:
                dapat = [kolom[k] for k in label if kolom[k]]
                tanda, ket, kunci = (("ok", " ".join(dapat), "ok") if dapat
                                     else ("--", "(ditolak)", "tolak"))
            elif ":" in b or (RE_ANGKA.search(b)
                              and not any(b in v for v in kv.values())):
                tanda, ket, kunci = "!!", "TIDAK TERTANGKAP", "curiga"
            else:
                tanda, ket, kunci = "  ", "", "abai"
            ini[kunci] += 1
            jumlah[kunci] += 1
            print(f"{tanda:4} {b[:58]:<58} {ket}")

        print("-" * 78)
        print(f"  ok {ini['ok']:>3} jadi kolom     "
              f"-- {ini['tolak']:>3} ditolak     "
              f"!! {ini['curiga']:>3} PERLU DIPERIKSA     "
              f"{ini['abai']:>3} bukan data")

    if len(daftar) > 1:
        print()
        print("=" * 78)
        print(f"TOTAL {len(daftar)} berkas:  ok {jumlah['ok']}  "
              f"-- {jumlah['tolak']}  !! {jumlah['curiga']}  "
              f"bukan data {jumlah['abai']}")
    print()
    print("Baca hanya baris bertanda !! . Kalau isinya terlihat seperti data klaim,")
    print("berarti ada yang tercecer. Kop surat dan alamat wajar muncul di situ.")


def main() -> int:
    perintah = sys.argv[1] if len(sys.argv) > 1 else ""
    sisa = sys.argv[2:]
    if perintah == "kolom":
        kolom()
    elif perintah == "pdf":
        pdf(sisa)
    elif perintah == "cocok":
        cocok(sisa)
    elif perintah == "audit":
        audit(sisa)
    else:
        print("Perintah: kolom | pdf | cocok | audit")
        print("  kolom              72 kolom standar beserta perannya")
        print("  pdf   [berkas]     hasil baca satu PDF")
        print("  cocok \"Nilai...\"   uji satu nama parameter")
        print("  audit [berkas]     periksa ada data PDF yang tercecer")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
