"""
Cella bot - 2026
Tests for the scraped-info embed in bot.utils.embeds.
Author: Giscard Adjanon
"""

import unittest

from bot.utils import embeds


def long_list(items: int) -> str:
    return "\n".join(f"• pièce numéro {n} à fournir dans le dossier de candidature" for n in range(items))


class ScrapedInfoEmbedTests(unittest.TestCase):
    def test_short_sections_become_one_field_each(self):
        embed = embeds.build_scraped_info_embed(
            "https://example.org", {"Pièces à fournir": "• CV", "Date limite": "1er mai"}, None
        )
        self.assertEqual([field.name for field in embed.fields], ["Pièces à fournir", "Date limite"])

    def test_a_long_section_continues_in_extra_fields_without_losing_lines(self):
        text = long_list(40)
        embed = embeds.build_scraped_info_embed("https://example.org", {"Pièces à fournir": text}, None)

        self.assertGreater(len(embed.fields), 1)
        self.assertEqual(embed.fields[0].name, "Pièces à fournir")
        self.assertEqual(embed.fields[1].name, "Pièces à fournir (suite)")
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))
        self.assertEqual("\n".join(field.value for field in embed.fields), text)

    def test_stays_under_discords_embed_size_limit(self):
        sections = {label: long_list(60) for label in ("A", "B", "C", "D", "E")}
        embed = embeds.build_scraped_info_embed("https://example.org", sections, None)

        self.assertLessEqual(len(embed), 6000)
        self.assertLessEqual(len(embed.fields), 25)

    def test_note_is_shown_when_nothing_was_extracted(self):
        embed = embeds.build_scraped_info_embed("https://example.org", {}, "Le PDF lié semble être un scan")
        self.assertEqual(embed.fields, [])
        self.assertIn("scan", embed.description)

    def test_footer_says_when_the_summary_comes_from_the_ai(self):
        with_ai = embeds.build_scraped_info_embed("https://example.org", {"Date limite": "x"}, None, True)
        without_ai = embeds.build_scraped_info_embed("https://example.org", {"Date limite": "x"}, None)

        self.assertIn("IA", with_ai.footer.text)
        self.assertNotIn("IA", without_ai.footer.text)
        self.assertIn("À vérifier", with_ai.footer.text)


if __name__ == "__main__":
    unittest.main()
