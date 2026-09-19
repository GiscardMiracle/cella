"""
Cella bot - 2026
Tests for the cleanup logic in bot.services.opportunity_service.
Author: Giscard Adjanon
"""

import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.database import db, queries
from bot.database.models import Opportunity
from bot.services import opportunity_service


def _http_error(error_class):
    return error_class(MagicMock(status=400, reason="error"), "error")


class RemoveOpportunityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._original_connection = db._connection
        db._connection = sqlite3.connect(":memory:")
        db.initialize_database()

        now = datetime(2026, 9, 19, 12, 0)
        self.opportunity = queries.create_opportunity(
            Opportunity(
                id=0,
                name="test",
                description="desc",
                link="https://example.org",
                deadline=now + timedelta(days=30),
                message_id=11,
                channel_id=22,
                status="open",
                created_by=33,
                created_at=now,
                role_id=44,
            )
        )

        self.role = MagicMock()
        self.role.delete = AsyncMock()
        self.message = MagicMock()
        self.message.delete = AsyncMock()
        self.channel = MagicMock()
        self.channel.guild.get_role.return_value = self.role
        self.channel.get_partial_message.return_value = self.message

    def tearDown(self):
        db._connection.close()
        db._connection = self._original_connection

    async def test_removes_role_message_and_database_entry(self):
        removed = await opportunity_service.remove_opportunity(self.channel, self.opportunity)

        self.assertTrue(removed)
        self.channel.guild.get_role.assert_called_once_with(44)
        self.role.delete.assert_awaited_once()
        self.channel.get_partial_message.assert_called_once_with(11)
        self.message.delete.assert_awaited_once()
        self.assertIsNone(queries.get_opportunity_by_name("test"))

    async def test_already_deleted_message_and_role_are_fine(self):
        self.role.delete.side_effect = _http_error(discord.NotFound)
        self.message.delete.side_effect = _http_error(discord.NotFound)

        removed = await opportunity_service.remove_opportunity(self.channel, self.opportunity)

        self.assertTrue(removed)
        self.assertIsNone(queries.get_opportunity_by_name("test"))

    async def test_role_not_in_cache_is_skipped(self):
        self.channel.guild.get_role.return_value = None

        await opportunity_service.remove_opportunity(self.channel, self.opportunity)

        self.role.delete.assert_not_awaited()
        self.assertIsNone(queries.get_opportunity_by_name("test"))

    async def test_database_entry_kept_when_discord_cleanup_fails(self):
        self.role.delete.side_effect = _http_error(discord.Forbidden)

        with self.assertRaises(discord.Forbidden):
            await opportunity_service.remove_opportunity(self.channel, self.opportunity)

        self.assertIsNotNone(queries.get_opportunity_by_name("test"))


class CloseOpportunityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._original_connection = db._connection
        db._connection = sqlite3.connect(":memory:")
        db.initialize_database()

        now = datetime(2026, 9, 19, 12, 0)
        self.opportunity = queries.create_opportunity(
            Opportunity(
                id=0,
                name="test",
                description="desc",
                link="https://example.org",
                deadline=now - timedelta(days=1),
                message_id=11,
                channel_id=22,
                status="open",
                created_by=33,
                created_at=now,
                role_id=44,
            )
        )
        self.message = MagicMock()
        self.message.edit = AsyncMock()

    def tearDown(self):
        db._connection.close()
        db._connection = self._original_connection

    async def test_marks_closed_and_refreshes_the_embed(self):
        closed = await opportunity_service.close_opportunity(self.opportunity, self.message)

        self.assertTrue(closed)
        self.assertEqual(queries.get_opportunity_by_name("test").status, "closed")
        self.message.edit.assert_awaited_once()
        embed = self.message.edit.await_args.kwargs["embed"]
        self.assertIn("Closed", [field.value for field in embed.fields])

    async def test_closed_opportunities_are_no_longer_listed_as_open(self):
        await opportunity_service.close_opportunity(self.opportunity, self.message)

        self.assertEqual(queries.list_open_opportunities(), [])


if __name__ == "__main__":
    unittest.main()
