from __future__ import annotations

import argparse
from pathlib import Path

from src import memori, pipeline
from src.pdf_reader import ocr_tersedia


def main() -> int:
    ap = argparse.ArgumentParser(description="Otomasi PDF laporan klaim ke Excel standar")
    ap.add_argument("--email", help="email operator, diisi ke kolom N")
    ap.add_argument("--folder", help="folder sumber PDF (bawaan: INPUT)")
    ap.add_argument("--batalkan", action="store_true",
                    help="kembalikan semua PDF ke lokasi semula")
    a = ap.parse_args()

    if a.batalkan:
        print(f"{memori.kembalikan_semua()} file dikembalikan.")
        return 0

    if not a.email:
        ap.error("Email wajib untuk diisi!")

    if not ocr_tersedia():
        print("OCR belum terpasang\n")

    hasil = pipeline.proses(
        email_operator=a.email,
        folder_input=Path(a.folder) if a.folder else None,
        lapor=lambda m: print(f"  .. {m}"),
    )

    print()
    print(f"PDF diproses   : {len(hasil.pdf)}")
    print(f"Baris jadi     : {len(hasil.berhasil)}")
    print(f"Perlu ditinjau : {len(hasil.perlu_ditinjau)}")
    print(f"Dilewati       : {len(hasil.gagal)}")
    for c in hasil.catatan_umum:
        print(f"  catatan: {c}")
    for e in hasil.excel:
        tanda = "ok" if e["dropdown_utuh"] else "DROPDOWN RUSAK"
        print(f"  excel  : {e['perusahaan']} -> {e['baris']} baris [{tanda}]")
    for h in hasil.perlu_ditinjau:
        print(f"  tinjau : {h.path.name}")
        for w in h.peringatan:
            print(f"           ! {w}")
    for h in hasil.gagal:
        print(f"  lewat  : {h.path.name} - {h.dilewati}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
