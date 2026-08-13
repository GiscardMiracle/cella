"""
Cella bot - 2026
Main file for the bot. Run the bot from here.
Author: Giscard Adjanon
"""

import discord
from discord.ext import commands

from bot.config import config
from bot.database.db import initialize_database

EXTENSIONS = [
    "bot.cogs.opportunities",
    "bot.cogs.reactions",
    "bot.cogs.scheduler",
]


class CellaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        initialize_database()

        for extension in EXTENSIONS:
            await self.load_extension(extension)

        guild = discord.Object(id=config.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


def main():
    bot = CellaBot()
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
