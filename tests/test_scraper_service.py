"""
Cella bot - 2026
Tests for the pure text-extraction logic in bot.services.scraper_service.
Author: Giscard Adjanon
"""

import unittest

from bot.services.scraper_service import _find_pdf_link, _html_to_text, extract_sections


class ExtractSectionsTests(unittest.TestCase):
    def test_finds_french_keywords(self):
        text = (
            "Bienvenue.\n"
            "Pièces à fournir : copie de la carte d'identité, releve de notes, "
            "lettre de motivation.\n"
            "Conditions d'éligibilité : être âgé de moins de 30 ans."
        )
        sections = extract_sections(text)
        self.assertIn("Pièces à fournir", sections)
        self.assertIn("copie de la carte d'identité", sections["Pièces à fournir"])
        self.assertIn("Conditions d'éligibilité", sections)

    def test_finds_english_keywords(self):
        text = "Required documents: passport copy, transcript, motivation letter."
        sections = extract_sections(text)
        self.assertIn("Pièces à fournir", sections)

    def test_is_case_insensitive(self):
        text = "DATE LIMITE: 15 septembre 2027"
        sections = extract_sections(text)
        self.assertIn("Date limite", sections)

    def test_no_keywords_returns_empty_dict(self):
        self.assertEqual(extract_sections("Juste un texte quelconque sans rapport."), {})

    def test_empty_text_returns_empty_dict(self):
        self.assertEqual(extract_sections(""), {})


class HtmlToTextTests(unittest.TestCase):
    def test_strips_script_and_style_content(self):
        html = "<html><head><style>.a{}</style></head><body><script>evil()</script><p>Bonjour</p></body></html>"
        text = _html_to_text(html)
        self.assertIn("Bonjour", text)
        self.assertNotIn("evil()", text)


class FindPdfLinkTests(unittest.TestCase):
    def test_finds_pdf_from_download_link(self):
        html = '<a href="/uploads/doc.pdf">Télécharger le fichier</a>'
        link = _find_pdf_link(html, "https://example.org/actualite/show/ACT-1")
        self.assertEqual(link, "https://example.org/uploads/doc.pdf")

    def test_finds_pdf_from_embed_tag(self):
        html = '<embed src="/uploads/doc.pdf" type="application/pdf">'
        link = _find_pdf_link(html, "https://example.org/actualite/show/ACT-1")
        self.assertEqual(link, "https://example.org/uploads/doc.pdf")

    def test_returns_none_when_no_pdf_present(self):
        html = "<p>Aucun document ici.</p>"
        self.assertIsNone(_find_pdf_link(html, "https://example.org"))


if __name__ == "__main__":
    unittest.main()
