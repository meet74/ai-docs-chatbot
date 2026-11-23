import asyncio

import numpy as np

from docs_chatbot.embeddings import EmbeddingClient
from docs_chatbot.index import Index
from docs_chatbot.retrieval import Retriever, rrf


def search(retriever, q, k=3):
    return asyncio.run(retriever.search(q, k))


def test_bm25_finds_the_right_document(retriever):
    top = search(retriever, "What is the cancellation fee for a no-show?")
    assert top[0].chunk.source == "booking-and-cancellation.md"


def test_price_question_hits_services(retriever):
    top = search(retriever, "How much is a molar root canal?")
    assert top[0].chunk.source == "services-and-prices.md"
    assert "$1,290" in top[0].chunk.text


def test_unrelated_question_has_low_coverage(retriever):
    top = search(retriever, "What is the capital of France?")
    assert max((p.coverage for p in top), default=0) < 0.2


def test_index_round_trip(index, tmp_path):
    index.save(tmp_path)
    again = Index.load(tmp_path)
    assert [c.id for c in again.chunks] == [c.id for c in index.chunks]
    assert (tmp_path / "meta.json").exists()
    assert not (tmp_path / "embeddings.npy").exists()


def test_rrf_prefers_items_ranked_high_in_both_lists():
    fused = rrf([[1, 2, 3], [3, 1, 4]])
    assert max(fused, key=fused.get) == 1
    assert fused[3] > fused[2]


def test_hybrid_uses_embeddings_when_enabled(index):
    """A fake embedding endpoint that maps every text near the 'insurance' chunk."""
    target = next(i for i, c in enumerate(index.chunks) if c.section == "Payment plans")
    vecs = np.eye(len(index.chunks), dtype=np.float32)

    class Fake(EmbeddingClient):
        async def embed_query(self, text):
            return vecs[target]

    emb = Index(index.chunks, vecs)
    r = Retriever(emb, Fake("openai", "http://x", "m", "k"))
    top = asyncio.run(r.search("zzz unmatched words", 3))
    assert top and top[0].chunk.section == "Payment plans"
    # with a query that BM25 also likes, the fused list still contains the BM25 winner
    top = asyncio.run(r.search("cancellation notice", 4))
    assert any(p.chunk.source == "booking-and-cancellation.md" for p in top)


def test_embedding_client_batches_and_normalises():
    import httpx

    seen = []

    def handler(req):
        body = req.read()
        import json
        seen.append(json.loads(body))
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [3.0, 4.0]} for i in range(len(seen[-1]["input"]))]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = EmbeddingClient("voyage", "http://emb.test/v1", "m", "k", http=http, batch_size=2)
    m = asyncio.run(c.embed_documents(["a", "b", "c"]))
    assert len(seen) == 2 and seen[0]["input_type"] == "document"
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0)
