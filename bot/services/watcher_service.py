"""
Cella bot - 2026
Watcher service: checks the ministry's scholarship listing page for new
announcements against what Cella has already seen.
Author: Giscard Adjanon
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from bot.database import queries
from bot.database.models import Announcement

BASE_URL = "https://enseignementsuperieur.gouv.bj"
USER_AGENT = "CellaBot/1.0 (+scholarship tracker for a Discord community)"
REQUEST_TIMEOUT_SECONDS = 15


def _parse_listing_date(date_text: Optional[str]) -> Optional[datetime]:
    """Parse the dd/mm/yyyy date shown next to each listing item."""
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text.strip(), "%d/%m/%Y")
    except ValueError:
        return None


def parse_listing_html(html: str, base_url: str = BASE_URL) -> list[Announcement]:
    """Extract announcements from a listing page. Pure function, no network."""
    soup = BeautifulSoup(html, "html.parser")
    seen_ids: set[str] = set()
    announcements: list[Announcement] = []

    for link_tag in soup.select("h6 a[href]"):
        href = link_tag.get("href", "")
        match = re.search(r"actualite/show/([A-Za-z0-9-]+)", href)
        if not match:
            continue

        announcement_id = match.group(1)
        if announcement_id in seen_ids:
            continue
        seen_ids.add(announcement_id)

        card = link_tag.find_parent("div", class_="card")
        date_tag = card.find("small") if card else None
        date_text = date_tag.get_text(strip=True) if date_tag else None

        announcements.append(
            Announcement(
                id=announcement_id,
                title=link_tag.get_text(strip=True),
                link=urljoin(base_url, href),
                published_at=_parse_listing_date(date_text),
                discovered_at=datetime.now(),
            )
        )

    return announcements


async def _fetch_listing_html(url: str) -> Optional[str]:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    headers = {"User-Agent": USER_AGENT}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                return await response.text()
    except aiohttp.ClientError:
        return None


async def get_new_announcements(watch_url: str) -> list[Announcement]:
    """
    Fetch the listing page and return announcements not seen before.

    On the very first run (empty table), the page's current content is
    treated as the baseline state (I0): it gets recorded as "seen" but
    nothing is reported as new, since it isn't - it's just what already
    existed before Cella started watching.
    """
    html = await _fetch_listing_html(watch_url)
    if html is None:
        return []

    fetched = parse_listing_html(html)
    if not fetched:
        return []

    is_first_run = queries.count_watched_announcements() == 0
    if is_first_run:
        queries.save_watched_announcements(fetched)
        return []

    known_ids = queries.get_watched_announcement_ids()
    new_announcements = [a for a in fetched if a.id not in known_ids]
    queries.save_watched_announcements(new_announcements)
    return new_announcements
