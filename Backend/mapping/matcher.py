from __future__ import annotations
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .. import settings
from ..build.excel import Column, Schema

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

SYNONYMS: dict[str, list[str]] = {
    "B": ["tanggal kejadian", "tanggal kerugian", "tgl kejadian", "tanggal loss",
          "date of loss", "tanggal peristiwa", "dol"],

    "C": ["jam kejadian", "waktu kejadian", "pukul kejadian", "time of loss", "jam loss"],

    "D": ["nomor polis", "no polis", "polis", "policy no", "policy number", "nomor pertanggungan"],

    "E": ["nomor objek", "objek", "object no", "object number", "nomor unit"],

    "H": ["nama tertanggung", "tertanggung", "nama pelapor", "pelapor",
          "reported name", "insured", "insured name", "nama pemegang polis",
          "name of insured", "the insured", "insured party"],

    "I": ["alamat tertanggung", "alamat pelapor", "alamat", "reported address",
          "insured address", "alamat lengkap"],

    "S": ["tanggal lapor", "tanggal pelaporan", "tanggal notifikasi", "tgl lapor",
          "notification date", "tanggal surat", "tanggal laporan",
          "cedent report date", "cedant report date", "report date"],

    "T": ["jam lapor", "waktu pelaporan", "jam pelaporan", "notification time"],

    "V": ["penyebab kerugian", "penyebab kejadian", "sebab kerugian", "penyebab",
          "cause of loss", "penyebab klaim"],

    "Y": ["nomor referensi", "nomor laporan", "nomor klaim eksternal",
          "claim external ref no", "reference number", "nomor surat",
          "claim no", "claim number", "claim ref", "your claim ref",
          "client claim ref", "ref no", "reff no", "ibs reff no",
          "your reference", "registration number", "no dla"],

    "Z": ["kode pos", "postal code", "zip code", "kodepos"],

    "AA": ["lokasi kejadian", "detail lokasi", "tempat kejadian", "lokasi kerugian",
           "lokasi", "detail location of loss", "location of loss",
           "place of loss", "location of risk", "lokasi risiko", "loss location"],

    "AB": ["detail kejadian", "kronologi", "kronologis", "uraian kejadian",
           "rincian kejadian", "detail of event", "deskripsi kejadian",
           "description of loss", "details of loss", "loss details",
           "uraian kerugian"],

    "AC": ["jenis kerusakan", "sifat kerusakan", "kerusakan", "nature of damage",
           "objek pertanggungan", "uraian kerusakan", "deskripsi kerusakan"],

    "AI": ["jaminan", "luas jaminan", "coverage", "jenis jaminan", "pertanggungan"],

    "AK": ["dibayarkan kepada", "pembayaran kepada", "penerima pembayaran", "pay to"],

    "AL": ["penggunaan", "kegunaan", "usage"],

    "AQ": ["nilai kerugian", "jumlah kerugian", "nilai klaim", "estimasi kerugian",
           "nilai adjustment", "net adjustment", "md gross amount", "gross amount",
           "total kerugian", "nilai ganti rugi",
           # "Definite Claim Amount" is the indemnity before it, so it is deliberately not listed here. 
           "nett amount", "net amount", "total nett claim", "adjusted claim",
           "claim 100",
           # last resort
           "total"],

    "AP": ["currency", "mata uang", "kurs", "curr"],

    "BT": ["share aab", "porsi aab", "bagian aab", "share", "porsi", "your share",
           "your share of claim", "your share of loss", "your share on nett loss",
           "our share amount"],
}

