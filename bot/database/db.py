"""
Cella bot - 2026
Database handling (creating tables and connecting to the database)
Author: Giscard Adjanon
"""

import sqlite3
from pathlib import Path

_connection = None  # Global variable to hold the database connection

DB_PATH = Path(__file__).parent / "cella.db"

def get_connection():
    """Get a new connection to the database."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH)
    _connection.row_factory = sqlite3.Row  # Enable named column access
    return _connection

def initialize_database():
    """Initialize the database and create tables if they don't exist."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            link TEXT NOT NULL,
            deadline DATETIME NOT NULL,
            message_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at DATETIME NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interests (
            opportunity_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            interested_at DATETIME NOT NULL,
            last_reminder_at DATETIME,
            PRIMARY KEY (opportunity_id, user_id)
        )
    """)

    connection.commit()
