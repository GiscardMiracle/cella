"""
Cella bot - 2026
Shared Data structures. Read and modified by database/queries.py
Author: Giscard Adjanon
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Opportunity:
    """Represents an opportunity."""
    id: int
    name: str
    description: str
    link: str      # url to the opportunity
    deadline: datetime
    message_id: int     # message posted in #opportunities channel
    channel_id: int     # dedicated channel for the opportunity
    status: str         # "open", "closed"
    created_by: int     # discord user id of the creator
    created_at: datetime

@dataclass
class Interest:
    """Represents a user's interest in an opportunity."""
    opportunity_id: int
    user_id: int
    interested_at: datetime
    last_reminder_at: Optional[datetime] = None