def simplify(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", str(s))
    s = re.sub(r"[^\w\s]", " ", s.lower())
    s = re.sub(r"\b(nomor|number|nomer)\b", "no", s)
    return " ".join(s.split())


@dataclass
class Match:
    column: str | None
    header: str | None
    score: float
    method: str
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.column is not None

    @property
    def needs_review(self) -> bool:
        return self.accepted and self.method == "semantic" and self.score < settings.CONFIDENT


@lru_cache(maxsize=1)
def _semantic_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except Exception:
        return None


class Matcher:
    def __init__(self, schema: Schema):
        self.schema = schema
        self.targets: list[Column] = schema.match_targets
        self.model = _semantic_model()
        self._synonyms = {k.letter: [k.clean_name] + SYNONYMS.get(k.letter, []) for k in self.targets}
        self._not_a_column = {simplify(x) for x in settings.NOT_A_COLUMN}
        self._build_tfidf()
        self._build_embeddings()

    @property
    def mode(self) -> str:
        return ("utama (model makna)" if self.model else "cadangan (kamus + kemiripan kata)")

    def _build_tfidf(self) -> None:
        corpus = [" ".join(simplify(x) for x in self._synonyms[k.letter]) for k in self.targets]
        self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self._matrix = self._tfidf.fit_transform(corpus) if corpus else None

    def _build_embeddings(self) -> None:
        self._emb = None
        if self.model is None:
            return
        phrases, owner = [], []
        for i, k in enumerate(self.targets):
            for f in self._synonyms[k.letter]:
                phrases.append(f)
                owner.append(i)
        try:
            import numpy as np
            self._emb = self.model.encode(phrases, normalize_embeddings=True)
            self._owner = np.asarray(owner)
        except Exception:
            self._emb = None

    def match(self, pdf_param: str) -> Match:
        p = simplify(pdf_param)
        if not p:
            return Match(None, None, 0.0, "no_match", "parameter kosong")

        if p in self._not_a_column:
            return Match(None, None, 0.0, "no_match", "tidak ada kolomnya di template standar")

        # exact
        for k in self.targets:
            if p == simplify(k.clean_name):
                return Match(k.letter, k.clean_name, 1.0, "exact", "nama parameter sama dengan kolom standar")

        # dictionary
        for k in self.targets:
            for i, synonym in enumerate(SYNONYMS.get(k.letter, [])):
                if p == simplify(synonym):
                    return Match(k.letter, k.clean_name, 0.97 - 0.001 * i,
                                 "dictionary", "terdaftar sebagai padanan " + k.clean_name)

        # semantic
        ranking = self._rank(pdf_param, p)
        if ranking:
            column, score = ranking[0]
            if score >= settings.MATCH_MINIMUM:
                c = Match(column.letter, column.clean_name, score, "semantic",
                          "mirip makna dengan " + column.clean_name)
                if len(ranking) > 1 and score - ranking[1][1] < 0.08:
                    c.reason += "; hampir seimbang dengan " + ranking[1][0].clean_name
                return c

        closest = ""
        if ranking:
            closest = " (paling dekat: %s, skor %.2f)" % (
                ranking[0][0].clean_name, ranking[0][1])
        return Match(None, None, ranking[0][1] if ranking else 0.0, "no_match", "tidak ada parameter yang cocok di excelnya" + closest)

    def _rank(self, original: str, cleaned: str) -> list[tuple[Column, float]]:
        semantic = None
        if self._emb is not None:
            try:
                import numpy as np
                sim = self._emb @ self.model.encode([original], normalize_embeddings=True)[0]
                # each column scores as its best-matching synonym
                semantic = np.array([
                    float(sim[self._owner == i].max()) if (self._owner == i).any() else 0.0
                    for i in range(len(self.targets))
                ])
            except Exception:
                semantic = None

        tf = None
        if self._matrix is not None:
            tf = cosine_similarity(self._tfidf.transform([cleaned]), self._matrix).ravel()

        scores: list[tuple[Column, float]] = []
        for i, k in enumerate(self.targets):
            variants = [simplify(x) for x in self._synonyms[k.letter]]
            char_ratio = max(fuzz.token_set_ratio(cleaned, c) for c in variants) / 100.0
            fallback = 0.55 * char_ratio + 0.45 * (float(tf[i]) if tf is not None else 0.0)
            value = (0.75 * float(semantic[i]) + 0.25 * fallback
                     if semantic is not None else fallback)
            scores.append((k, round(min(value, 0.999), 3)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

def semantic_model_available() -> bool:
    return _semantic_model() is not None
