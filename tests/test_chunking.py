from pathlib import Path

from docs_chatbot.ingest import chunk_document, chunk_section, extract, split_sections
from docs_chatbot.text import tokenize

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


def test_markdown_headings_are_kept_in_section_path(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# Title\n\nintro line\n\n## Billing\n\n### Late fees\n\nA late fee is $15.\n")
    chunks = chunk_document(f)
    assert [c.section for c in chunks] == ["Overview", "Billing > Late fees"]
    assert chunks[1].doc == "Title" and "$15" in chunks[1].text


def test_overlap_repeats_tail_of_previous_chunk():
    units = [f"sentence number {i} has exactly seven words." for i in range(30)]
    chunks = chunk_section(units, max_words=40, overlap_words=14)
    assert len(chunks) > 2
    for a, b in zip(chunks, chunks[1:]):
        assert a.splitlines()[-1] in b.splitlines()
    assert all(len(c.split()) <= 40 + 14 for c in chunks)


def test_every_unit_survives_chunking():
    units = [f"unit {i} text" for i in range(50)]
    joined = "\n".join(chunk_section(units, 20, 6))
    assert all(u in joined for u in units)


def test_html_drops_scripts_and_nav_and_keeps_table_rows():
    title, md = extract(KB / "hours-and-locations.html")
    assert title == "Hours and Locations"
    assert "tracking" not in md and "Book online" not in md
    assert "- Saturday - 9:00 am to 2:00 pm" in md


def test_pdf_headings_found_by_font_size():
    _, md = extract(KB / "aftercare-instructions.pdf")
    assert "## After a tooth extraction" in md
    sections = {s.path[-1] for s in split_sections(md) if s.path}
    assert "After a filling" in sections


def test_txt_numbered_headings():
    chunks = chunk_document(KB / "privacy-policy.txt")
    assert any(c.section == "How long we keep records" for c in chunks)


def test_markdown_table_rows_become_lines():
    chunks = chunk_document(KB / "services-and-prices.md")
    assert any("White filling, one surface - $210" in c.text for c in chunks)


def test_tokenizer_matches_plural_and_cost_words():
    assert tokenize("cleanings") == tokenize("cleaning") == tokenize("cleaned")
    assert tokenize("How much does it cost") == ["price"]
