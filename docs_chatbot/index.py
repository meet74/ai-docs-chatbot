"""On-disk index: chunks.json + embeddings.npy + meta.json. BM25 is rebuilt on load (milliseconds)."""
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .ingest import Chunk
from .text import tokenize


class Index:
    def __init__(self, chunks: list[Chunk], embeddings: np.ndarray | None = None,
                 meta: dict | None = None):
        self.chunks = chunks
        self.embeddings = embeddings
        self.meta = meta or {}
        self._tokens = [tokenize(c.index_text) for c in chunks]
        self._token_sets = [set(t) for t in self._tokens]
        self.bm25 = BM25Okapi(self._tokens) if chunks else None
        n = len(chunks)
        df: dict[str, int] = {}
        for ts in self._token_sets:
            for t in ts:
                df[t] = df.get(t, 0) + 1
        # Plain BM25 idf. rank_bm25 floors common terms, which breaks coverage weighting.
        self.idf = {t: math.log((n - d + 0.5) / (d + 0.5) + 1) for t, d in df.items()}
        self.max_idf = math.log(n + 1) if n else 1.0

    @property
    def docs(self) -> list[str]:
        return sorted({c.source for c in self.chunks})

    def bm25_scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        if not q or self.bm25 is None:
            return np.zeros(len(self.chunks))
        return np.asarray(self.bm25.get_scores(q))

    def coverage(self, query: str, chunk_idx: int) -> float:
        """Share of the question's rare-word weight found in the chunk (0..1).

        Words the corpus has never seen count at maximum weight, so a question about
        something the documents do not mention scores low even if it shares common words.
        """
        terms = set(tokenize(query))
        if not terms:
            return 0.0
        total = hit = 0.0
        for t in terms:
            w = self.idf.get(t, self.max_idf)
            total += w
            if t in self._token_sets[chunk_idx]:
                hit += w
        return hit / total if total else 0.0

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "chunks.json").write_text(
            json.dumps([asdict(c) for c in self.chunks], indent=1), encoding="utf-8")
        emb = directory / "embeddings.npy"
        if self.embeddings is not None:
            np.save(emb, self.embeddings)
        elif emb.exists():
            emb.unlink()
        meta = {**self.meta, "built_at": int(time.time()), "chunks": len(self.chunks),
                "embeddings": self.embeddings is not None}
        (directory / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "Index":
        raw = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        chunks = [Chunk(**r) for r in raw]
        emb_path = directory / "embeddings.npy"
        emb = np.load(emb_path) if emb_path.exists() else None
        meta_path = directory / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return cls(chunks, emb, meta)
