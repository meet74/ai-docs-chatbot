"""Turn PDF, Markdown, HTML and TXT files into heading-aware chunks."""
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

SUPPORTED = {".pdf", ".md", ".markdown", ".html", ".htm", ".txt"}


@dataclass
class Chunk:
    id: str
    doc: str          # human title, shown in citations
    source: str       # file name
    section: str      # heading path without the doc title
    text: str
    position: int = 0

    @property
    def index_text(self) -> str:
        # The heading is repeated so a query that names the topic beats a passing mention.
        return f"{self.section}. {self.section}. {self.text}"


@dataclass
class Section:
    path: list[str]
    lines: list[str] = field(default_factory=list)


# ---- loaders: every format becomes light markdown (# headings, - bullets) ----

def load_markdown(raw: str) -> str:
    raw = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.S)  # front matter
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("|"):
            if re.fullmatch(r"\|?[\s:|-]+\|?", s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            line = "- " + " - ".join(c for c in cells if c)
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"(\*\*|__|`)", "", line)
        lines.append(line.rstrip())
    return "\n".join(lines)


def load_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    body = soup.body or soup
    wanted = ["h1", "h2", "h3", "h4", "p", "li", "tr", "dt", "dd", "pre", "blockquote"]
    out = []
    if title and not body.find("h1"):
        out.append(f"# {title}")
    for el in body.find_all(wanted):
        if el.name not in ("h1", "h2", "h3", "h4") and el.find_parent(["li", "tr", "p", "dd", "dt"]):
            continue
        if el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["th", "td"])]
            text = " - ".join(c for c in cells if c)
            if el.find("th") and not el.find("td"):
                continue  # header rows only repeat column names
            out.append(f"- {text}" if text else "")
        elif el.name in ("h1", "h2", "h3", "h4"):
            out.append("#" * int(el.name[1]) + " " + el.get_text(" ", strip=True))
        elif el.name == "li":
            out.append("- " + el.get_text(" ", strip=True))
        else:
            out.append(el.get_text(" ", strip=True))
    return "\n".join(out)


_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+([A-Z][^.!?]{2,70})$")


def load_text(raw: str) -> str:
    lines = [l.rstrip() for l in raw.splitlines()]
    out, first = [], True
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            out.append("")
            continue
        nxt_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
        prev_blank = i == 0 or not lines[i - 1].strip()
        if first:
            out.append(f"# {s}")
            first = False
        elif _NUMBERED.match(s) and prev_blank and nxt_blank:
            out.append("## " + _NUMBERED.match(s).group(2))
        elif s.isupper() and len(s) < 70 and prev_blank and nxt_blank:
            out.append("## " + s.title())
        else:
            out.append(s)
    return "\n".join(out)


def load_pdf(path: Path) -> str:
    """Heading detection by font size: anything clearly larger than body text."""
    reader = PdfReader(str(path))
    segs: list[tuple[float, str]] = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            segs.append((round(float(font_size), 1), text))

    for page in reader.pages:
        page.extract_text(visitor_text=visit)
    if not segs:
        return ""
    weights = Counter()
    for size, text in segs:
        weights[size] += len(text.strip())
    body = weights.most_common(1)[0][0]
    heading_sizes = sorted({s for s, _ in segs if s >= body * 1.15}, reverse=True)

    out, para, bullet = [], [], False

    def flush():
        nonlocal para, bullet
        if para:
            out.append(("- " if bullet else "") + " ".join(para))
        para, bullet = [], False

    for size, text in segs:
        t = text.strip()
        if size in heading_sizes:
            flush()
            out.append("#" * (heading_sizes.index(size) + 1) + " " + t)
        elif t in {"-", "•", "*"}:
            flush()
            bullet = True
        else:
            para.append(t)
    flush()
    return "\n".join(out)


def extract(path: Path) -> tuple[str, str]:
    """Return (title, light markdown) for a supported file."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        md = load_pdf(path)
    else:
        raw = path.read_text(encoding="utf-8", errors="replace")
        md = {".md": load_markdown, ".markdown": load_markdown,
              ".html": load_html, ".htm": load_html, ".txt": load_text}[ext](raw)
    md = clean(md)
    m = re.search(r"^#\s+(.+)$", md, flags=re.M)
    title = m.group(1).strip() if m else path.stem.replace("-", " ").replace("_", " ").title()
    return title, md


def clean(text: str) -> str:
    text = text.replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---- chunking ----

def split_sections(md: str) -> list[Section]:
    sections: list[Section] = [Section(path=[])]
    stack: list[tuple[int, str]] = []
    for line in md.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2).strip()))
            # The level-1 heading is the document title, not part of the section path.
            sections.append(Section(path=[t for lv, t in stack if lv > 1]))
        else:
            sections[-1].lines.append(line)
    return [s for s in sections if any(l.strip() for l in s.lines)]


def _units(lines: list[str]) -> list[str]:
    units = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if len(s.split()) > 60:
            units.extend(p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", s) if p)
        else:
            units.append(s)
    return units


def chunk_section(units: list[str], max_words: int, overlap_words: int) -> list[str]:
    """Pack units into chunks of about max_words, repeating the tail of each chunk."""
    chunks: list[list[str]] = []
    cur: list[str] = []
    count = 0
    for u in units:
        w = len(u.split())
        if cur and count + w > max_words:
            chunks.append(cur)
            tail: list[str] = []
            t = 0
            for prev in reversed(cur):
                if t >= overlap_words:
                    break
                tail.insert(0, prev)
                t += len(prev.split())
            # A tail as large as the chunk itself would never make progress.
            cur = tail if t < max_words // 2 else []
            count = sum(len(x.split()) for x in cur)
        cur.append(u)
        count += w
    if cur:
        chunks.append(cur)
    return ["\n".join(c) for c in chunks]


def chunk_document(path: Path, max_words: int = 160, overlap_words: int = 30) -> list[Chunk]:
    title, md = extract(path)
    out: list[Chunk] = []
    for sec in split_sections(md):
        section = " > ".join(sec.path) or "Overview"
        for text in chunk_section(_units(sec.lines), max_words, overlap_words):
            out.append(Chunk(id=f"{path.name}#{len(out)}", doc=title, source=path.name,
                             section=section, text=text, position=len(out)))
    return out


def chunk_directory(kb_dir: Path, **kw) -> list[Chunk]:
    chunks: list[Chunk] = []
    for p in sorted(kb_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            chunks.extend(chunk_document(p, **kw))
    return chunks


def dir_fingerprint(kb_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(kb_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
