import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from docs_chatbot.app import build_index, create_app
from docs_chatbot.config import Settings
from docs_chatbot.index import Index
from docs_chatbot.retrieval import Retriever

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, kb_dir=KB, index_dir=tmp_path / "index", db_path=tmp_path / "h.db",
                    llm_provider="mock", whatsapp_verify_token="verify-me", whatsapp_app_secret="app-secret",
                    whatsapp_access_token="wa-token", whatsapp_phone_number_id="1234567890",
                    graph_base_url="http://graph.test/v21.0", handoff_webhook_url="http://hook.test/notify",
                    admin_token="admin-secret")


@pytest.fixture(scope="session")
def index(tmp_path_factory):
    s = Settings(_env_file=None, kb_dir=KB, index_dir=tmp_path_factory.mktemp("idx"))
    return asyncio.run(build_index(s, None))


@pytest.fixture
def retriever(index):
    return Retriever(index)


class Outbox:
    """Fake network: records every outgoing request and answers 200."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})

    def to(self, host_part: str):
        return [r for r in self.requests if host_part in str(r.url)]

    def bodies(self, host_part: str):
        return [json.loads(r.content) for r in self.to(host_part)]


@pytest.fixture
def outbox():
    return Outbox()


@pytest.fixture
def client(settings, outbox):
    http = httpx.AsyncClient(transport=httpx.MockTransport(outbox.handler))
    with TestClient(create_app(settings, http=http)) as c:
        yield c
