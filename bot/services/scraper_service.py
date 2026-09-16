"""
Cella bot - 2026
Scraper service: best-effort extraction of key info (required documents,
eligibility, deadline mentions) from an opportunity's link.

Sites have no common structure, so this doesn't try to parse layout - it
scans the page's plain text for FR/EN keywords that tend to introduce the
sections we care about, and grabs the text right after them. When the link
is a PDF with no extractable text (a scan, most commonly), or nothing
useful was found, it reports that instead of failing.
Author: Giscard Adjanon
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from pypdf import PdfReader

USER_AGENT = "CellaBot/1.0 (+scholarship tracker for a Discord community)"
REQUEST_TIMEOUT_SECONDS = 15
MIN_MEANINGFUL_TEXT_LENGTH = 200
SECTION_CAPTURE_LENGTH = 500

logger = logging.getLogger(__name__)

KEYWORDS: dict[str, list[str]] = {
    "Pièces à fournir": [
        "pièces à fournir",
        "pieces a fournir",
        "pièces requises",
        "documents à fournir",
        "documents requis",
        "dossier de candidature",
        "constitution du dossier",
        "required documents",
        "documents required",
        "application requirements",
        "how to apply",
    ],
    "Conditions d'éligibilité": [
        "conditions d'éligibilité",
        "conditions d'eligibilite",
        "critères d'éligibilité",
        "conditions de candidature",
        "qui peut postuler",
        "public cible",
        "eligibility criteria",
        "eligibility requirements",
        "who can apply",
    ],
    "Date limite": [
        "date limite",
        "date de clôture",
        "date de cloture",
        "délai de soumission",
        "deadline",
        "closing date",
        "due date",
    ],
}


@dataclass
class ScrapedInfo:
    """Result of scraping an opportunity's link."""
    source_url: str
    sections: dict[str, str] = field(default_factory=dict)
    note: Optional[str] = None  # explains a degraded or empty result


def extract_sections(text: str) -> dict[str, str]:
    """Pull out keyword-anchored excerpts from free text. Pure function."""
    if not text:
        return {}

    lowered = text.lower()
    sections: dict[str, str] = {}

    for label, keywords in KEYWORDS.items():
        for keyword in keywords:
            index = lowered.find(keyword)
            if index == -1:
                continue
            sections[label] = text[index : index + SECTION_CAPTURE_LENGTH].strip()
            break  # first matching keyword for this label is enough

    return sections


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _find_pdf_link(html: str, base_url: str) -> Optional[str]:
    """Some sites (e.g. government notices) only embed the real content as
    a linked/embedded PDF, with the surrounding page left mostly empty."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["a", "embed"]):
        src = tag.get("href") or tag.get("src")
        if src and src.lower().endswith(".pdf"):
            return urljoin(base_url, src)
    return None


def _pdf_to_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def _fetch(
    session: aiohttp.ClientSession, url: str
) -> tuple[Optional[bytes], Optional[str]]:
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning("Scraper: %s returned HTTP %d", url, response.status)
                return None, None
            return await response.read(), response.content_type
    except aiohttp.ClientError as error:
        logger.warning("Scraper: failed to reach %s: %s", url, error)
        return None, None


async def _fetch_and_extract_text(url: str) -> tuple[str, Optional[str], Optional[str]]:
    """
    Fetch a URL and extract its plain text.
    Returns (text, pdf_link_found_on_page, note) - pdf_link_found_on_page is
    only ever set for an HTML page, so callers can follow it as a fallback;
    note is set when extraction was degraded or failed outright.
    """
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    headers = {"User-Agent": USER_AGENT}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        content, content_type = await _fetch(session, url)
        if content is None:
            return "", None, "Le lien n'a pas pu être atteint."

        is_pdf = url.lower().endswith(".pdf") or (content_type and "pdf" in content_type)
        if is_pdf:
            text = _pdf_to_text(content)
            if len(text.strip()) < MIN_MEANINGFUL_TEXT_LENGTH:
                return "", None, "Le PDF lié semble être un scan (pas de texte extractible automatiquement)."
            return text, None, None

        html = content.decode("utf-8", errors="ignore")
        return _html_to_text(html), _find_pdf_link(html, url), None


async def scrape_opportunity(url: str) -> ScrapedInfo:
    """
    Best-effort extraction. Never raises - callers can post the result
    (sections, or its fallback note) without worrying about network or
    parsing failures.

    Many sites (government notices especially) leave the HTML page itself
    almost empty and put the real content in a linked/embedded PDF - so
    when the page's own text yields nothing, a PDF link found on it is
    tried too before giving up.
    """
    try:
        text, pdf_link, note = await _fetch_and_extract_text(url)
    except Exception:
        logger.exception("Scraper: unexpected error while scraping %s", url)
        return ScrapedInfo(source_url=url, note="Erreur inattendue pendant l'extraction.")

    sections = extract_sections(text)

    if not sections and pdf_link:
        try:
            pdf_text, _, pdf_note = await _fetch_and_extract_text(pdf_link)
        except Exception:
            logger.exception("Scraper: unexpected error while scraping linked PDF %s", pdf_link)
            pdf_text, pdf_note = "", "Erreur inattendue pendant l'extraction du PDF."

        pdf_sections = extract_sections(pdf_text)
        if pdf_sections:
            sections, note = pdf_sections, None
        elif pdf_note:
            note = pdf_note

    if not sections and note is None:
        note = "Aucune information clé détectée automatiquement."

    if note:
        logger.info("Scraper: %s -> %s", url, note)

    return ScrapedInfo(source_url=url, sections=sections, note=note)
