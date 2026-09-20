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


SCRAPED_INFO_TITLE = "Infos extraites automatiquement du lien"
EMBED_FIELD_LIMIT = 1024
EMBED_TEXT_BUDGET = 5500


def _split_for_fields(text: str, limit: int = EMBED_FIELD_LIMIT) -> list[str]:
    """Split text on line boundaries into pieces that fit an embed field."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(line) > limit:
            line = line[: limit - 1] + "…"
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_scraped_info_embed(
    source_url: str,
    sections: dict[str, str],
    note: "str | None",
    ai_generated: bool = False,
) -> discord.Embed:
    """
    Build a Discord embed presenting info auto-extracted from an opportunity's link.
    """
    embed = discord.Embed(
        title=SCRAPED_INFO_TITLE,
        url=source_url,
        colour=discord.Colour.light_grey(),
    )
    if sections:
        budget = EMBED_TEXT_BUDGET
        for label, excerpt in sections.items():
            for number, chunk in enumerate(_split_for_fields(excerpt)):
                name = label if number == 0 else f"{label} (suite)"
                budget -= len(name) + len(chunk)
                if budget < 0:
                    break
                embed.add_field(name=name, value=chunk, inline=False)
    else:
        embed.description = note or "Aucune information n'a pu être extraite automatiquement."

    origin = "Résumé généré par IA (Gemini). " if ai_generated else ""
    embed.set_footer(text=f"{origin}À vérifier sur le lien original avant de constituer votre dossier.")
    return embed
