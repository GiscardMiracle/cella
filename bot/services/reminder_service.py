"""
Cella bot - 2026
Reminder service for the bot. Determines when to send reminders to users about their interests in opportunities.
Author: Giscard Adjanon
"""

from datetime import timedelta

FINAL_REMINDER_DAYS = (2, 5)

def should_send_reminder(interested_at, last_reminder_at, deadline, current_time):
    """
    Determine if a reminder should be sent to the user based on their interest and the opportunity's deadline.
    Returns a tuple (should_send_reminder, new_last_reminder_at).
    """
    if current_time >= deadline:
        return False, last_reminder_at
    for days in FINAL_REMINDER_DAYS:
        threshold = deadline - timedelta(days=days)
        if current_time >= threshold and interested_at < threshold and (last_reminder_at is None or last_reminder_at < threshold):
            return True, current_time
    if last_reminder_at is None:
        if current_time >= interested_at + timedelta(days=10): # First reminder after 10 days of interest
            return True, current_time
        return False, last_reminder_at
    if current_time >= last_reminder_at + timedelta(days=30) and deadline - current_time >= timedelta(days=90):
        return True, current_time
    if current_time >= last_reminder_at + timedelta(days=15) and deadline - current_time < timedelta(days=90):
        return True, current_time
    return False, last_reminder_at
