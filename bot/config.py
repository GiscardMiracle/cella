"""
Cella bot - 2026
Environment variables and configuration settings for the bot.
Author: Giscard Adjanon
"""

import os
import sys
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()

@dataclass(frozen=True)
class Config:
    discord_token: str
    guild_id: int
    category_id: int                    # id of the category where opportunity channels will be created
    opportunities_channel_id: int       # id of the channel where opportunities will be posted

def _require(var_name: str) -> str:
    """Retrieve an environment variable or exit if not found."""
    value = os.getenv(var_name)
    if value is None:
        print(f"Error: Environment variable '{var_name}' is required but not set.", file=sys.stderr)
        sys.exit(1)
    return value

def load_config() -> Config:
    return Config(
        discord_token=_require("DISCORD_TOKEN"),
        guild_id=int(_require("GUILD_ID")),
        category_id=int(_require("CATEGORY_ID")),
        opportunities_channel_id=int(_require("OPPORTUNITIES_CHANNEL_ID"))
    )

config = load_config()
