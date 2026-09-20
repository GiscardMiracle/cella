"""
Cella bot - 2026
Extractor service: pulls the key sections of an opportunity (documents to
provide, eligibility, deadline, benefits, how to apply) out of a page's HTML
or a PDF's plain text, without any AI.

It doesn't depend on any one site's layout. It relies on how pages are
usually written: a heading (or a bold lead-in) that names a section, using
FR/EN keywords, followed by a paragraph or a list. Pure functions, no network.
Author: Giscard Adjanon
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import PreformattedString, Tag

SECTION_LABELS: dict[str, str] = {
    "documents": "Pièces à fournir",
    "eligibility": "Conditions d'éligibilité",
    "deadline": "Date limite",
    "benefits": "Avantages et montant",
    "how_to_apply": "Comment postuler",
}

KEYWORDS: dict[str, list[str]] = {
    "documents": [
        "pièces à fournir",
        "pièces requises",
        "pièces justificatives",
        "pièces du dossier",
        "documents à fournir",
        "documents requis",
        "documents nécessaires",
        "documents demandés",
        "dossier de candidature",
        "constitution du dossier",
        "composition du dossier",
        "required documents",
        "documents required",
        "supporting documents",
        "application documents",
        "documents needed",
        "application materials",
        "required materials",
        "what to submit",
    ],
    "eligibility": [
        "conditions d'éligibilité",
        "critères d'éligibilité",
        "conditions de candidature",
        "conditions requises",
        "conditions d'admission",
        "conditions d'accès",
        "qui peut postuler",
        "qui peut candidater",
        "public cible",
        "profil requis",
        "profil recherché",
        "candidats éligibles",
        "prérequis",
        "pré-requis",
        "eligibility",
        "who can apply",
        "who is eligible",
        "requirements",
        "admission requirements",
        "entry requirements",
    ],
    "deadline": [
        "date limite",
        "date de clôture",
        "clôture des candidatures",
        "délai de soumission",
        "délai de candidature",
        "date limite de dépôt",
        "deadline",
        "closing date",
        "due date",
        "apply by",
        "applications close",
    ],
    "benefits": [
        "montant de la bourse",
        "montant",
        "avantages",
        "prise en charge",
        "la bourse couvre",
        "la bourse comprend",
        "financement",
        "dotation",
        "allocation",
        "benefits",
        "what we offer",
        "what's offered",
        "scholarship covers",
        "funding",
        "stipend",
        "coverage",
    ],
    "how_to_apply": [
        "comment postuler",
        "comment candidater",
        "modalités de candidature",
        "modalités de dépôt",
        "procédure de candidature",
        "dépôt des candidatures",
        "soumission des candidatures",
        "how to apply",
        "application process",
        "application procedure",
        "how to submit",
    ],
}

MAX_FIELD_CHARS = 2000
MAX_SECTION_CHARS = 2000
MAX_SECTION_BLOCKS = 25
MAX_TEXT_BLOCKS = 3
MAX_HEADING_LENGTH = 150
MAX_DEADLINE_BLOCK_LENGTH = 250
MIN_SECTION_CHARS = 3
MAX_PDF_LINKS = 2
MAX_RELATED_LINKS = 2

_DROPPED_TAGS = ["script", "style", "noscript", "nav", "footer", "aside", "svg", "iframe", "select", "template"]
_DROPPED_ROLES = ["navigation", "banner", "contentinfo", "complementary"]
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "summary", "dt", "legend", "caption"})
_BLOCK_TAGS = frozenset(
    {
        "p", "div", "section", "article", "main", "address", "blockquote", "dd", "details",
        "fieldset", "figure", "figcaption", "form", "hr", "ol", "ul", "pre", "table", "thead",
        "tbody", "tfoot", "body", "html", "center",
    }
)

_LINK_KEYWORDS = (
    "eligib", "requirement", "condition", "criteri", "how to apply", "comment postuler",
    "candidature", "documents", "pieces", "procedure", "modalites", "application process",
)
_LINK_BLOCKLIST = ("login", "signin", "sign-in", "register", "account", "logout")

_BULLET = re.compile(r"^(?:[•●▪◦·*\-–—\uf0a7\uf0b7\uf0d8\uf0fc]|\d{1,2}[.)]|[a-zA-Z][.)])\s+")
_INLINE_COLON = re.compile(r"[:：]")


@dataclass(frozen=True)
class Block:
    kind: str  # "heading", "item" (list entry / table row), "link" (an item that is only a link) or "text"
    text: str


def _normalize(text: str) -> str:
    """Lowercase, drop accents and unify apostrophes so keywords match loosely."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    stripped = stripped.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", stripped).lower().strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_KEYWORDS = {category: tuple(_normalize(keyword) for keyword in keywords) for category, keywords in KEYWORDS.items()}


