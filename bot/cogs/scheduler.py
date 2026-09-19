"""
Cella bot - 2026
Daily scheduler: sends reminder DMs, auto-locks opportunities past their
deadline, and refreshes embed colours for open ones.
Author: Giscard Adjanon
"""

import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks

from bot.config import config
from bot.database import queries
from bot.database.models import Opportunity
from bot.services import opportunity_service, reminder_service
from bot.utils import embeds

logger = logging.getLogger(__name__)


class SchedulerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_check.start()

    def cog_unload(self):
        self.daily_check.cancel()

    @tasks.loop(hours=24)
    async def daily_check(self):
        now = datetime.now()
        await self._send_due_reminders(now)
        await self._process_open_opportunities(now)

    @daily_check.before_loop
    async def before_daily_check(self):
        await self.bot.wait_until_ready()

    async def _send_due_reminders(self, now: datetime):
        sent = 0

        for interest, opportunity in queries.list_due_reminders():
            should_send, new_last_reminder_at = reminder_service.should_send_reminder(
                interest.interested_at,
                interest.last_reminder_at,
                opportunity.deadline,
                now,
            )
            if not should_send:
                continue

            try:
                user = await self.bot.fetch_user(interest.user_id)
                await user.send(
                    f"Reminder: **{opportunity.name}** is still open "
                    f"({discord.utils.format_dt(opportunity.deadline, style='R')})."
                )
            except discord.Forbidden:
                logger.info(
                    "Scheduler: DMs closed for user %d, reminder for opportunity %d skipped.",
                    interest.user_id,
                    opportunity.id,
                )
                continue
            except discord.HTTPException:
                logger.exception(
                    "Scheduler: failed to send reminder for opportunity %d to user %d.",
                    opportunity.id,
                    interest.user_id,
                )
                continue

            queries.update_last_reminder(
                opportunity.id, interest.user_id, new_last_reminder_at
            )
            sent += 1

        logger.info("Scheduler: %d reminder(s) sent.", sent)

    async def _process_open_opportunities(self, now: datetime):
        opportunities_channel = self.bot.get_channel(config.opportunities_channel_id)
        if opportunities_channel is None:
            logger.warning(
                "Scheduler: opportunities channel %d not found.",
                config.opportunities_channel_id,
            )
            return

        for opportunity in queries.list_open_opportunities():
            try:
                await self._process_opportunity(opportunities_channel, opportunity, now)
            except discord.HTTPException:
                logger.exception(
                    "Scheduler: failed to process opportunity %d.", opportunity.id
                )

    async def _handle_missing_channel(self, opportunity: Opportunity):
        try:
            await self.bot.fetch_channel(opportunity.channel_id)
        except discord.NotFound:
            queries.delete_opportunity(opportunity.id)
            logger.info(
                "Scheduler: channel %d of opportunity %d (%s) no longer exists, removed it from the database.",
                opportunity.channel_id,
                opportunity.id,
                opportunity.name,
            )
        except discord.Forbidden:
            logger.warning(
                "Scheduler: no access to channel %d of opportunity %d, skipping.",
                opportunity.channel_id,
                opportunity.id,
            )
        else:
            logger.warning(
                "Scheduler: channel %d of opportunity %d exists but is not cached, skipping.",
                opportunity.channel_id,
                opportunity.id,
            )

    async def _process_opportunity(
        self,
        opportunities_channel: discord.TextChannel,
        opportunity: Opportunity,
        now: datetime,
    ):
        channel = self.bot.get_channel(opportunity.channel_id)
        if channel is None:
            await self._handle_missing_channel(opportunity)
            return

        try:
            message = await opportunities_channel.fetch_message(opportunity.message_id)
        except discord.NotFound:
            logger.warning(
                "Scheduler: message %d of opportunity %d not found, skipping.",
                opportunity.message_id,
                opportunity.id,
            )
            return

        if now >= opportunity.deadline:
            role = channel.guild.get_role(opportunity.role_id)
            if role is None:
                logger.warning(
                    "Scheduler: role %d of opportunity %d not found, cannot close it.",
                    opportunity.role_id,
                    opportunity.id,
                )
                return
            if await opportunity_service.close_opportunity(opportunity, channel, role, message):
                logger.info("Scheduler: closed opportunity %d (%s).", opportunity.id, opportunity.name)
            return

        current_colour = message.embeds[0].colour if message.embeds else None
        if current_colour == embeds.urgency_colour(opportunity.deadline, now):
            return

        await message.edit(embed=embeds.build_opportunity_embed(opportunity))
        logger.info(
            "Scheduler: refreshed colour of opportunity %d (%s).", opportunity.id, opportunity.name
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulerCog(bot))
