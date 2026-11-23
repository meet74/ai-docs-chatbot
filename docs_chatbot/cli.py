"""python -m docs_chatbot.cli ingest [--kb DIR] [--out DIR]"""
import argparse
import asyncio

from .app import build_index, make_embedder
from .config import Settings


def main() -> None:
    p = argparse.ArgumentParser(prog="docs_chatbot")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="chunk the knowledge base and write the index")
    ing.add_argument("--kb")
    ing.add_argument("--out")
    args = p.parse_args()

    s = Settings()
    if args.kb:
        s.kb_dir = type(s.kb_dir)(args.kb)
    if args.out:
        s.index_dir = type(s.index_dir)(args.out)
    index = asyncio.run(build_index(s, make_embedder(s)))
    kind = "BM25 + embeddings" if index.embeddings is not None else "BM25"
    print(f"Indexed {len(index.docs)} documents into {len(index.chunks)} chunks ({kind}) at {s.index_dir}")


if __name__ == "__main__":
    main()
