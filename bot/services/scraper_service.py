"""
Cella bot - 2026
Scraper service: best-effort extraction of an opportunity's key info
(documents to provide, eligibility, deadline, benefits, how to apply) from
its link. It fetches the page, follows the PDFs and "eligibility"-style links
it finds, then extracts the sections:

    1. with Gemini, when an API key is configured (reads any layout, and
       scanned PDFs too);
    2. otherwise, or if Gemini fails, with the keyword extractor.

It never raises: when nothing can be extracted, the result carries a note
saying why.
Author: Giscard Adjanon
"""

import asyncio
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from pypdf import PdfReader

from bot.services import extractor_service, gemini_service

USER_AGENT = "CellaBot/1.0 (+scholarship tracker for a Discord community)"
REQUEST_TIMEOUT_SECONDS = 15
MIN_MEANINGFUL_TEXT_LENGTH = 200
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_FOLLOWED_LINKS = 3
MAX_PDF_PAGES = 30

_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?([\w-]+)", re.IGNORECASE)

logger = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass
class ScrapedInfo:
    """Result of scraping an opportunity's link."""
    source_url: str
    sections: dict[str, str] = field(default_factory=dict)
    note: Optional[str] = None
    ai_generated: bool = False
    ai_failed: bool = False
    quota_exceeded: bool = False


@dataclass
class Page:
    """One fetched and parsed document (a web page or a PDF)."""
    url: str
    text: str = ""
    pdf: Optional[bytes] = None
    sections: dict[str, str] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    is_scan: bool = False


def _decode_html(content: bytes, header_charset: Optional[str]) -> str:
    charset = header_charset
    if charset is None:
        match = _META_CHARSET.search(content[:4096])
        charset = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


def _pdf_to_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])
    except Exception:
        logger.warning("Scraper: could not read a PDF's text.", exc_info=True)
        return ""


def _parse_content(url: str, content: bytes, content_type: Optional[str], charset: Optional[str]) -> Page:
    """CPU-bound parsing, run in a thread so it never blocks the bot."""
    if urlparse(url).path.lower().endswith(".pdf") or (content_type and "pdf" in content_type):
        text = _pdf_to_text(content)
        if len(text.strip()) < MIN_MEANINGFUL_TEXT_LENGTH:
            return Page(url=url, pdf=content, is_scan=True)
        return Page(url=url, text=text, sections=extractor_service.extract_sections_from_text(text))

    html = _decode_html(content, charset)
    return Page(
        url=url,
        text=extractor_service.html_to_text(html),
        sections=extractor_service.extract_sections_from_html(html),
        links=extractor_service.find_document_links(html, url),
    )


async def _read_limited(response: aiohttp.ClientResponse, limit: int) -> Optional[bytes]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(64 * 1024):
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_page(session: aiohttp.ClientSession, url: str) -> Optional[Page]:
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning("Scraper: %s returned HTTP %d", url, response.status)
                return None
            content = await _read_limited(response, MAX_DOWNLOAD_BYTES)
            if content is None:
                logger.warning("Scraper: %s is larger than %d bytes, skipped.", url, MAX_DOWNLOAD_BYTES)
                return None
            final_url, content_type, charset = str(response.url), response.content_type, response.charset
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        logger.warning("Scraper: failed to reach %s: %s", url, error)
        return None

    return await asyncio.to_thread(_parse_content, final_url, content, content_type, charset)


def _merge_sections(pages: list[Page]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for page in pages:
        for category, content in page.sections.items():
            merged.setdefault(category, content)
    return merged


async def _scrape(
    url: str,
    gemini_api_key: Optional[str],
    gemini_model: Optional[str],
    fallback_to_keywords: bool,
) -> ScrapedInfo:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": USER_AGENT}) as session:
        main = await _fetch_page(session, url)
        if main is None:
            return ScrapedInfo(source_url=url, note="Le lien n'a pas pu être atteint.")

        followed = await asyncio.gather(
            *(_fetch_page(session, link) for link in main.links[:MAX_FOLLOWED_LINKS]),
            return_exceptions=True,
        )

    pages = [main]
    for result in followed:
        if isinstance(result, Page):
            pages.append(result)
        elif isinstance(result, Exception):
            logger.warning("Scraper: a linked page could not be parsed: %s", result)

    sections: dict[str, str] = {}
    ai_generated = False
    if gemini_api_key:
        documents = [gemini_service.Document(name=page.url, text=page.text, pdf=page.pdf) for page in pages]
        try:
            sections = await gemini_service.extract_sections(documents, gemini_api_key, gemini_model) or {}
        except gemini_service.GeminiError as error:
            logger.warning("Scraper: Gemini unavailable for %s: %s", url, error)
            if not fallback_to_keywords:
                return ScrapedInfo(
                    source_url=url,
                    note="L'IA n'a pas pu lire ce lien.",
                    ai_failed=True,
                    quota_exceeded=error.quota,
                )
        ai_generated = bool(sections)
    if not sections:
        sections = _merge_sections(pages)

    note = None
    if not sections:
        if any(page.is_scan for page in pages):
            note = "Le PDF lié semble être un scan (pas de texte extractible automatiquement)."
        else:
            note = "Aucune information clé détectée automatiquement."

    logger.info(
        "Scraper: %s -> %d section(s) via %s from %d page(s).",
        url,
        len(sections),
        "Gemini" if ai_generated else "keywords",
        len(pages),
    )
    return ScrapedInfo(
        source_url=url,
        sections=extractor_service.labelled(sections),
        note=note,
        ai_generated=ai_generated,
    )


async def scrape_opportunity(
    url: str,
    *,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    fallback_to_keywords: bool = True,
) -> ScrapedInfo:
    """
    Best-effort extraction. Never raises - callers can post the result
    (sections, or its fallback note) without worrying about network or
    parsing failures.

    When Gemini is configured but fails, the keyword extractor takes over -
    unless fallback_to_keywords is False, in which case the result is flagged
    ai_failed (and quota_exceeded for a rate limit) with no sections. Callers
    that would rather retry later than post a weaker result use that.
    """
    try:
        return await _scrape(url, gemini_api_key, gemini_model, fallback_to_keywords)
    except Exception:
        logger.exception("Scraper: unexpected error while scraping %s", url)
        return ScrapedInfo(source_url=url, note="Erreur inattendue pendant l'extraction.")
