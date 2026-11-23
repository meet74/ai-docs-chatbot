"""Tokenising shared by indexing, retrieval and the mock model.

The stemmer is deliberately tiny. It only has to make "cleanings", "cleaning"
and "cleaned" meet in the middle for BM25; it is not a linguistic stemmer.
"""
import re

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

STOPWORDS = frozenset(
    """a an the and or of to in on at for from by with is are was were be been am do does did
    can could would should will may might i me my we our you your it its this that these those
    what which who whom how when where why if then than so as about into over any some there
    their they them have has had not no yes please tell know want need get just also much many
    s t""".split()
)

# Words a patient uses for "what does it cost" rarely match the page's wording.
# This list is hand-maintained per knowledge base.
SYNONYMS = {
    "cost": "price", "costs": "price", "pricing": "price", "prices": "price",
    "fee": "price", "fees": "price", "charge": "price", "charges": "price",
    "expensive": "price", "cheap": "price",
    "cancel": "cancellation", "cancelling": "cancellation", "canceling": "cancellation",
    "cancelled": "cancellation", "canceled": "cancellation",
}


def stem(word: str) -> str:
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("sses"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    return word


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    out = []
    for raw in _WORD.findall(text.lower()):
        if not keep_stopwords and raw in STOPWORDS:
            continue
        raw = SYNONYMS.get(raw, raw)
        out.append(stem(raw))
    return out
