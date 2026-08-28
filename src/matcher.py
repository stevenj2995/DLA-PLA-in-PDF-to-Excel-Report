from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config
from .excel import Kolom, Skema

KAMUS: dict[str, list[str]] = {
    "B": ["tanggal kejadian", "tanggal kerugian", "tgl kejadian", "tanggal loss",
          "date of loss", "tanggal peristiwa", "dol"],

    "C": ["jam kejadian", "waktu kejadian", "pukul kejadian", "time of loss", "jam loss"],

    "D": ["nomor polis", "no polis", "polis", "policy no", "policy number", "nomor pertanggungan"],

    "E": ["nomor objek", "objek", "object no", "object number", "nomor unit"],

    "H": ["nama tertanggung", "tertanggung", "nama pelapor", "pelapor",
          "reported name", "insured", "insured name", "nama pemegang polis"],

    "I": ["alamat tertanggung", "alamat pelapor", "alamat", "reported address",
          "insured address", "alamat lengkap"],

    "S": ["tanggal lapor", "tanggal pelaporan", "tanggal notifikasi", "tgl lapor",
          "notification date", "tanggal surat", "tanggal laporan"],

    "T": ["jam lapor", "waktu pelaporan", "jam pelaporan", "notification time"],

    "V": ["penyebab kerugian", "penyebab kejadian", "sebab kerugian", "penyebab",
          "cause of loss", "penyebab klaim"],

    "Y": ["nomor referensi", "nomor laporan", "nomor klaim eksternal",
          "claim external ref no", "reference number", "nomor surat"],

    "Z": ["kode pos", "postal code", "zip code", "kodepos"],

    "AA": ["lokasi kejadian", "detail lokasi", "tempat kejadian", "lokasi kerugian",
           "lokasi", "detail location of loss", "location of loss"],

    "AB": ["detail kejadian", "kronologi", "kronologis", "uraian kejadian",
           "rincian kejadian", "detail of event", "deskripsi kejadian"],

    "AC": ["jenis kerusakan", "sifat kerusakan", "kerusakan", "nature of damage",
           "objek pertanggungan", "uraian kerusakan", "deskripsi kerusakan"],

    "AI": ["jaminan", "luas jaminan", "coverage", "jenis jaminan", "pertanggungan"],

    "AK": ["dibayarkan kepada", "pembayaran kepada", "penerima pembayaran", "pay to"],

    "AL": ["penggunaan", "kegunaan", "usage"],

    "AQ": ["nilai kerugian", "jumlah kerugian", "nilai klaim", "estimasi kerugian",
           "nilai adjustment", "net adjustment", "md gross amount", "gross amount",
           "total kerugian", "nilai ganti rugi"],

    "BT": ["share aab", "porsi aab", "bagian aab", "share", "porsi"],
}

def bersihkan(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", str(s))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    s = re.sub(r"\b(nomor|number|nomer)\b", "no", s)
    return " ".join(s.split())


@dataclass
class Cocok:
    kolom: str | None
    header: str | None
    skor: float
    cara: str
    alasan: str = ""

    @property
    def diterima(self) -> bool:
        return self.kolom is not None

    @property
    def perlu_ditinjau(self) -> bool:
        return self.diterima and self.cara == "analisis_makna" and self.skor < config.YAKIN


# jalur utama
@lru_cache(maxsize=1)
def _model_utama():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception:
        return None


class Pencocok:
    def __init__(self, skema: Skema):
        self.skema = skema
        self.target: list[Kolom] = skema.target_pencocokan
        self.model = _model_utama()
        self._sinonim = {k.huruf: [k.nama_bersih] + KAMUS.get(k.huruf, [])
                         for k in self.target}
        self._siapkan_tfidf()
        self._siapkan_model()

    @property
    def jalur(self) -> str:
        return ("utama (model makna)" if self.model
                else "cadangan (kamus + kemiripan kata)")

    def _siapkan_tfidf(self) -> None:
        korpus = [" ".join(bersihkan(x) for x in self._sinonim[k.huruf])
                  for k in self.target]
        self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self._matriks = self._tfidf.fit_transform(korpus) if korpus else None

    def _siapkan_model(self) -> None:
        self._emb = None
        if self.model is None:
            return
        frasa, milik = [], []
        for i, k in enumerate(self.target):
            for f in self._sinonim[k.huruf]:
                frasa.append(f)
                milik.append(i)
        try:
            import numpy as np
            self._emb = self.model.encode(frasa, normalize_embeddings=True)
            self._milik = np.asarray(milik)
        except Exception:
            self._emb = None

    def cocokkan(self, param_pdf: str) -> Cocok:
        p = bersihkan(param_pdf)
        if not p:
            return Cocok(None, None, 0.0, "tidak_cocok", "parameter kosong")

        # sama persis
        for k in self.target:
            if p == bersihkan(k.nama_bersih):
                return Cocok(k.huruf, k.nama_bersih, 1.0, "sama_persis",
                             "nama parameter sama dengan kolom standar")

        # kamus
        for k in self.target:
            for sinonim in KAMUS.get(k.huruf, []):
                if p == bersihkan(sinonim):
                    return Cocok(k.huruf, k.nama_bersih, 0.97, "kamus",
                                 "terdaftar sebagai padanan " + k.nama_bersih)

        # analisis makna
        peringkat = self._peringkat(param_pdf, p)
        if peringkat:
            kolom, skor = peringkat[0]
            if skor >= config.RAGU:
                c = Cocok(kolom.huruf, kolom.nama_bersih, skor, "analisis_makna",
                          "mirip makna dengan " + kolom.nama_bersih)
                if len(peringkat) > 1 and skor - peringkat[1][1] < 0.08:
                    c.alasan += "; hampir seimbang dengan " + peringkat[1][0].nama_bersih
                return c

        dekat = ""
        if peringkat:
            dekat = " (paling dekat: %s, skor %.2f)" % (
                peringkat[0][0].nama_bersih, peringkat[0][1])
        return Cocok(None, None, peringkat[0][1] if peringkat else 0.0, "tidak_cocok",
                     "tidak ada parameter yang cocok di excelnya" + dekat)

    def _peringkat(self, asli: str, bersih: str) -> list[tuple[Kolom, float]]:
        makna = None
        if self._emb is not None:
            try:
                import numpy as np
                sim = self._emb @ self.model.encode([asli], normalize_embeddings=True)[0]
                # tiap kolom diwakili sinonimnya yang paling mirip
                makna = np.array([
                    float(sim[self._milik == i].max()) if (self._milik == i).any() else 0.0
                    for i in range(len(self.target))
                ])
            except Exception:
                makna = None

        tf = None
        if self._matriks is not None:
            tf = cosine_similarity(self._tfidf.transform([bersih]), self._matriks).ravel()

        skor: list[tuple[Kolom, float]] = []
        for i, k in enumerate(self.target):
            kandidat = [bersihkan(x) for x in self._sinonim[k.huruf]]
            mirip_huruf = max(fuzz.token_set_ratio(bersih, c) for c in kandidat) / 100.0
            cadangan = 0.55 * mirip_huruf + 0.45 * (float(tf[i]) if tf is not None else 0.0)
            nilai = (0.75 * float(makna[i]) + 0.25 * cadangan
                     if makna is not None else cadangan)
            skor.append((k, round(min(nilai, 0.999), 3)))

        skor.sort(key=lambda x: x[1], reverse=True)
        return skor

def model_makna_ada() -> bool:
    return _model_utama() is not None
