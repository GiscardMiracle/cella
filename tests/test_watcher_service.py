"""
Cella bot - 2026
Tests for the pure parsing logic in bot.services.watcher_service.
Author: Giscard Adjanon
"""

import unittest
from datetime import datetime

from bot.services.watcher_service import BASE_URL, parse_listing_html

LISTING_HTML = """
<div class="row justify-content-md-center">
    <div class="mb-3 col-sm-12 col-md-4 col-lg-3">
        <div class="card me-1 ms-1 shadow-sm">
            <a href="/actualite/show/ACT-j9eDxIXb-9B54FE4">
                <div class="actualite-img"></div>
            </a>
            <div>
                <p><small class="text-secondary w-25">14/09/2026</small></p>
                <span class="badge bg-success">Communiqué</span>
            </div>
            <h6>
                <a class="text-decoration-none" href="/actualite/show/ACT-j9eDxIXb-9B54FE4">
                    Bourse de coopération Algérienne - Master professionnel 2026-2027
                </a>
            </h6>
            <a href="/actualite/show/ACT-j9eDxIXb-9B54FE4" class="actualite-btn btn w-75 btn-sm text-uppercase">
                voir le contenu
            </a>
        </div>
    </div>
    <div class="mb-3 col-sm-12 col-md-4 col-lg-3">
        <div class="card me-1 ms-1 shadow-sm">
            <a href="/actualite/show/ACT-WPdXS2di-1C4746A"></a>
            <div>
                <p><small class="text-secondary w-25">04/06/2026</small></p>
                <span class="badge bg-success">Communiqué</span>
            </div>
            <h6>
                <a class="text-decoration-none" href="/actualite/show/ACT-WPdXS2di-1C4746A">
                    Bourse marocaine (Formations Universitaires) 2026-2027
                </a>
            </h6>
        </div>
    </div>
</div>
"""


class ParseListingHtmlTests(unittest.TestCase):
    def test_extracts_one_announcement_per_card(self):
        announcements = parse_listing_html(LISTING_HTML)
        self.assertEqual(len(announcements), 2)

    def test_deduplicates_repeated_links_within_a_card(self):
        # The site links to the same article twice (image + "voir le contenu"
        # button) besides the h6 title link; only the h6 one is selected,
        # so no duplicate id should appear.
        announcements = parse_listing_html(LISTING_HTML)
        ids = [a.id for a in announcements]
        self.assertEqual(len(ids), len(set(ids)))

    def test_extracts_id_title_link_and_date(self):
        announcements = parse_listing_html(LISTING_HTML)
        first = announcements[0]
        self.assertEqual(first.id, "ACT-j9eDxIXb-9B54FE4")
        self.assertIn("Bourse de coopération Algérienne", first.title)
        self.assertEqual(first.link, f"{BASE_URL}/actualite/show/ACT-j9eDxIXb-9B54FE4")
        self.assertEqual(first.published_at, datetime(2026, 9, 14))

    def test_missing_date_is_none_not_a_crash(self):
        html = """
        <div class="card">
            <h6><a href="/actualite/show/ACT-noDate-1">No date item</a></h6>
        </div>
        """
        announcements = parse_listing_html(html)
        self.assertEqual(len(announcements), 1)
        self.assertIsNone(announcements[0].published_at)

    def test_empty_page_returns_empty_list(self):
        self.assertEqual(parse_listing_html("<html><body>Rien ici</body></html>"), [])


if __name__ == "__main__":
    unittest.main()
