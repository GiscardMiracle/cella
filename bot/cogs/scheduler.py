"""
Cella bot - 2026
Daily scheduler: sends reminder DMs, auto-locks opportunities past their
deadline, and refreshes embed colours for open ones.
Author: Giscard Adjanon
"""

from datetime import datetime

import discord
from discord.ext import commands, tasks

from bot.config import config
from bot.database import queries
from bot.services import opportunity_service, reminder_service
from bot.utils import embeds


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
                continue  # DMs closed, skip silently

            queries.update_last_reminder(
                opportunity.id, interest.user_id, new_last_reminder_at
            )

    async def _process_open_opportunities(self, now: datetime):
        opportunities_channel = self.bot.get_channel(config.opportunities_channel_id)

        for opportunity in queries.list_open_opportunities():
            channel = self.bot.get_channel(opportunity.channel_id)
            if channel is None:
                continue

            try:
                message = await opportunities_channel.fetch_message(
                    opportunity.message_id
                )
            except discord.NotFound:
                continue

            if now >= opportunity.deadline:
                role = channel.guild.get_role(opportunity.role_id)
                if role is not None:
                    await opportunity_service.close_opportunity(
                        opportunity, channel, role, message
                    )
            else:
                await message.edit(embed=embeds.build_opportunity_embed(opportunity))


async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulerCog(bot))
