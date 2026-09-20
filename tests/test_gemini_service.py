"""
Cella bot - 2026
Tests for bot.services.gemini_service, against a fake server that follows the
documented Interactions API contract (no API key, no network).
Author: Giscard Adjanon
"""

import base64
import json
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.services import gemini_service
from bot.services.gemini_service import Document, GeminiError, extract_sections

ANSWER = {
    "documents": ["Copie du passeport", "Relevé de notes", "Copie du passeport"],
    "eligibility": ["Être inscrit en Master"],
    "deadline": "15 octobre 2027",
    "benefits": [],
    "how_to_apply": ["Déposer le dossier en ligne"],
}


def interaction(answer, status="completed"):
    return {
        "status": status,
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "ignored"}]},
            {"type": "model_output", "content": [{"type": "text", "text": json.dumps(answer)}]},
        ],
    }


class GeminiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.reply = (200, interaction(ANSWER))

        async def handler(request):
            self.requests.append({"headers": request.headers, "body": await request.json()})
            status, body = self.reply
            if isinstance(body, str):
                return web.Response(status=status, text=body)
            return web.json_response(body, status=status)

        app = web.Application()
        app.router.add_post("/v1beta/interactions", handler)
        self.server = TestServer(app)
        await self.server.start_server()
        patcher = patch.object(gemini_service, "GEMINI_API_URL", str(self.server.make_url("/v1beta/interactions")))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.server.close()

    async def test_returns_sections_from_the_structured_answer(self):
        sections = await extract_sections([Document("page", text="Bourse")], "secret-key")

        self.assertEqual(sections["documents"], "• Copie du passeport\n• Relevé de notes")
        self.assertEqual(sections["eligibility"], "• Être inscrit en Master")
        self.assertEqual(sections["deadline"], "15 octobre 2027")
        self.assertEqual(sections["how_to_apply"], "• Déposer le dossier en ligne")
        self.assertNotIn("benefits", sections)

    async def test_request_follows_the_interactions_contract(self):
        await extract_sections([Document("https://example.org/a", text="Contenu de la page")], "secret-key", "my-model")

        request = self.requests[0]
        body = request["body"]
        self.assertEqual(request["headers"]["x-goog-api-key"], "secret-key")
        self.assertEqual(body["model"], "my-model")
        self.assertIs(body["store"], False)
        self.assertIn("n'invente rien", body["system_instruction"])
        self.assertEqual(body["response_format"]["mime_type"], "application/json")
        self.assertEqual(
            set(body["response_format"]["schema"]["required"]),
            {"documents", "eligibility", "deadline", "benefits", "how_to_apply"},
        )
        self.assertEqual(body["input"][0]["type"], "text")
        self.assertIn("Contenu de la page", body["input"][0]["text"])
        self.assertIn("https://example.org/a", body["input"][0]["text"])

    async def test_uses_the_default_model_when_none_is_given(self):
        await extract_sections([Document("page", text="x")], "key")
        self.assertEqual(self.requests[0]["body"]["model"], gemini_service.DEFAULT_MODEL)

    async def test_api_key_is_never_part_of_the_body(self):
        await extract_sections([Document("page", text="x")], "secret-key")
        self.assertNotIn("secret-key", json.dumps(self.requests[0]["body"]))

    async def test_scanned_pdf_is_sent_as_a_document_part(self):
        pdf = b"%PDF-1.4 fake scan"
        await extract_sections([Document("https://example.org/scan.pdf", pdf=pdf)], "key")

        parts = self.requests[0]["body"]["input"]
        document = next(part for part in parts if part["type"] == "document")
        self.assertEqual(document["mime_type"], "application/pdf")
        self.assertEqual(base64.b64decode(document["data"]), pdf)

    async def test_oversized_pdf_is_skipped_and_nothing_is_sent(self):
        with patch.object(gemini_service, "MAX_PDF_BYTES", 5):
            result = await extract_sections([Document("big.pdf", pdf=b"0123456789")], "key")

        self.assertIsNone(result)
        self.assertEqual(self.requests, [])

    async def test_long_page_text_is_capped(self):
        with patch.object(gemini_service, "MAX_TEXT_CHARS_PER_DOCUMENT", 50):
            await extract_sections([Document("page", text="a" * 500)], "key")

        self.assertLess(len(self.requests[0]["body"]["input"][0]["text"]), 120)

    async def test_no_documents_means_no_request(self):
        self.assertIsNone(await extract_sections([], "key"))
        self.assertIsNone(await extract_sections([Document("page")], "key"))
        self.assertEqual(self.requests, [])

    async def test_rate_limit_raises_a_quota_error_with_the_reason(self):
        self.reply = (429, {"error": {"code": "429", "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
        with self.assertRaises(GeminiError) as raised:
            await extract_sections([Document("page", text="x")], "key")
        self.assertTrue(raised.exception.quota)
        self.assertIn("429", str(raised.exception))
        self.assertIn("quota exceeded", str(raised.exception))

    async def test_resource_exhausted_is_a_quota_error_whatever_the_http_status(self):
        self.reply = (503, {"error": {"message": "limit", "status": "RESOURCE_EXHAUSTED"}})
        with self.assertRaises(GeminiError) as raised:
            await extract_sections([Document("page", text="x")], "key")
        self.assertTrue(raised.exception.quota)

    async def test_other_http_errors_are_not_quota_errors(self):
        self.reply = (400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}})
        with self.assertRaises(GeminiError) as raised:
            await extract_sections([Document("page", text="x")], "key")
        self.assertFalse(raised.exception.quota)
        self.assertIn("API key not valid", str(raised.exception))

    async def test_server_error_with_a_non_json_body_raises(self):
        self.reply = (502, "<html>Bad gateway</html>")
        with self.assertRaises(GeminiError) as raised:
            await extract_sections([Document("page", text="x")], "key")
        self.assertIn("HTTP 502", str(raised.exception))
        self.assertFalse(raised.exception.quota)

    async def test_success_status_with_a_non_json_body_raises(self):
        self.reply = (200, "<html>Maintenance</html>")
        with self.assertRaises(GeminiError):
            await extract_sections([Document("page", text="x")], "key")

    async def test_unfinished_interaction_raises(self):
        self.reply = (200, interaction(ANSWER, status="failed"))
        with self.assertRaises(GeminiError) as raised:
            await extract_sections([Document("page", text="x")], "key")
        self.assertIn("failed", str(raised.exception))

    async def test_answer_that_is_not_json_raises(self):
        body = interaction(ANSWER)
        body["steps"][1]["content"][0]["text"] = "Voici les infos : ..."
        self.reply = (200, body)
        with self.assertRaises(GeminiError):
            await extract_sections([Document("page", text="x")], "key")

    async def test_answer_with_no_model_output_raises(self):
        self.reply = (200, {"status": "completed", "steps": []})
        with self.assertRaises(GeminiError):
            await extract_sections([Document("page", text="x")], "key")

    async def test_falls_back_to_the_candidates_response_shape(self):
        self.reply = (200, {"candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}]}}]})
        sections = await extract_sections([Document("page", text="x")], "key")
        self.assertEqual(sections["deadline"], "15 octobre 2027")

    async def test_an_answer_with_nothing_found_gives_an_empty_result_not_none(self):
        empty = {"documents": [], "eligibility": [], "deadline": "", "benefits": [], "how_to_apply": []}
        self.reply = (200, interaction(empty))
        self.assertEqual(await extract_sections([Document("page", text="x")], "key"), {})

    async def test_wrongly_typed_fields_are_ignored(self):
        odd = {"documents": "pas une liste", "eligibility": [1, None, "OK"], "deadline": ["x"], "benefits": {}}
        self.reply = (200, interaction(odd))
        self.assertEqual(
            await extract_sections([Document("page", text="x")], "key"), {"eligibility": "• OK"}
        )

    async def test_lists_are_capped(self):
        many = {"documents": [f"pièce {n}" for n in range(50)]}
        self.reply = (200, interaction(many))
        sections = await extract_sections([Document("page", text="x")], "key")
        self.assertEqual(len(sections["documents"].splitlines()), gemini_service.MAX_ITEMS)


class UnreachableServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_error_raises_a_non_quota_error(self):
        with patch.object(gemini_service, "GEMINI_API_URL", "http://127.0.0.1:9/v1beta/interactions"):
            with self.assertRaises(GeminiError) as raised:
                await extract_sections([Document("page", text="x")], "key")
        self.assertFalse(raised.exception.quota)


if __name__ == "__main__":
    unittest.main()
