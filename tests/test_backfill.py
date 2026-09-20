"""
Cella bot - 2026
Tests for the backfill in bot.services.opportunity_service, with fake Discord
objects and a fake scraper (no network, no Discord).
Author: Giscard Adjanon
"""

import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.database.models import Opportunity
from bot.services import opportunity_service, scraper_service
from bot.services.opportunity_service import BackfillOutcome, BackfillReport, backfill_scraped_info
from bot.services.scraper_service import ScrapedInfo
from bot.utils import embeds

BOT_ID = 42
FOUND = ScrapedInfo("https://example.org", {"Date limite": "1er mai"}, None, ai_generated=True)


def http_error(error_class):
    return error_class(MagicMock(status=400, reason="error"), "error")


def make_opportunity(number: int) -> Opportunity:
    now = datetime(2026, 9, 19, 12, 0)
    return Opportunity(
        id=number,
        name=f"Bourse {number}",
        description="desc",
        link=f"https://example.org/{number}",
        deadline=now + timedelta(days=30),
        message_id=1000 + number,
        channel_id=2000 + number,
        status="open",
        created_by=1,
        created_at=now,
        role_id=3000 + number,
    )


def info_message(author_id: int = BOT_ID, title: str = embeds.SCRAPED_INFO_TITLE):
    return MagicMock(author=MagicMock(id=author_id), embeds=[MagicMock(title=title)])


