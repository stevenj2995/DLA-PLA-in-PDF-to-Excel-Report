from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, memori, teks
from .excel import Baris, Skema, muat as muat_skema, tulis
from .matcher import Pencocok
from .memori import GudangProfil, Profil
from .pdf_reader import DokumenPdf, baca, ocr_tersedia
from .teks import deteksi, nama_folder

# Flow: PDF di INPUT -> baca -> deteksi perusahaan -> sortir -> generate Excel 
# Satu Excel per perusahaan, diletakkan di folder perusahaannya masing-masing.

@dataclass
class HasilPdf:
    path: Path
    dokumen: DokumenPdf | None = None
    perusahaan: str | None = None
    keyakinan: float = 0.0
    tingkat: str = "tidak_terdeteksi"
    baris: Baris | None = None
    peringatan: list[str] = field(default_factory=list)
    dilewati: str | None = None
    tujuan: Path | None = None


@dataclass
class HasilProses:
    mulai: datetime = field(default_factory=datetime.now)
    pdf: list[HasilPdf] = field(default_factory=list)
    excel: list[dict] = field(default_factory=list)
    perusahaan_baru: list[str] = field(default_factory=list)
    catatan_umum: list[str] = field(default_factory=list)

    @property
    def berhasil(self) -> list[HasilPdf]:
        return [h for h in self.pdf if h.baris is not None]

    @property
    def perlu_ditinjau(self) -> list[HasilPdf]:
        return [h for h in self.pdf if h.peringatan and h.dilewati is None]

    @property
    def gagal(self) -> list[HasilPdf]:
        return [h for h in self.pdf if h.dilewati]


# sesuaikan bentuk nilai dengan kolom tujuannya
def _rapikan_nilai(kolom: str, mentah):
    if kolom in ("B", "S"):
        d = teks.parse_tanggal(mentah)
        return teks.format_tanggal(d) or teks.rapikan_teks(mentah, 40)
    if kolom in ("C", "T"):
        return teks.parse_jam(mentah) or teks.rapikan_teks(mentah, 20)
    if kolom == "Z":
        return teks.parse_kode_pos(mentah) or teks.rapikan_teks(mentah, 10)
    if kolom == "AQ":
        return teks.parse_uang(mentah)
    if kolom == "BT":
        return teks.parse_persen(mentah)
    return teks.rapikan_teks(mentah)


# ubah isi satu PDF menjadi satu baris Excel
def _susun_baris(dok: DokumenPdf, profil: Profil, pencocok: Pencocok,
                 skema: Skema) -> tuple[Baris, list[str]]:
    b = Baris(sumber=dok.path.name)
    catatan: list[str] = []

    for param, mentah in dok.pasangan_kunci_nilai().items():
        kolom = profil.kolom_untuk(param)
        if kolom is None:
            c = pencocok.cocokkan(param)
            if c.diterima:
                profil.ingat_parameter(param, c.kolom, c.cara, c.skor)
                kolom = c.kolom
                if c.perlu_ditinjau:
                    catatan.append(
                        f"'{param}' dipetakan ke {c.kolom} ({c.header}) lewat "
                        f"analisis makna dengan skor {c.skor:.2f} - mohon dicek")
            else:
                profil.ingat_tidak_cocok(param, c.alasan)
                continue
        if kolom in b.nilai:
            continue # ambil kemunculan pertama
        nilai = _rapikan_nilai(kolom, mentah)
        if nilai is not None and nilai != "":
            b.nilai[kolom] = nilai

    # Reported Name = tertanggung, dan itu sudah dipastikan waktu deteksi lewat
    # label "Insured Name" / "Name of Insured". Ditimpa di sini karena pencocok
    # sering menyambar pihak lain - paling sering justru Astra Buana.
    b.nilai[config.KOLOM_NAMA_TERTANGGUNG] = profil.nama_resmi

    if config.KOLOM_TANGGAL_SURAT:
        d, kota, _ = teks.tanggal_kaki_surat(dok.teks)
        if d:
            b.nilai.setdefault(
                config.KOLOM_TANGGAL_SURAT,
                teks.format_tanggal(d, config.FORMAT_TANGGAL_SURAT))
            if kota:
                b.nilai.setdefault("AA", kota)

    polis = b.nilai.get("D")
    if polis and polis in config.SHARE_PER_POLIS:
        share = config.SHARE_PER_POLIS[polis]
        b.nilai["BT"] = f"{share * 100:g}%"
        b.nilai["_share_aab"] = f"{share * 100:g}%"

    for k in skema.target_pencocokan:
        if k.huruf in config.KOLOM_DITUNDA:
            continue
        if k.huruf not in b.nilai:
            b.nilai[k.huruf] = (
                f"N/A: tidak ada parameter yang cocok di PDF untuk '{k.nama_bersih}'")

    b.peringatan = catatan
    return b, catatan

