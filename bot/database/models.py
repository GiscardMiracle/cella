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
    role_id: int          # discord role id for the opportunity

@dataclass
class Interest:
    """Represents a user's interest in an opportunity."""
    opportunity_id: int
    user_id: int
    interested_at: datetime
    last_reminder_at: Optional[datetime] = None

@dataclass
class Announcement:
    """Represents a scholarship announcement discovered on a watched listing page."""
    id: str                            # id extracted from the source page's URL
    title: str
    link: str
    published_at: Optional[datetime]   # date shown on the listing page, if any
    discovered_at: datetime            # when Cella first saw it
