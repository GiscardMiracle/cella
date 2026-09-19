"""
Cella bot - 2026
Opportunity service: orchestrates role creation, channel setup, embed
posting, and DB persistence for opportunities.
Author: Giscard Adjanon
"""

import asyncio
import logging
import re
import secrets
from datetime import datetime
from typing import Optional

import discord

from bot.database import queries
from bot.database.models import Interest, Opportunity
from bot.services import scraper_service
from bot.utils import embeds, permissions

logger = logging.getLogger(__name__)

# asyncio only keeps a *weak* reference to tasks - one with no other
# reference can be garbage-collected before it ever runs, silently. This
# set holds a strong reference to background scrape tasks until they're
# done, as recommended by the asyncio docs.
_background_tasks: set[asyncio.Task] = set()


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

    task = asyncio.create_task(_post_scraped_info(channel, saved.link))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return saved


async def _post_scraped_info(channel: discord.TextChannel, link: str) -> None:
    """Best-effort: post auto-extracted info as the channel's first message.
    Runs in the background so opportunity creation never waits on it, and
    never raises - a failed scrape just means no info message gets posted."""
    try:
        info = await scraper_service.scrape_opportunity(link)
        await channel.send(
            embed=embeds.build_scraped_info_embed(info.source_url, info.sections, info.note)
        )
    except Exception:
        logger.exception("Failed to post auto-extracted info in channel %d", channel.id)


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


async def close_opportunity(opportunity: Opportunity, message: discord.Message) -> bool:
    """Mark closed in DB and refresh the embed. The channel stays open so
    members can keep discussing."""
    if not queries.update_opportunity_status(opportunity.id, "closed"):
        return False

    opportunity.status = "closed"
    await message.edit(embed=embeds.build_opportunity_embed(opportunity))
    return True


async def remove_opportunity(
    opportunities_channel: discord.TextChannel, opportunity: Opportunity
) -> bool:
    """Delete an opportunity's role and announcement message, then its DB row.
    The DB row goes last so a failed Discord cleanup is retried on the next run."""
    role = opportunities_channel.guild.get_role(opportunity.role_id)
    if role is not None:
        try:
            await role.delete()
        except discord.NotFound:
            pass

    try:
        await opportunities_channel.get_partial_message(opportunity.message_id).delete()
    except discord.NotFound:
        pass

    return queries.delete_opportunity(opportunity.id)


async def remove_interested(member: discord.Member, opportunity: Opportunity) -> bool:
    """Revoke channel access and remove the interest record."""
    role = member.guild.get_role(opportunity.role_id)
    if role is not None and not await permissions.revoke_access(member, role):
        return False
    return queries.remove_interest(opportunity.id, member.id)
