"""
Cella bot - 2026
Watcher cog: periodically checks the ministry's scholarship listing page
and posts newly discovered announcements in #opportunities.
Author: Giscard Adjanon
"""

import logging

from discord.ext import commands, tasks

from bot.config import config
from bot.services import watcher_service
from bot.utils import embeds

logger = logging.getLogger(__name__)


class WatcherCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_for_announcements.change_interval(hours=config.watch_interval_hours)
        self.check_for_announcements.start()

    def cog_unload(self):
        self.check_for_announcements.cancel()

    @tasks.loop(hours=6)
    async def check_for_announcements(self):
        if not config.watch_url:
            logger.info("Watcher: WATCH_URL not set, skipping check.")
            return

        logger.info("Watcher: checking %s", config.watch_url)
        new_announcements = await watcher_service.get_new_announcements(config.watch_url)
        if not new_announcements:
            return

        opportunities_channel = self.bot.get_channel(config.opportunities_channel_id)
        if opportunities_channel is None:
            logger.warning(
                "Watcher: opportunities channel %d not found, could not post %d new announcement(s).",
                config.opportunities_channel_id,
                len(new_announcements),
            )
            return

        for announcement in new_announcements:
            await opportunities_channel.send(embed=embeds.build_announcement_embed(announcement))

        logger.info(
            "Watcher: posted %d new announcement(s) in #opportunities.", len(new_announcements)
        )

    @check_for_announcements.before_loop
    async def before_check_for_announcements(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(WatcherCog(bot))
