"""
Cella bot - 2026
Tests for the keyword/structure extractor in bot.services.extractor_service.
Author: Giscard Adjanon
"""

import unittest

from bot.services.extractor_service import (
    extract_sections_from_html,
    extract_sections_from_text,
    find_document_links,
    html_to_text,
    labelled,
    shorten_text,
)

FRENCH_PAGE = """
<html><head><title>Bourse d'excellence</title></head><body>
<header><a href="/">Accueil</a></header>
<nav><ul><li><a href="/x">Comment postuler</a></li><li><a href="/y">Contact</a></li></ul></nav>
<main>
  <h1>Bourse d'excellence 2027</h1>
  <h2>Conditions d'éligibilité</h2>
  <ul><li>Être inscrit en Master</li><li>Avoir moins de 28 ans</li></ul>
  <h2>Pièces à fournir</h2>
  <ul><li>Copie de la CNI</li><li>Relevé de notes</li><li>Lettre de motivation</li></ul>
  <p>Date limite : 30 novembre 2027</p>
</main>
<footer>Mentions légales</footer>
</body></html>
"""


class HtmlSectionsTests(unittest.TestCase):
    def test_reads_headings_followed_by_lists(self):
        sections = extract_sections_from_html(FRENCH_PAGE)
        self.assertEqual(sections["eligibility"], "• Être inscrit en Master\n• Avoir moins de 28 ans")
        self.assertEqual(
            sections["documents"], "• Copie de la CNI\n• Relevé de notes\n• Lettre de motivation"
        )

    def test_reads_a_deadline_sentence(self):
        self.assertIn("30 novembre 2027", extract_sections_from_html(FRENCH_PAGE)["deadline"])

    def test_ignores_menus_and_footers(self):
        sections = extract_sections_from_html(FRENCH_PAGE)
        self.assertNotIn("how_to_apply", sections)
        self.assertNotIn("Mentions légales", " ".join(sections.values()))

    def test_bold_lead_in_with_inline_content(self):
        html = "<body><p><strong>Documents requis :</strong> CV, lettre de motivation, diplômes</p></body>"
        self.assertEqual(
            extract_sections_from_html(html)["documents"], "CV, lettre de motivation, diplômes"
        )

    def test_lead_in_on_its_own_line_takes_the_following_list(self):
        html = "<body><p><b>Required documents</b></p><ul><li>Passport</li><li>Transcript</li></ul></body>"
        self.assertEqual(extract_sections_from_html(html)["documents"], "• Passport\n• Transcript")

    def test_table_rows_become_label_value_pairs(self):
        html = "<body><table><tr><th>Application deadline</th><td>15 October 2026</td></tr></table></body>"
        self.assertIn("15 October 2026", extract_sections_from_html(html)["deadline"])

    def test_matches_without_accents_and_with_curly_apostrophes(self):
        html = "<body><h2>Conditions d’eligibilite</h2><p>Etre majeur</p></body>"
        self.assertEqual(extract_sections_from_html(html)["eligibility"], "Etre majeur")

    def test_english_headings(self):
        html = "<body><h3>Who can apply?</h3><ul><li>Citizens of Benin</li></ul></body>"
        self.assertEqual(extract_sections_from_html(html)["eligibility"], "• Citizens of Benin")

    def test_a_section_stops_at_the_next_heading(self):
        html = "<body><h2>Eligibility</h2><p>Be a student</p><h2>Contact us</h2><p>Call us</p></body>"
        self.assertEqual(extract_sections_from_html(html)["eligibility"], "Be a student")

    def test_lists_made_only_of_links_are_not_content(self):
        html = (
            "<body><h2>How to apply</h2><ul><li><a href='/a'>Advice</a></li>"
            "<li><a href='/b'>FAQs</a></li></ul></body>"
        )
        self.assertNotIn("how_to_apply", extract_sections_from_html(html))

    def test_keeps_the_fullest_of_several_matches(self):
        html = (
            "<body><p>Requirements: see below</p>"
            "<h2>Requirements</h2><ul><li>Bachelor's degree</li><li>Two references</li></ul></body>"
        )
        self.assertEqual(
            extract_sections_from_html(html)["eligibility"], "• Bachelor's degree\n• Two references"
        )

    def test_page_without_anything_relevant(self):
        self.assertEqual(extract_sections_from_html("<body><p>Bonjour</p></body>"), {})

    def test_empty_input(self):
        self.assertEqual(extract_sections_from_html(""), {})


