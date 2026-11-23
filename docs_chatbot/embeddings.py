"""Optional embedding provider. Both OpenAI and Voyage expose the same /embeddings shape."""
import httpx
import numpy as np


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self, provider: str, base_url: str, model: str, api_key: str,
                 http: httpx.AsyncClient | None = None, batch_size: int = 64):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.batch_size = batch_size
        self._http = http

    async def _post(self, inputs: list[str], input_type: str) -> list[list[float]]:
        body: dict = {"model": self.model, "input": inputs}
        if self.provider == "voyage":
            body["input_type"] = input_type
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = self._http or httpx.AsyncClient(timeout=30)
        try:
            r = await client.post(f"{self.base_url}/embeddings", json=body, headers=headers)
            r.raise_for_status()
            data = r.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise EmbeddingError(f"embedding request failed: {type(e).__name__}") from e
        finally:
            if self._http is None:
                await client.aclose()
        return [d["embedding"] for d in sorted(data, key=lambda d: d.get("index", 0))]

    async def embed_documents(self, texts: list[str]) -> np.ndarray:
        vecs: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vecs.extend(await self._post(texts[i:i + self.batch_size], "document"))
        return _normalize(np.array(vecs, dtype=np.float32))

    async def embed_query(self, text: str) -> np.ndarray:
        return _normalize(np.array(await self._post([text], "query"), dtype=np.float32))[0]


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.clip(norms, 1e-9, None)
