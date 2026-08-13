"""
Cella bot - 2026
Opportunity service: orchestrates role creation, channel setup, embed
posting, and DB persistence for opportunities.
Author: Giscard Adjanon
"""

import re
import secrets
from datetime import datetime
from typing import Optional

import discord

from bot.database import queries
from bot.database.models import Interest, Opportunity
from bot.utils import embeds, permissions


def _slugify(name: str) -> str:
    """Turn a free-text name into a short, safe slug for role/channel names."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80]


async def create_opportunity(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    opportunities_channel: discord.TextChannel,
    name: str,
    description: str,
    link: str,
    deadline: datetime,
    created_by: int,
) -> Optional[Opportunity]:
    """Create a full opportunity: role, channel, embed message, DB row.
    Returns None (and cleans up any partial Discord state) on failure."""

    if queries.get_opportunity_by_name(name):
        return None

    role_name = f"{_slugify(name)}-{secrets.token_hex(3)}"
    role = await permissions.create_opportunity_role(guild, role_name)
    if role is None:
        return None

    try:
        channel = await guild.create_text_channel(
            name=_slugify(name), category=category
        )
    except discord.HTTPException:
        await role.delete()
        return None

    if not await permissions.setup_channel_permissions(channel, role):
        await role.delete()
        await channel.delete()
        return None

    created_at = datetime.now()
    draft = Opportunity(
        id=0,
        name=name,
        description=description,
        link=link,
        deadline=deadline,
        message_id=0,
        channel_id=channel.id,
        role_id=role.id,
        status="open",
        created_by=created_by,
        created_at=created_at,
    )

    try:
        message = await opportunities_channel.send(
            embed=embeds.build_opportunity_embed(draft)
        )
    except discord.HTTPException:
        await role.delete()
        await channel.delete()
        return None

    final = Opportunity(
        id=0,
        name=name,
        description=description,
        link=link,
        deadline=deadline,
        message_id=message.id,
        channel_id=channel.id,
        role_id=role.id,
        status="open",
        created_by=created_by,
        created_at=created_at,
    )

    try:
        saved = queries.create_opportunity(final)
    except Exception:
        await role.delete()
        await channel.delete()
        await message.delete()
        raise

    if saved is None:
        await role.delete()
        await channel.delete()
        await message.delete()
        return None

    return saved


async def mark_interested(member: discord.Member, opportunity: Opportunity) -> bool:
    """Grant channel access and record interest. Only touches the DB if
    the Discord side actually succeeded."""
    role = member.guild.get_role(opportunity.role_id)
    if role is None or not await permissions.grant_access(member, role):
        return False

    interest = Interest(
        opportunity_id=opportunity.id, user_id=member.id, interested_at=datetime.now()
    )
    return queries.add_interest(interest)


async def close_opportunity(
    opportunity: Opportunity,
    channel: discord.TextChannel,
    role: discord.Role,
    message: discord.Message,
) -> bool:
    """Lock the channel, mark closed in DB, refresh the embed."""
    if not await permissions.lock_channel(channel, role):
        return False
    if not queries.update_opportunity_status(opportunity.id, "closed"):
        return False

    opportunity.status = "closed"
    await message.edit(embed=embeds.build_opportunity_embed(opportunity))
    return True


async def remove_interested(member: discord.Member, opportunity: Opportunity) -> bool:
    """Revoke channel access and remove the interest record."""
    role = member.guild.get_role(opportunity.role_id)
    if role is not None and not await permissions.revoke_access(member, role):
        return False
    return queries.remove_interest(opportunity.id, member.id)
