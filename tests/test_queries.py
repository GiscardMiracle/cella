"""
Cella bot - 2026
Tests for database queries, run against an in-memory SQLite database.
Author: Giscard Adjanon
"""

import sqlite3
import unittest
from datetime import datetime, timedelta

from bot.database import db, queries
from bot.database.models import Interest, Opportunity


def _make_opportunity(name: str) -> Opportunity:
    now = datetime(2026, 9, 19, 12, 0)
    return Opportunity(
        id=0,
        name=name,
        description="desc",
        link="https://example.org",
        deadline=now + timedelta(days=30),
        message_id=1,
        channel_id=2,
        status="open",
        created_by=3,
        created_at=now,
        role_id=4,
    )


class DeleteOpportunityTests(unittest.TestCase):
    def setUp(self):
        self._original_connection = db._connection
        db._connection = sqlite3.connect(":memory:")
        db.initialize_database()

    def tearDown(self):
        db._connection.close()
        db._connection = self._original_connection

    def test_removes_the_opportunity_and_its_interests_only(self):
        doomed = queries.create_opportunity(_make_opportunity("doomed"))
        kept = queries.create_opportunity(_make_opportunity("kept"))
        now = datetime(2026, 9, 19, 12, 0)
        queries.add_interest(Interest(doomed.id, 10, now))
        queries.add_interest(Interest(kept.id, 10, now))

        self.assertTrue(queries.delete_opportunity(doomed.id))

        self.assertIsNone(queries.get_opportunity_by_name("doomed"))
        self.assertEqual(queries.list_interested(doomed.id), [])
        self.assertIsNotNone(queries.get_opportunity_by_name("kept"))
        self.assertEqual(queries.list_interested(kept.id), [10])

    def test_returns_false_for_unknown_opportunity(self):
        self.assertFalse(queries.delete_opportunity(999))


if __name__ == "__main__":
    unittest.main()
