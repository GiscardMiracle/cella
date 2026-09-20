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
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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

BACKFILL_MAX_PER_RUN = 10
BACKFILL_DELAY_SECONDS = 15
BACKFILL_TIME_BUDGET_SECONDS = 600
HISTORY_SCAN_LIMIT = 100


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
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
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

    task = asyncio.create_task(
        _post_scraped_info(channel, saved.link, gemini_api_key, gemini_model)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return saved


async def _post_scraped_info(
    channel: discord.TextChannel,
    link: str,
    gemini_api_key: Optional[str],
    gemini_model: Optional[str],
) -> None:
    """Best-effort: post auto-extracted info as the channel's first message.
    Runs in the background so opportunity creation never waits on it, and
    never raises - a failed scrape just means no info message gets posted."""
    try:
        info = await scraper_service.scrape_opportunity(
            link, gemini_api_key=gemini_api_key, gemini_model=gemini_model
        )
        await channel.send(
            embed=embeds.build_scraped_info_embed(
                info.source_url, info.sections, info.note, info.ai_generated
            )
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


class BackfillOutcome(Enum):
    POSTED = "posted"
    ALREADY_HAS_INFO = "already_has_info"
    NOTHING_FOUND = "nothing_found"
    CHANNEL_MISSING = "channel_missing"
    NO_ACCESS = "no_access"
    AI_FAILED = "ai_failed"
    QUOTA_EXCEEDED = "quota_exceeded"


_SCRAPED_OUTCOMES = {
    BackfillOutcome.POSTED,
    BackfillOutcome.NOTHING_FOUND,
    BackfillOutcome.AI_FAILED,
    BackfillOutcome.QUOTA_EXCEEDED,
}

_SUMMARY_LABELS = [
    (BackfillOutcome.POSTED, "Infos ajoutées"),
    (BackfillOutcome.ALREADY_HAS_INFO, "Déjà à jour"),
    (BackfillOutcome.NOTHING_FOUND, "Rien d'exploitable trouvé"),
    (BackfillOutcome.AI_FAILED, "IA indisponible (à relancer)"),
    (BackfillOutcome.NO_ACCESS, "Accès impossible au channel"),
    (BackfillOutcome.CHANNEL_MISSING, "Channel introuvable"),
]


@dataclass
class BackfillReport:
    results: list[tuple[Opportunity, BackfillOutcome]] = field(default_factory=list)
    not_attempted: int = 0

    def names(self, outcome: BackfillOutcome) -> list[str]:
        return [opportunity.name for opportunity, result in self.results if result is outcome]

    def summary(self) -> str:
        lines = [
            f"**{label}** ({len(self.names(outcome))}) : {', '.join(self.names(outcome))}"
            for outcome, label in _SUMMARY_LABELS
            if self.names(outcome)
        ]
        if self.names(BackfillOutcome.QUOTA_EXCEEDED):
            lines.append(
                "**Quota Gemini atteint** : réessaie dans quelques minutes, ou demain si la limite journalière est atteinte."
            )
        if self.not_attempted:
            lines.append(f"{self.not_attempted} opportunité(s) pas encore traitée(s) : relance la commande.")
        return "\n".join(lines)[:1900] or "Aucune opportunité ouverte à traiter."


def _bot_can_post(guild: discord.Guild, channel: discord.abc.GuildChannel) -> bool:
    perms = channel.permissions_for(guild.me)
    return perms.view_channel and perms.send_messages and perms.read_message_history


async def _regain_access(
    guild: discord.Guild, opportunity: Opportunity
) -> Optional[discord.abc.GuildChannel]:
    """Channels made before the bot was granted access to them are invisible to
    it. Joining the opportunity's own role (which can see the channel) lets it
    reach the channel and give itself a permanent overwrite, then it leaves."""
    role = guild.get_role(opportunity.role_id)
    if role is None:
        return None

    joined = False
    try:
        await guild.me.add_roles(role)
        joined = True
        channel = await guild.fetch_channel(opportunity.channel_id)
        return channel if await permissions.grant_bot_access(channel) else None
    except discord.HTTPException:
        logger.exception("Backfill: could not regain access to channel %d.", opportunity.channel_id)
        return None
    finally:
        if joined:
            try:
                await guild.me.remove_roles(role)
            except discord.HTTPException:
                logger.warning("Backfill: could not leave role %d again.", opportunity.role_id)


async def _channel_for_backfill(guild: discord.Guild, opportunity: Opportunity):
    channel = guild.get_channel(opportunity.channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(opportunity.channel_id)
        except discord.NotFound:
            return BackfillOutcome.CHANNEL_MISSING
        except discord.Forbidden:
            channel = await _regain_access(guild, opportunity)
            return channel if channel is not None else BackfillOutcome.NO_ACCESS

    if not _bot_can_post(guild, channel) and not await permissions.grant_bot_access(channel):
        return BackfillOutcome.NO_ACCESS
    return channel


async def _has_scraped_info(channel: discord.TextChannel, bot_user: discord.abc.User) -> bool:
    async for message in channel.history(limit=HISTORY_SCAN_LIMIT):
        if message.author.id == bot_user.id and any(
            embed.title == embeds.SCRAPED_INFO_TITLE for embed in message.embeds
        ):
            return True
    return False


async def _backfill_one(
    guild: discord.Guild,
    bot_user: discord.abc.User,
    opportunity: Opportunity,
    gemini_api_key: Optional[str],
    gemini_model: Optional[str],
) -> BackfillOutcome:
    try:
        channel = await _channel_for_backfill(guild, opportunity)
        if isinstance(channel, BackfillOutcome):
            return channel
        if await _has_scraped_info(channel, bot_user):
            return BackfillOutcome.ALREADY_HAS_INFO

        info = await scraper_service.scrape_opportunity(
            opportunity.link,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            fallback_to_keywords=False,
        )
        if info.quota_exceeded:
            return BackfillOutcome.QUOTA_EXCEEDED
        if info.ai_failed:
            return BackfillOutcome.AI_FAILED
        if not info.sections:
            return BackfillOutcome.NOTHING_FOUND

        await channel.send(
            embed=embeds.build_scraped_info_embed(
                info.source_url, info.sections, info.note, info.ai_generated
            )
        )
        return BackfillOutcome.POSTED
    except discord.HTTPException:
        logger.exception("Backfill: Discord refused an operation for opportunity %d.", opportunity.id)
        return BackfillOutcome.NO_ACCESS


async def backfill_scraped_info(
    guild: discord.Guild,
    bot_user: discord.abc.User,
    opportunities: list[Opportunity],
    gemini_api_key: Optional[str],
    gemini_model: Optional[str],
    *,
    max_scrapes: int = BACKFILL_MAX_PER_RUN,
    delay_seconds: float = BACKFILL_DELAY_SECONDS,
    time_budget_seconds: float = BACKFILL_TIME_BUDGET_SECONDS,
) -> BackfillReport:
    """Post the extracted info in the channel of each opportunity that lacks it.

    Built to stay inside a free API quota: at most max_scrapes extractions per
    run, a pause between them, a stop at the first quota error, and no weaker
    keyword result posted when the AI is unavailable (that would mark the
    opportunity as done and it would never be retried). Opportunities that
    already have their info don't count toward the cap, so the command can
    simply be run again until everything is covered."""
    report = BackfillReport()
    started = time.monotonic()
    scrapes = 0

    for index, opportunity in enumerate(opportunities):
        if scrapes >= max_scrapes or time.monotonic() - started > time_budget_seconds:
            report.not_attempted = len(opportunities) - index
            break

        outcome = await _backfill_one(guild, bot_user, opportunity, gemini_api_key, gemini_model)
        report.results.append((opportunity, outcome))
        logger.info("Backfill: opportunity %d (%s) -> %s.", opportunity.id, opportunity.name, outcome.value)

        if outcome is BackfillOutcome.QUOTA_EXCEEDED:
            report.not_attempted = len(opportunities) - index - 1
            break
        if outcome in _SCRAPED_OUTCOMES:
            scrapes += 1
            if gemini_api_key and delay_seconds and index + 1 < len(opportunities):
                await asyncio.sleep(delay_seconds)

    return report


async def remove_interested(member: discord.Member, opportunity: Opportunity) -> bool:
    """Revoke channel access and remove the interest record."""
    role = member.guild.get_role(opportunity.role_id)
    if role is not None and not await permissions.revoke_access(member, role):
        return False
    return queries.remove_interest(opportunity.id, member.id)
