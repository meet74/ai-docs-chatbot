"""Hybrid retrieval: BM25 always, embeddings when configured, fused with reciprocal rank."""
from dataclasses import dataclass

import numpy as np

from .embeddings import EmbeddingClient, EmbeddingError
from .index import Index
from .ingest import Chunk

RRF_K = 60


@dataclass
class Passage:
    chunk: Chunk
    score: float       # final ranking score (BM25 or fused)
    bm25: float
    coverage: float    # 0..1, see Index.coverage
    rank: int


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for pos, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return fused


class Retriever:
    def __init__(self, index: Index, embedder: EmbeddingClient | None = None):
        self.index = index
        self.embedder = embedder if index.embeddings is not None else None

    async def search(self, query: str, k: int = 4) -> list[Passage]:
        idx = self.index
        if not idx.chunks:
            return []
        bm = idx.bm25_scores(query)
        bm_rank = [int(i) for i in np.argsort(-bm)[: max(k * 4, 10)] if bm[i] > 0]
        rankings = [bm_rank]
        if self.embedder is not None:
            try:
                qv = await self.embedder.embed_query(query)
                sims = idx.embeddings @ qv
                rankings.append([int(i) for i in np.argsort(-sims)[: max(k * 4, 10)]])
            except EmbeddingError:
                pass  # fall back to BM25 alone rather than failing the question
        if len(rankings) == 1:
            order = [(i, float(bm[i])) for i in bm_rank[:k]]
        else:
            fused = rrf(rankings)
            order = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [
            Passage(chunk=idx.chunks[i], score=s, bm25=float(bm[i]),
                    coverage=idx.coverage(query, i), rank=r + 1)
            for r, (i, s) in enumerate(order)
        ]