def make_channel(guild, history=(), can_post: bool = True):
    channel = MagicMock()
    channel.guild = guild
    channel.send = AsyncMock()
    channel.set_permissions = AsyncMock()
    channel.permissions_for.return_value = MagicMock(
        view_channel=can_post, send_messages=can_post, read_message_history=can_post
    )

    async def history_iterator(limit=None):
        for message in history:
            yield message

    channel.history = history_iterator
    return channel


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        logging.getLogger("bot.services").setLevel(logging.CRITICAL)
        self.addCleanup(logging.getLogger("bot.services").setLevel, logging.NOTSET)
        printer = patch("builtins.print")
        printer.start()
        self.addCleanup(printer.stop)

        self.guild = MagicMock()
        self.guild.me = MagicMock()
        self.guild.me.add_roles = AsyncMock()
        self.guild.me.remove_roles = AsyncMock()
        self.guild.fetch_channel = AsyncMock()
        self.role = MagicMock()
        self.guild.get_role.return_value = self.role
        self.bot_user = MagicMock(id=BOT_ID)

        self.scrape = AsyncMock(return_value=FOUND)
        patcher = patch.object(scraper_service, "scrape_opportunity", self.scrape)
        patcher.start()
        self.addCleanup(patcher.stop)

        sleeper = patch.object(opportunity_service.asyncio, "sleep", AsyncMock())
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def channels(self, *channels):
        by_id = {}
        for number, channel in enumerate(channels, start=1):
            by_id[2000 + number] = channel
        self.guild.get_channel.side_effect = lambda channel_id: by_id.get(channel_id)

    async def run_backfill(self, opportunities, key="key", model="model", **options):
        options.setdefault("delay_seconds", 15)
        return await backfill_scraped_info(
            self.guild, self.bot_user, opportunities, key, model, **options
        )

    async def test_posts_the_extracted_info_where_it_is_missing(self):
        channel = make_channel(self.guild)
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)
        self.scrape.assert_awaited_once_with(
            "https://example.org/1", gemini_api_key="key", gemini_model="model", fallback_to_keywords=False
        )
        embed = channel.send.await_args.kwargs["embed"]
        self.assertEqual(embed.title, embeds.SCRAPED_INFO_TITLE)
        self.assertIn("IA", embed.footer.text)

    async def test_channels_that_already_have_the_info_are_left_alone(self):
        self.channels(make_channel(self.guild, history=[info_message()]))

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.ALREADY_HAS_INFO)
        self.scrape.assert_not_awaited()

    async def test_a_similar_message_from_someone_else_does_not_count(self):
        channel = make_channel(self.guild, history=[info_message(author_id=7)])
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)

    async def test_other_bot_messages_do_not_count(self):
        channel = make_channel(self.guild, history=[info_message(title="Autre chose")])
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)

    async def test_nothing_is_posted_when_nothing_was_found(self):
        channel = make_channel(self.guild)
        self.channels(channel)
        self.scrape.return_value = ScrapedInfo("https://example.org", note="Aucune information clé")

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NOTHING_FOUND)
        channel.send.assert_not_awaited()

    async def test_an_ai_failure_posts_nothing_and_moves_on(self):
        first, second = make_channel(self.guild), make_channel(self.guild)
        self.channels(first, second)
        self.scrape.side_effect = [ScrapedInfo("u", ai_failed=True), FOUND]

        report = await self.run_backfill([make_opportunity(1), make_opportunity(2)])

        self.assertEqual([outcome for _, outcome in report.results], [BackfillOutcome.AI_FAILED, BackfillOutcome.POSTED])
        first.send.assert_not_awaited()
        second.send.assert_awaited_once()

    async def test_stops_at_the_first_quota_error(self):
        channels = [make_channel(self.guild) for _ in range(3)]
        self.channels(*channels)
        self.scrape.return_value = ScrapedInfo("u", ai_failed=True, quota_exceeded=True)

        report = await self.run_backfill([make_opportunity(n) for n in (1, 2, 3)])

        self.assertEqual(self.scrape.await_count, 1)
        self.assertEqual(report.results[0][1], BackfillOutcome.QUOTA_EXCEEDED)
        self.assertEqual(report.not_attempted, 2)
        self.assertIn("Quota Gemini atteint", report.summary())

    async def test_caps_the_number_of_extractions_per_run(self):
        self.channels(*[make_channel(self.guild) for _ in range(4)])

        report = await self.run_backfill([make_opportunity(n) for n in range(1, 5)], max_scrapes=2)

        self.assertEqual(self.scrape.await_count, 2)
        self.assertEqual(len(report.results), 2)
        self.assertEqual(report.not_attempted, 2)

    async def test_already_done_channels_do_not_use_up_the_cap(self):
        done = [make_channel(self.guild, history=[info_message()]) for _ in range(3)]
        todo = make_channel(self.guild)
        self.channels(*done, todo)

        report = await self.run_backfill([make_opportunity(n) for n in range(1, 5)], max_scrapes=1)

        self.assertEqual(self.scrape.await_count, 1)
        self.assertEqual(report.not_attempted, 0)
        todo.send.assert_awaited_once()

    async def test_stops_when_the_time_budget_is_spent(self):
        self.channels(make_channel(self.guild))

        report = await self.run_backfill([make_opportunity(1)], time_budget_seconds=-1)

        self.assertEqual(report.results, [])
        self.assertEqual(report.not_attempted, 1)

    async def test_pauses_between_extractions_but_not_after_the_last(self):
        self.channels(*[make_channel(self.guild) for _ in range(3)])

        await self.run_backfill([make_opportunity(n) for n in (1, 2, 3)])

        self.assertEqual(self.sleep.await_count, 2)
        self.sleep.assert_awaited_with(15)

    async def test_no_pause_without_an_api_key(self):
        self.channels(*[make_channel(self.guild) for _ in range(2)])

        await self.run_backfill([make_opportunity(1), make_opportunity(2)], key=None)

        self.sleep.assert_not_awaited()

    async def test_channel_deleted_on_discord(self):
        self.channels()
        self.guild.fetch_channel.side_effect = http_error(discord.NotFound)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.CHANNEL_MISSING)
        self.scrape.assert_not_awaited()

    async def test_regains_access_to_a_channel_the_bot_cannot_see(self):
        channel = make_channel(self.guild)
        self.channels()
        self.guild.fetch_channel.side_effect = [http_error(discord.Forbidden), channel]

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)
        self.guild.get_role.assert_called_with(3001)
        self.guild.me.add_roles.assert_awaited_once_with(self.role)
        channel.set_permissions.assert_awaited_once()
        self.assertIs(channel.set_permissions.await_args.args[0], self.guild.me)
        self.guild.me.remove_roles.assert_awaited_once_with(self.role)
        channel.send.assert_awaited_once()

    async def test_the_bot_leaves_the_role_even_when_granting_itself_access_fails(self):
        channel = make_channel(self.guild)
        channel.set_permissions.side_effect = http_error(discord.Forbidden)
        self.channels()
        self.guild.fetch_channel.side_effect = [http_error(discord.Forbidden), channel]

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NO_ACCESS)
        self.guild.me.remove_roles.assert_awaited_once_with(self.role)
        channel.send.assert_not_awaited()

    async def test_no_access_when_the_role_is_gone_too(self):
        self.channels()
        self.guild.get_role.return_value = None
        self.guild.fetch_channel.side_effect = http_error(discord.Forbidden)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NO_ACCESS)
        self.guild.me.add_roles.assert_not_awaited()

    async def test_no_access_when_the_bot_cannot_join_the_role(self):
        self.channels()
        self.guild.fetch_channel.side_effect = http_error(discord.Forbidden)
        self.guild.me.add_roles.side_effect = http_error(discord.Forbidden)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NO_ACCESS)
        self.guild.me.remove_roles.assert_not_awaited()

    async def test_visible_channel_where_the_bot_cannot_post_gets_an_overwrite(self):
        channel = make_channel(self.guild, can_post=False)
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)
        channel.set_permissions.assert_awaited_once()
        self.guild.me.add_roles.assert_not_awaited()

    async def test_no_access_when_a_visible_channel_cannot_be_fixed(self):
        channel = make_channel(self.guild, can_post=False)
        channel.set_permissions.side_effect = http_error(discord.Forbidden)
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NO_ACCESS)

    async def test_a_refused_send_is_reported_not_raised(self):
        channel = make_channel(self.guild)
        channel.send.side_effect = http_error(discord.Forbidden)
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)])

        self.assertEqual(report.results[0][1], BackfillOutcome.NO_ACCESS)

    async def test_works_without_an_api_key_using_keywords(self):
        channel = make_channel(self.guild)
        self.channels(channel)

        report = await self.run_backfill([make_opportunity(1)], key=None)

        self.assertEqual(report.results[0][1], BackfillOutcome.POSTED)
        self.assertIsNone(self.scrape.await_args.kwargs["gemini_api_key"])


class BackfillReportTests(unittest.TestCase):
    def test_summary_lists_names_per_outcome(self):
        report = BackfillReport(
            results=[
                (make_opportunity(1), BackfillOutcome.POSTED),
                (make_opportunity(2), BackfillOutcome.POSTED),
                (make_opportunity(3), BackfillOutcome.NO_ACCESS),
            ],
            not_attempted=4,
        )

        summary = report.summary()

        self.assertIn("Infos ajoutées** (2) : Bourse 1, Bourse 2", summary)
        self.assertIn("Accès impossible au channel** (1) : Bourse 3", summary)
        self.assertIn("4 opportunité(s) pas encore traitée(s)", summary)
        self.assertNotIn("Quota", summary)

    def test_empty_report(self):
        self.assertEqual(BackfillReport().summary(), "Aucune opportunité ouverte à traiter.")

    def test_summary_fits_in_a_discord_message(self):
        results = [(make_opportunity(n), BackfillOutcome.POSTED) for n in range(400)]
        self.assertLessEqual(len(BackfillReport(results=results).summary()), 2000)


if __name__ == "__main__":
    unittest.main()
