PY ?= .venv/bin/python
PORT ?= 8000

.PHONY: setup test test-js test-all ingest demo eval shots cover

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	npm install --no-audit --no-fund

test:
	$(PY) -m pytest -q

test-js:
	npm test --silent

test-all: test test-js

ingest:
	$(PY) -m docs_chatbot.cli ingest

# Runs on BM25 and the mock model unless a key is set in .env or the environment.
demo: ingest
	@echo "Demo site: http://localhost:$(PORT)/demo   API docs: http://localhost:$(PORT)/docs"
	$(PY) -m uvicorn docs_chatbot.app:app_factory --factory --port $(PORT)

eval:
	$(PY) eval/run_eval.py --verbose

shots:
	node scripts/screenshots.js

cover:
	node scripts/make_cover.js
