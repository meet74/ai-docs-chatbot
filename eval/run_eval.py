"""Run the evaluation set against the real index and write eval/results/<provider>.json.

Retrieval hit@3 is computed offline with BM25 and needs no key. The answer checks run
through the full pipeline with whichever LLM the environment selects (mock by default).
"""
import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from docs_chatbot.app import build_index, make_embedder  # noqa: E402
from docs_chatbot.config import Settings  # noqa: E402
from docs_chatbot.handoff import HandoffStore  # noqa: E402
from docs_chatbot.llm import make_llm  # noqa: E402
from docs_chatbot.memory import SessionStore  # noqa: E402
from docs_chatbot.pipeline import ChatService  # noqa: E402
from docs_chatbot.retrieval import Retriever  # noqa: E402


async def run(verbose: bool) -> dict:
    s = Settings()
    s.handoff_webhook_url = ""            # never call out during evaluation
    tmp = Path(tempfile.mkdtemp())
    s.index_dir, s.db_path = tmp / "index", tmp / "h.db"
    questions = json.loads((ROOT / "eval" / "questions.json").read_text())

    async with httpx.AsyncClient() as http:
        embedder = make_embedder(s, http)
        index = await build_index(s, embedder)
        retriever = Retriever(index, embedder)
        llm = make_llm(s, http)
        chat = ChatService(s, retriever, llm, SessionStore(), HandoffStore(s.db_path), http)

        answerable = [q for q in questions if q["expect"] != "refuse"]
        trick = [q for q in questions if q["expect"] == "refuse"]

        hits3 = hits1 = 0
        rr = 0.0
        rows = []
        for q in answerable:
            top = await retriever.search(q["q"], 3)
            docs = [p.chunk.source for p in top]
            hit3 = q["expect"] in docs
            hits3 += hit3
            hits1 += bool(docs) and docs[0] == q["expect"]
            rr += 1 / (docs.index(q["expect"]) + 1) if hit3 else 0
            r = await chat.handle(f"eval-{q['id']}", q["q"])
            cited = {c.source for c in r.citations}
            rows.append({"id": q["id"], "q": q["q"], "expect": q["expect"], "retrieved": docs,
                         "hit3": hit3, "refused": r.refused or r.needs_human,
                         "cited": sorted(cited), "citation_ok": q["expect"] in cited,
                         "answer": r.answer})
        trick_rows = []
        for q in trick:
            r = await chat.handle(f"eval-{q['id']}", q["q"])
            trick_rows.append({"id": q["id"], "q": q["q"], "kind": q["kind"],
                               "refused": r.refused or r.needs_human, "reason": r.reason,
                               "answer": r.answer})

    n, t = len(answerable), len(trick)
    answered = [r for r in rows if not r["refused"]]
    result = {
        "llm": llm.name,
        "embeddings": index.embeddings is not None,
        "documents": len(index.docs), "chunks": len(index.chunks),
        "answerable": n, "out_of_scope": t,
        "retrieval_hit_at_3": round(hits3 / n, 3),
        "retrieval_hit_at_1": round(hits1 / n, 3),
        "retrieval_mrr_at_3": round(rr / n, 3),
        "answered_rate": round(len(answered) / n, 3),
        "false_refusals": n - len(answered),
        "citation_correct_of_answered": round(sum(r["citation_ok"] for r in answered) / max(1, len(answered)), 3),
        "citation_correct_of_all": round(sum(r["citation_ok"] for r in rows) / n, 3),
        "refusal_correct": round(sum(r["refused"] for r in trick_rows) / t, 3),
        "missed_refusals": [r["id"] for r in trick_rows if not r["refused"]],
        "failed_retrieval": [r["id"] for r in rows if not r["hit3"]],
        "rows": rows, "trick_rows": trick_rows,
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    res = asyncio.run(run(args.verbose))
    res["seconds"] = round(time.time() - t0, 2)
    name = res["llm"].split(":")[0] + ("+emb" if res["embeddings"] else "")
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")

    print(f"LLM: {res['llm']}   embeddings: {res['embeddings']}   chunks: {res['chunks']}")
    print(f"Retrieval hit@3:            {res['retrieval_hit_at_3']:.1%}  ({res['answerable']} answerable questions)")
    print(f"Retrieval hit@1:            {res['retrieval_hit_at_1']:.1%}   MRR@3: {res['retrieval_mrr_at_3']:.3f}")
    print(f"Answered (not refused):     {res['answered_rate']:.1%}   false refusals: {res['false_refusals']}")
    print(f"Citation correct (answered): {res['citation_correct_of_answered']:.1%}")
    print(f"Refusal correct:            {res['refusal_correct']:.1%}  ({res['out_of_scope']} out-of-scope questions)")
    if res["failed_retrieval"]:
        print("Retrieval misses (ids):", res["failed_retrieval"])
    if res["missed_refusals"]:
        print("Missed refusals (ids):", res["missed_refusals"])
    if args.verbose:
        for r in res["rows"]:
            flag = "ok " if r["hit3"] and not r["refused"] and r["citation_ok"] else "BAD"
            print(f"{flag} {r['id']:>2} {r['q'][:55]:<55} -> {r['retrieved']}  refused={r['refused']}")
        for r in res["trick_rows"]:
            print(f"{'ok ' if r['refused'] else 'BAD'} {r['id']:>2} {r['q'][:55]:<55} [{r['kind']}] {r['reason']}")
    print(f"Wrote eval/results/{name}.json")


if __name__ == "__main__":
    main()