def labelled(sections: dict[str, str]) -> dict[str, str]:
    """Swap machine keys for display labels, in a stable display order."""
    return {SECTION_LABELS[key]: sections[key] for key in SECTION_LABELS if key in sections}


def shorten_text(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    """Cut at a line, sentence or word boundary rather than mid-word."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    boundary = max(cut.rfind("\n"), cut.rfind(". "), cut.rfind("; "))
    if boundary < limit * 0.5:
        boundary = cut.rfind(" ")
    if boundary <= 0:
        boundary = len(cut)
    return cut[:boundary].rstrip(" .;,") + "…"


def _clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROPPED_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": _DROPPED_ROLES}):
        tag.decompose()
    for tag in soup.find_all("header"):
        if tag.find_parent(["article", "main", "section"]) is None:
            tag.decompose()
    return soup


def _blocks_from_html(root: Tag) -> list[Block]:
    blocks: list[Block] = []
    buffer: list[str] = []

    def flush(kind: str = "text") -> None:
        text = _clean(" ".join(buffer))
        buffer.clear()
        if text:
            blocks.append(Block(kind, text))

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, PreformattedString):
                continue
            if not isinstance(child, Tag):
                buffer.append(str(child))
                continue

            name = child.name
            if name == "br":
                flush()
            elif name in _HEADING_TAGS:
                flush()
                text = _clean(child.get_text(" ", strip=True))
                if text:
                    blocks.append(Block("heading", text))
            elif name == "tr":
                flush()
                cells = [_clean(cell.get_text(" ", strip=True)) for cell in child.find_all(["td", "th"])]
                cells = [cell for cell in cells if cell]
                if cells:
                    blocks.append(Block("item", (": " if len(cells) == 2 else " | ").join(cells)))
            elif name == "li":
                flush()
                if child.find(["ul", "ol"]):
                    walk(child)
                    flush("item")
                else:
                    text = _clean(child.get_text(" ", strip=True))
                    link_text = _clean(" ".join(anchor.get_text(" ", strip=True) for anchor in child.find_all("a")))
                    if text:
                        blocks.append(Block("link" if link_text == text else "item", text))
            elif name in _BLOCK_TAGS:
                flush()
                walk(child)
                flush()
            else:
                walk(child)

    walk(root)
    flush()
    return blocks


def _looks_like_heading(line: str) -> bool:
    return len(line) <= 80 and (line.endswith(":") or (line.isupper() and len(line) > 3))


def _continues_previous(previous: Block, line: str) -> bool:
    """PDF text is wrapped line by line: a lowercase start, or a previous line
    that stopped without punctuation, means the sentence carries on."""
    if previous.kind == "item":
        return line[0].islower()
    return line[0].islower() or previous.text[-1] not in ".!?:;"


def _blocks_from_text(text: str) -> list[Block]:
    """Blocks from unstructured text (a PDF's text layer): bullets become
    items, short lines ending with ':' or in capitals become headings, and
    wrapped lines are stitched back into paragraphs."""
    blocks: list[Block] = []
    for raw in text.splitlines():
        line = _clean(raw)
        if not line:
            continue
        bullet = _BULLET.match(line)
        if bullet:
            blocks.append(Block("item", line[bullet.end():]))
        elif _looks_like_heading(line):
            blocks.append(Block("heading", line))
        elif blocks and blocks[-1].kind in ("text", "item") and _continues_previous(blocks[-1], line):
            blocks[-1] = Block(blocks[-1].kind, f"{blocks[-1].text} {line}")
        else:
            blocks.append(Block("text", line))
    return blocks


def _inline_content(text: str, normalized: str, keyword: str) -> str:
    """What follows the keyword on the same line, e.g. 'Documents : CV, lettre'."""
    colon = _INLINE_COLON.search(text[: len(keyword) + 15])
    if colon:
        return text[colon.end():].strip()
    return "" if len(normalized) <= len(keyword) + 3 else text


def _match_category(block: Block) -> Optional[tuple[str, str, bool]]:
    """If the block opens a section, return (category, inline content, complete).
    'complete' means the block is the whole answer (a deadline sentence)."""
    normalized = _normalize(block.text)

    if block.kind == "heading":
        heading = normalized.rstrip(" :.-–—")
        if len(heading) > MAX_HEADING_LENGTH:
            return None
        for category, keywords in _KEYWORDS.items():
            if any(keyword in heading for keyword in keywords):
                after_colon = block.text.split(":", 1)[1].strip() if ":" in block.text else ""
                return category, after_colon, False
        return None

    if (
        len(block.text) <= MAX_DEADLINE_BLOCK_LENGTH
        and re.search(r"\d", block.text)
        and any(keyword in normalized for keyword in _KEYWORDS["deadline"])
    ):
        return "deadline", block.text, True

    for category, keywords in _KEYWORDS.items():
        for keyword in keywords:
            if normalized.startswith(keyword):
                return category, _inline_content(block.text, normalized, keyword), False
    return None


def _render(parts: list[Block]) -> str:
    lines = [f"• {part.text}" if part.kind == "item" else part.text for part in parts]
    return shorten_text("\n".join(lines))


def _collect_section(blocks: list[Block], start: int, inline: str, complete: bool) -> str:
    parts: list[Block] = [Block("text", inline)] if inline else []
    if complete:
        return _render(parts)

    seen_items = False
    text_blocks = len(parts)
    for block in blocks[start + 1:]:
        if block.kind == "link":
            continue
        if block.kind == "heading" or _match_category(block) is not None:
            break
        if block.kind == "item":
            seen_items = True
        elif seen_items or text_blocks >= MAX_TEXT_BLOCKS:
            break
        else:
            text_blocks += 1
        parts.append(block)
        if len(parts) >= MAX_SECTION_BLOCKS or sum(len(part.text) for part in parts) >= MAX_SECTION_CHARS:
            break
    return _render(parts)


def _sections_from_blocks(blocks: list[Block]) -> dict[str, str]:
    found: dict[str, str] = {}
    for index, block in enumerate(blocks):
        match = None if block.kind == "link" else _match_category(block)
        if match is None:
            continue
        category, inline, complete = match
        content = _collect_section(blocks, index, inline, complete)
        if len(content) < MIN_SECTION_CHARS:
            continue
        if category == "deadline":
            found.setdefault(category, content)
        elif category not in found or len(content) > len(found[category]):
            found[category] = content
    return found


def extract_sections_from_html(html: str) -> dict[str, str]:
    """Key sections found in a web page, keyed by category (see SECTION_LABELS)."""
    soup = _clean_soup(html)
    main = soup.find("main")
    scopes = ([main] if main else []) + [soup.body or soup]

    merged: dict[str, str] = {}
    for scope in scopes:
        for category, content in _sections_from_blocks(_blocks_from_html(scope)).items():
            merged.setdefault(category, content)
    return merged


def extract_sections_from_text(text: str) -> dict[str, str]:
    """Key sections found in plain text, e.g. the text layer of a PDF."""
    return _sections_from_blocks(_blocks_from_text(text))


def html_to_text(html: str) -> str:
    """Readable text of a page with its structure kept ('#' headings, '-' list
    items), without menus and footers. This is what gets sent to the AI."""
    soup = _clean_soup(html)
    lines: list[str] = []
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        lines.append(f"# {_clean(title)}")
    for block in _blocks_from_html(soup.body or soup):
        prefix = {"heading": "## ", "item": "- "}.get(block.kind, "")
        lines.append(prefix + block.text)
    return "\n".join(lines)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def find_document_links(html: str, base_url: str) -> list[str]:
    """PDFs linked or embedded in the page, then same-site links that look like
    'eligibility' / 'how to apply' pages. Worth following for more details."""
    soup = BeautifulSoup(html, "html.parser")
    base_without_fragment = base_url.split("#", 1)[0]
    pdfs: list[str] = []
    related: list[str] = []

    for tag in soup.find_all(["a", "embed", "iframe", "object"]):
        href = (tag.get("href") or tag.get("src") or tag.get("data") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or absolute == base_without_fragment:
            continue

        if parsed.path.lower().endswith(".pdf"):
            if absolute not in pdfs:
                pdfs.append(absolute)
        elif tag.name == "a" and _host(absolute) == _host(base_url) and absolute not in related:
            text = _normalize(tag.get_text(" ", strip=True))
            path = parsed.path.lower()
            if (
                0 < len(text) <= 80
                and any(keyword in text for keyword in _LINK_KEYWORDS)
                and not any(blocked in path for blocked in _LINK_BLOCKLIST)
            ):
                related.append(absolute)

    return pdfs[:MAX_PDF_LINKS] + related[:MAX_RELATED_LINKS]