def proses(
    *,
    email_operator: str,
    folder_input: Path | None = None,
    lapor=None,
) -> HasilProses:
    def _kabar(pesan: str):
        if lapor:
            lapor(pesan)

    config.siapkan_folder()
    hasil = HasilProses()
    skema = muat_skema()
    pencocok = Pencocok(skema)
    gudang = GudangProfil()

    hasil.catatan_umum.append(f"Jalur analisis makna: {pencocok.jalur}")
    if not ocr_tersedia():
        hasil.catatan_umum.append(
            "OCR belum terpasang - PDF hasil scan tidak bisa dibaca isinya.")

    daftar = memori.daftar_pdf(folder_input)
    if not daftar:
        hasil.catatan_umum.append(f"Tidak ada PDF di {folder_input or config.INPUT_DIR}")
        return hasil

    kelompok: dict[str, list[HasilPdf]] = {}
    for p in daftar:
        _kabar(f"Membaca {p.name}")
        h = HasilPdf(path=p)
        h.dokumen = baca(p)
        h.peringatan.extend(h.dokumen.peringatan)

        if h.dokumen.gagal:
            h.dilewati = h.dokumen.gagal
            hasil.pdf.append(h)
            continue

        d = deteksi(h.dokumen.baris, nama_file=p.name)
        h.perusahaan, h.keyakinan, h.tingkat = d.nama, d.keyakinan, d.tingkat
        h.peringatan.extend(d.peringatan)
        hasil.pdf.append(h)

        if d.tingkat == "tidak_terdeteksi":
            continue
        profil, baru = gudang.ambil_atau_buat(d.nama)
        if baru:
            hasil.perusahaan_baru.append(profil.nama_resmi)
        kelompok.setdefault(profil.kunci, []).append(h)

    stempel = hasil.mulai.strftime("%Y%m%d")
    for anggota in kelompok.values():
        profil = gudang.cari(anggota[0].perusahaan)
        _kabar(f"Menyusun {profil.nama_resmi} ({len(anggota)} PDF)")
        folder = memori.folder_perusahaan(profil.grup, profil.folder)
        folder_pdf = folder / config.SUBFOLDER_PDF

        baris: list[Baris] = []
        for h in anggota:
            b, catatan = _susun_baris(h.dokumen, profil, pencocok, skema)
            ref = b.nilai.get(config.KOLOM_REF_UNIK)
            baru = ref and not str(ref).startswith("N/A")
            if baru and ref in profil.ref_sudah_diproses:
                h.dilewati = f"sudah pernah diproses (ref {ref})"
                h.tujuan = memori.pindahkan(h.path, folder_pdf, alasan="duplikat")
                continue
            if baru:
                profil.ref_sudah_diproses.append(str(ref))
            h.baris = b
            h.peringatan.extend(catatan)
            baris.append(b)

        if baris:
            nama_excel = f"{nama_folder(profil.nama_resmi)}_{stempel}.xlsx"
            ringkas = tulis(baris, folder / nama_excel,
                            email_operator=email_operator, skema=skema)
            ringkas["perusahaan"] = profil.nama_resmi
            if not ringkas["dropdown_utuh"]:
                hasil.catatan_umum.append(
                    f"{profil.nama_resmi}: dropdown tidak utuh "
                    f"({ringkas['dropdown_hasil']}/{ringkas['dropdown_asli']})")
            hasil.excel.append(ringkas)

        for h in anggota:
            if h.tujuan is None:
                h.tujuan = memori.pindahkan(
                    h.path, folder_pdf,
                    alasan=f"{profil.nama_resmi} (keyakinan {h.keyakinan:.2f})")
        profil.jumlah_pdf += len(baris)
        gudang.simpan(profil)

    for h in hasil.pdf:
        if h.tujuan is None and h.path.exists():
            h.tujuan = memori.pindahkan(
                h.path, memori.folder_tidak_terdeteksi(),
                alasan=h.dilewati or "perusahaan tidak terdeteksi")

    tulis_laporan(hasil)
    return hasil


def tulis_laporan(hasil: HasilProses) -> Path:
    f = config.OUTPUT_DIR / f"_LAPORAN_{hasil.mulai:%Y%m%d_%H%M%S}.txt"
    f.parent.mkdir(parents=True, exist_ok=True)

    b: list[str] = []
    b.append("LAPORAN PROSES OTOMASI PDF -> EXCEL")
    b.append(f"Waktu   : {hasil.mulai:%Y-%m-%d %H:%M:%S}")
    b.append(f"Total   : {len(hasil.pdf)} PDF | berhasil {len(hasil.berhasil)} | "
             f"dilewati {len(hasil.gagal)} | perlu ditinjau {len(hasil.perlu_ditinjau)}")
    b.append("")
    for c in hasil.catatan_umum:
        b.append(f"CATATAN: {c}")
    if hasil.perusahaan_baru:
        b.append("")
        b.append("PERUSAHAAN BARU (profil memory dibuat):")
        b += [f"  - {n}" for n in hasil.perusahaan_baru]
    if hasil.excel:
        b.append("")
        b.append("FILE EXCEL YANG DIHASILKAN:")
        for e in hasil.excel:
            utuh = "dropdown utuh" if e["dropdown_utuh"] else "DROPDOWN RUSAK"
            b.append(f"  - {e['perusahaan']}: {e['baris']} baris, {utuh}")
            b.append(f"    {e['file']}")
    if hasil.perlu_ditinjau:
        b.append("")
        b.append("PERLU DITINJAU:")
        for h in hasil.perlu_ditinjau:
            b.append(f"  - {h.path.name} (perusahaan: {h.perusahaan or '-'}, "
                     f"keyakinan {h.keyakinan:.2f})")
            b += [f"      ! {w}" for w in h.peringatan]
    if hasil.gagal:
        b.append("")
        b.append("DILEWATI:")
        b += [f"  - {h.path.name}: {h.dilewati}" for h in hasil.gagal]

    f.write_text("\n".join(b), encoding="utf-8")
    return f
