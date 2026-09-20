"""
Cella bot - 2026
Tests for the fetch-and-extract flow in bot.services.scraper_service, against
a local fake site and a fake Gemini API.
Author: Giscard Adjanon
"""

import io
import json
import logging
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer
from pypdf import PdfWriter

from bot.services import gemini_service
from bot.services.scraper_service import _decode_html, scrape_opportunity

MAIN_PAGE = """
<html><head><title>Bourse test</title></head><body>
<nav><a href="/apply">How to apply</a></nav>
<main>
  <h1>Bourse d'excellence</h1>
  <h2>Conditions d'éligibilité</h2>
  <ul><li>Être inscrit en Master</li><li>Avoir moins de 28 ans</li></ul>
  <h2>Pièces à fournir</h2>
  <ul><li>Copie de la CNI</li><li>Relevé de notes</li></ul>
  <p>Date limite : 30 novembre 2027</p>
  <a href="/details">Eligibility criteria</a>
</main></body></html>
"""

DETAILS_PAGE = """
<html><body><main>
  <h2>Comment postuler</h2>
  <ul><li>Créer un compte sur la plateforme</li><li>Déposer le dossier complet</li></ul>
</main></body></html>
"""

PDF_ONLY_PAGE = '<html><body><main><p>Voir le communiqué.</p><a href="/scan.pdf">Télécharger</a></main></body></html>'


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def gemini_answer(answer: dict) -> dict:
    return {
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(answer)}]}],
    }


class ScrapeOpportunityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.getLogger("bot.services").setLevel(logging.ERROR)
        self.addCleanup(logging.getLogger("bot.services").setLevel, logging.NOTSET)

        self.hits = []
        self.gemini_requests = []
        self.gemini_reply = (200, gemini_answer({"documents": ["Passeport"], "deadline": "1er décembre 2027"}))
        self.pdf = blank_pdf()

        async def page(request):
            self.hits.append(request.path)
            return web.Response(text=MAIN_PAGE, content_type="text/html")

        async def details(request):
            self.hits.append(request.path)
            return web.Response(text=DETAILS_PAGE, content_type="text/html")

        async def pdf_only(request):
            self.hits.append(request.path)
            return web.Response(text=PDF_ONLY_PAGE, content_type="text/html")

        async def scan(request):
            self.hits.append(request.path)
            return web.Response(body=self.pdf, content_type="application/pdf")

        async def missing(request):
            return web.Response(status=404)

        async def latin1(request):
            body = "<html><body><h2>Conditions d'éligibilité</h2><p>Être étudiant à l'étranger</p></body></html>"
            return web.Response(body=body.encode("latin-1"), headers={"Content-Type": "text/html; charset=ISO-8859-1"})

        async def gemini(request):
            self.gemini_requests.append({"headers": request.headers, "body": await request.json()})
            status, body = self.gemini_reply
            return web.json_response(body, status=status)

        app = web.Application()
        app.router.add_get("/bourse", page)
        app.router.add_get("/details", details)
        app.router.add_get("/pdf-only", pdf_only)
        app.router.add_get("/scan.pdf", scan)
        app.router.add_get("/missing", missing)
        app.router.add_get("/latin1", latin1)
        app.router.add_post("/v1beta/interactions", gemini)
        self.server = TestServer(app)
        await self.server.start_server()

        patcher = patch.object(gemini_service, "GEMINI_API_URL", str(self.server.make_url("/v1beta/interactions")))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.server.close()

    def url(self, path: str) -> str:
        return str(self.server.make_url(path))

    async def test_extracts_labelled_sections_without_ai(self):
        info = await scrape_opportunity(self.url("/bourse"))

        self.assertFalse(info.ai_generated)
        self.assertIsNone(info.note)
        self.assertEqual(info.sections["Conditions d'éligibilité"], "• Être inscrit en Master\n• Avoir moins de 28 ans")
        self.assertEqual(info.sections["Pièces à fournir"], "• Copie de la CNI\n• Relevé de notes")
        self.assertIn("30 novembre 2027", info.sections["Date limite"])
        self.assertEqual(self.gemini_requests, [])

    async def test_follows_related_pages_and_merges_what_they_add(self):
        info = await scrape_opportunity(self.url("/bourse"))

        self.assertIn("/details", self.hits)
        self.assertEqual(
            info.sections["Comment postuler"], "• Créer un compte sur la plateforme\n• Déposer le dossier complet"
        )

    async def test_the_main_page_wins_over_followed_pages(self):
        info = await scrape_opportunity(self.url("/bourse"))
        self.assertIn("Copie de la CNI", info.sections["Pièces à fournir"])

    async def test_sections_come_out_in_display_order(self):
        info = await scrape_opportunity(self.url("/bourse"))
        self.assertEqual(
            list(info.sections),
            ["Pièces à fournir", "Conditions d'éligibilité", "Date limite", "Comment postuler"],
        )

    async def test_gemini_answer_replaces_the_keyword_extraction(self):
        info = await scrape_opportunity(self.url("/bourse"), gemini_api_key="key", gemini_model="m")

        self.assertTrue(info.ai_generated)
        self.assertEqual(info.sections, {"Pièces à fournir": "• Passeport", "Date limite": "1er décembre 2027"})
        request = self.gemini_requests[0]
        self.assertEqual(request["headers"]["x-goog-api-key"], "key")
        self.assertEqual(request["body"]["model"], "m")
        sent = json.dumps(request["body"]["input"], ensure_ascii=False)
        self.assertIn("Être inscrit en Master", sent)
        self.assertIn("Créer un compte sur la plateforme", sent)
        self.assertNotIn("How to apply", sent)

    async def test_falls_back_to_keywords_when_gemini_fails(self):
        self.gemini_reply = (429, {"error": {"message": "quota"}})

        info = await scrape_opportunity(self.url("/bourse"), gemini_api_key="key")

        self.assertFalse(info.ai_generated)
        self.assertIn("Conditions d'éligibilité", info.sections)

    async def test_without_fallback_a_gemini_failure_yields_no_sections(self):
        self.gemini_reply = (500, {"error": {"message": "boom"}})

        info = await scrape_opportunity(self.url("/bourse"), gemini_api_key="key", fallback_to_keywords=False)

        self.assertEqual(info.sections, {})
        self.assertTrue(info.ai_failed)
        self.assertFalse(info.quota_exceeded)

    async def test_without_fallback_a_rate_limit_is_reported_as_quota(self):
        self.gemini_reply = (429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})

        info = await scrape_opportunity(self.url("/bourse"), gemini_api_key="key", fallback_to_keywords=False)

        self.assertTrue(info.ai_failed)
        self.assertTrue(info.quota_exceeded)

    async def test_without_fallback_and_without_a_key_keywords_still_apply(self):
        info = await scrape_opportunity(self.url("/bourse"), fallback_to_keywords=False)

        self.assertFalse(info.ai_failed)
        self.assertIn("Pièces à fournir", info.sections)

    async def test_falls_back_to_keywords_when_gemini_finds_nothing(self):
        self.gemini_reply = (200, gemini_answer({"documents": [], "deadline": ""}))

        info = await scrape_opportunity(self.url("/bourse"), gemini_api_key="key")

        self.assertFalse(info.ai_generated)
        self.assertIn("Pièces à fournir", info.sections)

    async def test_scanned_pdf_without_ai_explains_why(self):
        info = await scrape_opportunity(self.url("/pdf-only"))

        self.assertIn("/scan.pdf", self.hits)
        self.assertEqual(info.sections, {})
        self.assertIn("scan", info.note)

    async def test_scanned_pdf_is_handed_to_gemini(self):
        info = await scrape_opportunity(self.url("/pdf-only"), gemini_api_key="key")

        self.assertTrue(info.ai_generated)
        parts = self.gemini_requests[0]["body"]["input"]
        self.assertIn("document", [part["type"] for part in parts])

    async def test_unreachable_link(self):
        info = await scrape_opportunity(self.url("/missing"))
        self.assertEqual(info.sections, {})
        self.assertEqual(info.note, "Le lien n'a pas pu être atteint.")

    async def test_unreachable_link_never_calls_gemini(self):
        await scrape_opportunity(self.url("/missing"), gemini_api_key="key")
        self.assertEqual(self.gemini_requests, [])

    async def test_page_declaring_a_legacy_charset_is_decoded_correctly(self):
        info = await scrape_opportunity(self.url("/latin1"))
        self.assertEqual(info.sections["Conditions d'éligibilité"], "Être étudiant à l'étranger")

    async def test_never_raises_on_a_bad_url(self):
        info = await scrape_opportunity("not a url")
        self.assertEqual(info.sections, {})
        self.assertIsNotNone(info.note)


class DecodeHtmlTests(unittest.TestCase):
    def test_uses_the_declared_header_charset(self):
        self.assertEqual(_decode_html("é".encode("latin-1"), "ISO-8859-1"), "é")

    def test_falls_back_to_the_meta_charset(self):
        html = '<meta charset="iso-8859-1"><p>é</p>'.encode("latin-1")
        self.assertIn("é", _decode_html(html, None))

    def test_defaults_to_utf8_and_survives_unknown_charsets(self):
        self.assertEqual(_decode_html("é".encode("utf-8"), None), "é")
        self.assertEqual(_decode_html("é".encode("utf-8"), "no-such-charset"), "é")


if __name__ == "__main__":
    unittest.main()
