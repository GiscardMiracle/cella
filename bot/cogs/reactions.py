"""
Cella bot - 2026
Listens for reactions on opportunity messages in #opportunities and grants
the reactor access to that opportunity's channel.
Author: Giscard Adjanon
"""

from enum import member

import discord
from discord import guild
from discord.ext import commands

from bot.config import config
from bot.database import queries
from bot.services import opportunity_service


class ReactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id != config.opportunities_channel_id:
            return
        if payload.member is None or payload.member.bot:
            return

        opportunity = queries.get_opportunity_by_message_id(payload.message_id)
        if opportunity is None or opportunity.status != "open":
            return

        await opportunity_service.mark_interested(payload.member, opportunity)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id != config.opportunities_channel_id:
            return

        opportunity = queries.get_opportunity_by_message_id(payload.message_id)
        if opportunity is None or opportunity.status != "open":
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        if member is None or member.bot:
            return

        await opportunity_service.remove_interested(member, opportunity)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionsCog(bot))
