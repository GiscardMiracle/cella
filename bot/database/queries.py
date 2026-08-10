"""
Cella bot - 2026
CRUD utility functions for managing opportunities in the database.
Author: Giscard Adjanon
"""

from datetime import datetime
import sqlite3
from typing import Optional

from bot.database.db import get_connection
from bot.database.models import Interest, Opportunity


def _row_to_opportunity(row: sqlite3.Row) -> Opportunity:
    """Convert a database row to an Opportunity object."""
    return Opportunity(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        link=row["link"],
        deadline=datetime.fromisoformat(row["deadline"]),
        message_id=row["message_id"],
        channel_id=row["channel_id"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        role_id=row["role_id"],
    )


def _row_to_interest(row: sqlite3.Row) -> Interest:
    """Convert a database row to an Interest object."""
    return Interest(
        opportunity_id=row["opportunity_id"],
        user_id=row["user_id"],
        interested_at=datetime.fromisoformat(row["interested_at"]),
        last_reminder_at=(
            datetime.fromisoformat(row["last_reminder_at"])
            if row["last_reminder_at"]
            else None
        ),
    )


def create_opportunity(opportunity: Opportunity) -> Optional[Opportunity]:
    """Insert a new opportunity into the database and return it with its new ID."""
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO opportunities (name, description, link, deadline, message_id, channel_id, status, created_by, created_at, role_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                opportunity.name,
                opportunity.description,
                opportunity.link,
                opportunity.deadline.isoformat(),
                opportunity.message_id,
                opportunity.channel_id,
                opportunity.status,
                opportunity.created_by,
                opportunity.created_at.isoformat(),
                opportunity.role_id,
            ),
        )
    except sqlite3.IntegrityError:
        # Handle the case where the opportunity name is not unique
        connection.rollback()  # Rollback the transaction to maintain database integrity
        return None

    connection.commit()
    opportunity.id = cursor.lastrowid  # Set the ID of the newly created opportunity
    return opportunity


def get_opportunity_by_message_id(message_id: int) -> Optional[Opportunity]:
    """Retrieve an opportunity by its message ID."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM opportunities WHERE message_id = ?", (message_id,))
    row = cursor.fetchone()

    if row:
        return _row_to_opportunity(row)
    return None


def get_opportunity_by_name(name: str) -> Optional[Opportunity]:
    """Retrieve an opportunity by its name."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM opportunities WHERE name = ?", (name,))
    row = cursor.fetchone()

    if row:
        return _row_to_opportunity(row)
    return None


def list_open_opportunities() -> list[Opportunity]:
    """List all open opportunities."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM opportunities WHERE status = 'open'")
    rows = cursor.fetchall()

    return [_row_to_opportunity(row) for row in rows]


def update_opportunity_status(opportunity_id: int, status: str) -> bool:
    """Update the status of an opportunity."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE opportunities SET status = ? WHERE id = ?", (status, opportunity_id)
    )
    connection.commit()
    return cursor.rowcount > 0


def add_interest(interest: Interest) -> bool:
    """Add a user's interest in an opportunity."""
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO interests (opportunity_id, user_id, interested_at)
            VALUES (?, ?, ?)
        """,
            (
                interest.opportunity_id,
                interest.user_id,
                interest.interested_at.isoformat(),
            ),
        )
    except sqlite3.IntegrityError:
        # Handle the case where the user has already expressed interest
        connection.rollback()
        return False

    connection.commit()
    return True


def remove_interest(opportunity_id: int, user_id: int) -> bool:
    """Remove a user's interest in an opportunity."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM interests WHERE opportunity_id = ? AND user_id = ?",
        (opportunity_id, user_id),
    )
    connection.commit()
    return cursor.rowcount > 0


def list_interested(opportunity_id: int) -> list[int]:
    """List all user IDs interested in a specific opportunity."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT user_id FROM interests WHERE opportunity_id = ?", (opportunity_id,)
    )
    rows = cursor.fetchall()

    return [row["user_id"] for row in rows]


def list_due_reminders() -> list[tuple[Interest, Opportunity]]:
    """List all interests that are due for a reminder."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT opportunities.*, interests.*
        FROM interests
        JOIN opportunities ON interests.opportunity_id = opportunities.id
        WHERE opportunities.status = 'open'
        """)
    rows = cursor.fetchall()

    return [(_row_to_interest(row), _row_to_opportunity(row)) for row in rows]


def update_last_reminder(
    opportunity_id: int, user_id: int, new_last_reminder_at: datetime
) -> bool:
    """Update the last reminder timestamp for a user's interest in an opportunity."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE interests SET last_reminder_at = ? WHERE opportunity_id = ? AND user_id = ?",
        (new_last_reminder_at.isoformat(), opportunity_id, user_id),
    )
    connection.commit()
    return cursor.rowcount > 0
