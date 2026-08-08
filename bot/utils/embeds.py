"""
Cella bot - 2026
Embed utility functions for creating and managing Discord embeds.
Author: Giscard Adjanon
"""

from datetime import datetime, timedelta

import discord

from bot.database.models import Opportunity


def urgency_colour(deadline, current_time):
    """
    Determine the urgency colour based on the deadline and current time.
    Returns a discord.Colour object.
    """
    if deadline - current_time >= timedelta(days=90):
        return discord.Colour.green()
    elif deadline - current_time < timedelta(
        days=90
    ) and deadline - current_time >= timedelta(days=30):
        return discord.Colour.orange()
    else:
        return discord.Colour.red()


def build_opportunity_embed(opportunity: Opportunity) -> discord.Embed:
    """
    Build a Discord embed for an opportunity.
    """
    deadline = discord.utils.format_dt(opportunity.deadline, style="F")
    embed = discord.Embed(
        title=opportunity.name,
        description=opportunity.description,
        url=opportunity.link,
        colour=urgency_colour(opportunity.deadline, datetime.now()),
    )
    embed.add_field(name="Deadline", value=deadline, inline=False)
    embed.add_field(name="Status", value=opportunity.status.capitalize(), inline=False)
    embed.add_field(
        name="Author",
        value=f"Created by User: <@{opportunity.created_by}> on {discord.utils.format_dt(opportunity.created_at, style='F')}",
        inline=False,
    )
    return embed
