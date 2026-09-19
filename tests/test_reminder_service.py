"""
Cella bot - 2026
Tests for the reminder cadence in bot.services.reminder_service.
Author: Giscard Adjanon
"""

import unittest
from datetime import datetime, timedelta

from bot.services.reminder_service import should_send_reminder

NOW = datetime(2026, 9, 19, 12, 0)


class FirstReminderTests(unittest.TestCase):
    def test_sent_after_ten_days_of_interest(self):
        sent, new_last = should_send_reminder(
            NOW - timedelta(days=10), None, NOW + timedelta(days=60), NOW
        )
        self.assertTrue(sent)
        self.assertEqual(new_last, NOW)

    def test_not_sent_before_ten_days(self):
        sent, new_last = should_send_reminder(
            NOW - timedelta(days=9), None, NOW + timedelta(days=60), NOW
        )
        self.assertFalse(sent)
        self.assertIsNone(new_last)

    def test_not_sent_after_deadline(self):
        sent, _ = should_send_reminder(
            NOW - timedelta(days=12), None, NOW - timedelta(days=1), NOW
        )
        self.assertFalse(sent)

    def test_not_sent_exactly_at_deadline(self):
        sent, _ = should_send_reminder(NOW - timedelta(days=12), None, NOW, NOW)
        self.assertFalse(sent)


class RecurringReminderTests(unittest.TestCase):
    def test_monthly_when_deadline_is_far(self):
        deadline = NOW + timedelta(days=120)
        interested_at = NOW - timedelta(days=60)
        self.assertTrue(
            should_send_reminder(interested_at, NOW - timedelta(days=30), deadline, NOW)[0]
        )
        self.assertFalse(
            should_send_reminder(interested_at, NOW - timedelta(days=29), deadline, NOW)[0]
        )

    def test_every_two_weeks_when_deadline_is_close(self):
        deadline = NOW + timedelta(days=40)
        interested_at = NOW - timedelta(days=60)
        self.assertTrue(
            should_send_reminder(interested_at, NOW - timedelta(days=15), deadline, NOW)[0]
        )
        self.assertFalse(
            should_send_reminder(interested_at, NOW - timedelta(days=14), deadline, NOW)[0]
        )

    def test_not_sent_after_deadline_even_if_cadence_is_due(self):
        sent, _ = should_send_reminder(
            NOW - timedelta(days=60),
            NOW - timedelta(days=20),
            NOW - timedelta(days=1),
            NOW,
        )
        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()
