"""
Cella bot - 2026
Embed utility functions for creating and managing Discord embeds.
Author: Giscard Adjanon
"""

from datetime import datetime, timedelta

import discord

from bot.database.models import Announcement, Opportunity


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


def build_announcement_embed(announcement: Announcement) -> discord.Embed:
    """
    Build a Discord embed for a newly discovered scholarship announcement.
    """
    embed = discord.Embed(
        title=announcement.title,
        url=announcement.link,
        description="Nouvelle annonce détectée. Utilisez `/opportunity-add` pour la suivre officiellement.",
        colour=discord.Colour.blurple(),
    )
    if announcement.published_at:
        embed.add_field(
            name="Publié le",
            value=discord.utils.format_dt(announcement.published_at, style="D"),
            inline=False,
        )
    return embed


def build_scraped_info_embed(
    source_url: str, sections: dict[str, str], note: "str | None"
) -> discord.Embed:
    """
    Build a Discord embed presenting info auto-extracted from an opportunity's link.
    """
    embed = discord.Embed(
        title="Infos extraites automatiquement du lien",
        url=source_url,
        colour=discord.Colour.light_grey(),
    )
    if sections:
        for label, excerpt in sections.items():
            embed.add_field(name=label, value=excerpt[:1024], inline=False)
    else:
        embed.description = note or "Aucune information n'a pu être extraite automatiquement."
    embed.set_footer(text="À vérifier sur le lien original avant de constituer votre dossier.")
    return embed
