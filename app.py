# Antarmuka Streamlit. Jalankan: streamlit run app.py
# Semua proses terjadi di laptop ini, tidak ada data yang dikirim ke mana pun.
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from src import config, memori, pipeline, tampilan


# Streamlit itu server web, bukan skrip biasa. Kalau dijalankan lewat
# "python app.py" atau tombol Run di VSCode, semua perintah st.* tidak punya
# tempat tampil dan yang keluar hanya peringatan "missing ScriptRunContext".
# Alihkan sendiri supaya tidak perlu ingat perintahnya.
def _pastikan_lewat_streamlit() -> None:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except ImportError:
        return
    if get_script_run_ctx() is not None:
        return
    print("Dialihkan ke: streamlit run app.py\n")
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__]))


_pastikan_lewat_streamlit()

st.set_page_config(page_title="DLA to Excel Report", page_icon="📄", layout="wide")
st.markdown(tampilan.css(), unsafe_allow_html=True)


def tulis(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def judul_bagian(teks: str) -> None:
    tulis(f'<p class="astra-judul-bagian">{teks}</p>')


tulis(tampilan.judul_utama("DLA to Excel Report"))

# ------------------------------------------------------------------ panel kiri
with st.sidebar:
    if tampilan.ada_logo():
        tulis(f'<div class="astra-sidebar-logo">'
              f'<img src="data:image/png;base64,{tampilan.logo_base64()}"></div>')

    tulis('<div class="astra-sidebar-bagian" style="margin-top:0;border-top:none;'
          'padding-top:0">Masukkan Email</div>')
    email = st.text_input(
        "Email Anda", value="", placeholder="Masukkan email anda...",
        help="Diisi ke kolom N — Reported Email Address — di setiap baris.")

# ------------------------------------------------------------------ sumber PDF
config.siapkan_folder()
folder_dipakai: Path | None = None

with st.container(border=True, key="panel_sumber"):
    judul_bagian("Langkah 1 · Sumber PDF")

    sumber = st.radio(
        "Sumber PDF", ["📁  Folder INPUT", "🗜️  Upload file ZIP"],
        horizontal=True, label_visibility="collapsed")

    if "Folder INPUT" in sumber:
        lokasi = st.text_input("Lokasi folder", value=str(config.INPUT_DIR))
        p = Path(lokasi)
        if not p.exists():
            st.error("Folder tidak ditemukan")
        else:
            jml = len(memori.daftar_pdf(p))
            # jangan ditulis sebagai ekspresi satu baris -- "magic" Streamlit akan
            # menganggap nilai kembaliannya sebagai isi halaman dan mencetak
            # objek DeltaGenerator beserta seluruh dokumentasinya ke layar
            if jml:
                st.success(f"{jml} PDF siap diproses")
                folder_dipakai = p
            else:
                tulis(tampilan.kosong(
                    "📂", "Belum ada PDF di folder ini",
                    "Taruh file PDF ke folder INPUT, lalu muat ulang halaman."))
    else:
        berkas = st.file_uploader("File ZIP berisi PDF", type=["zip"])
        if berkas is None:
            tulis(tampilan.kosong(
                "🗜️", "Belum ada ZIP diunggah",
                "Tarik file ZIP ke kotak di atas, atau klik untuk memilih."))
        else:
            tujuan = Path(tempfile.mkdtemp()) / "zip"
            tujuan.mkdir(parents=True)
            with zipfile.ZipFile(berkas) as z:
                z.extractall(tujuan)
            jml = len(memori.daftar_pdf(tujuan))
            if jml:
                st.success(f"{jml} PDF diekstrak dari ZIP")
                folder_dipakai = tujuan
            else:
                st.warning("Tidak ada file PDF di dalam ZIP ini")

st.write("")

# ------------------------------------------------------------------ jalankan
ada_email = bool(email.strip())
siap = ada_email and folder_dipakai is not None
selesai = ({1} if folder_dipakai is not None else set()) | ({2} if ada_email else set())
aktif = 1 if folder_dipakai is None else (2 if not ada_email else 3)

with st.container(border=True, key="panel_jalan"):
    judul_bagian("Langkah 2 · Jalankan")
    tulis(tampilan.langkah(aktif, selesai))

    if not ada_email:
        st.warning("Isi terlebih dahulu email Anda untuk mengisi Reported Email Address.")

    kiri, tengah, kanan = st.columns([1, 1.3, 1])
    with tengah:
        mulai = st.button("Proses sekarang", type="primary",
                          disabled=not siap, use_container_width=True)

if mulai:
    kotak = st.empty()
    with st.spinner("Memproses..."):
        hasil = pipeline.proses(
            email_operator=email.strip(),
            folder_input=folder_dipakai,
            lapor=lambda m: kotak.write(f"⏳ {m}"),
        )
    kotak.empty()
    st.write("")

    tulis('<p class="astra-judul-terang">Ringkasan</p>')
    tulis(tampilan.statistik([
        ("PDF diproses", len(hasil.pdf), "📄", tampilan.BIRU),
        ("Baris jadi", len(hasil.berhasil), "✅", tampilan.HIJAU),
        ("Perlu ditinjau", len(hasil.perlu_ditinjau), "⚠️", tampilan.KUNING),
        ("Dilewati", len(hasil.gagal), "⏭️", tampilan.MERAH),
    ]))

    if hasil.catatan_umum or hasil.perusahaan_baru:
        with st.container(border=True, key="panel_catatan"):
            judul_bagian("Catatan proses")
            for catatan in hasil.catatan_umum:
                st.info(catatan)
            if hasil.perusahaan_baru:
                st.success("Perusahaan baru dikenali: "
                           + ", ".join(hasil.perusahaan_baru))
        st.write("")

    if hasil.excel:
        with st.container(border=True, key="panel_hasil"):
            judul_bagian("File Excel yang dihasilkan")
            for e in hasil.excel:
                f = Path(e["file"])
                k1, k2 = st.columns([3.2, 1])
                with k1:
                    tulis(tampilan.kartu_hasil(
                        e["perusahaan"], e["baris"], str(f.relative_to(config.ROOT))))
                    if not e["dropdown_utuh"]:
                        st.error(f"Dropdown tidak utuh: "
                                 f"{e['dropdown_hasil']}/{e['dropdown_asli']}")
                with k2:
                    st.download_button(
                        "⬇  Unduh", f.read_bytes(), file_name=f.name,
                        mime="application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet",
                        key=str(f), use_container_width=True)

    if hasil.perlu_ditinjau:
        st.write("")
        with st.container(border=True, key="panel_tinjau"):
            judul_bagian("Perlu ditinjau")
            for h in hasil.perlu_ditinjau:
                with st.expander(f"⚠️  {h.path.name} — "
                                 f"{h.perusahaan or 'tidak terdeteksi'} "
                                 f"(keyakinan {h.keyakinan:.2f})"):
                    for w in h.peringatan:
                        st.warning(w)

    if hasil.gagal:
        st.write("")
        with st.container(border=True, key="panel_lewat"):
            judul_bagian("Dilewati")
            for h in hasil.gagal:
                st.write(f"- `{h.path.name}` — {h.dilewati}")

    laporan = sorted(config.OUTPUT_DIR.glob("_LAPORAN_*.txt"))
    if laporan:
        st.write("")
        with st.expander(f"📋  Laporan lengkap — {laporan[-1].name}"):
            st.code(laporan[-1].read_text(encoding="utf-8"))