class TextSectionsTests(unittest.TestCase):
    PDF_TEXT = (
        "COMMUNIQUE\n"
        "Pièces à fournir :\n"
        "- Une copie de la carte\n"
        "d'identité en cours de validité\n"
        "- Un relevé de notes\n"
        "Conditions d'éligibilité :\n"
        "Le candidat doit être de nationalité\n"
        "béninoise et âgé de moins de 30 ans.\n"
        "Date limite de dépôt : 15 septembre 2027\n"
    )

    def test_bullets_and_wrapped_lines(self):
        sections = extract_sections_from_text(self.PDF_TEXT)
        self.assertEqual(
            sections["documents"],
            "• Une copie de la carte d'identité en cours de validité\n• Un relevé de notes",
        )

    def test_paragraphs_are_stitched_back_together(self):
        sections = extract_sections_from_text(self.PDF_TEXT)
        self.assertEqual(
            sections["eligibility"],
            "Le candidat doit être de nationalité béninoise et âgé de moins de 30 ans.",
        )

    def test_deadline_line(self):
        self.assertIn("15 septembre 2027", extract_sections_from_text(self.PDF_TEXT)["deadline"])

    def test_empty_text(self):
        self.assertEqual(extract_sections_from_text(""), {})


class HtmlToTextTests(unittest.TestCase):
    def test_keeps_structure_and_drops_chrome(self):
        text = html_to_text(FRENCH_PAGE)
        self.assertIn("# Bourse d'excellence", text)
        self.assertIn("## Conditions d'éligibilité", text)
        self.assertIn("- Être inscrit en Master", text)
        self.assertNotIn("Mentions légales", text)
        self.assertNotIn("Contact", text)

    def test_strips_scripts_and_styles(self):
        html = "<body><script>evil()</script><style>.a{}</style><p>Bonjour</p></body>"
        self.assertEqual(html_to_text(html), "Bonjour")


class FindDocumentLinksTests(unittest.TestCase):
    BASE = "https://example.org/bourses/daad"

    def test_pdfs_come_first_then_related_pages(self):
        html = (
            '<a href="/bourses/daad/eligibility">Eligibility criteria</a>'
            '<embed src="/files/call.pdf"><a href="guide.PDF">Guide</a>'
        )
        self.assertEqual(
            find_document_links(html, self.BASE),
            [
                "https://example.org/files/call.pdf",
                "https://example.org/bourses/guide.PDF",
                "https://example.org/bourses/daad/eligibility",
            ],
        )

    def test_ignores_other_sites_logins_and_anchors(self):
        html = (
            '<a href="https://other.org/eligibility">Eligibility</a>'
            '<a href="/login?next=apply">Requirements login</a>'
            '<a href="#eligibility">Eligibility</a>'
            '<a href="mailto:a@b.org">Conditions</a>'
        )
        self.assertEqual(find_document_links(html, self.BASE), [])

    def test_pdf_on_another_host_is_kept(self):
        html = '<a href="https://cdn.other.org/call.pdf">Call</a>'
        self.assertEqual(find_document_links(html, self.BASE), ["https://cdn.other.org/call.pdf"])

    def test_does_not_link_back_to_itself(self):
        html = f'<a href="{self.BASE}#top">Eligibility</a>'
        self.assertEqual(find_document_links(html, self.BASE), [])

    def test_caps_the_number_of_links(self):
        html = "".join(f'<a href="/f{n}.pdf">f</a><a href="/c{n}">Conditions {n}</a>' for n in range(6))
        self.assertEqual(len(find_document_links(html, self.BASE)), 4)


class OutputHelpersTests(unittest.TestCase):
    def test_labelled_uses_display_labels_in_a_stable_order(self):
        result = labelled({"deadline": "d", "documents": "x"})
        self.assertEqual(list(result), ["Pièces à fournir", "Date limite"])

    def test_shorten_cuts_on_a_boundary_and_adds_an_ellipsis(self):
        text = "\n".join(f"• élément numéro {n}" for n in range(200))
        shortened = shorten_text(text, 100)
        self.assertLessEqual(len(shortened), 100)
        self.assertTrue(shortened.endswith("…"))
        self.assertNotIn("numé…", shortened)

    def test_shorten_leaves_short_text_alone(self):
        self.assertEqual(shorten_text("court"), "court")


if __name__ == "__main__":
    unittest.main()
