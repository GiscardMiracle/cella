"""
Cella bot - 2026
Slash commands for creating opportunities and listing interested members.
Author: Giscard Adjanon
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.database import queries
from bot.services import opportunity_service
from bot.ui.modals import OpportunityAddModal


class OpportunitiesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._backfill_running = False

    @app_commands.command(
        name="opportunity-add", description="Add a new scholarship opportunity"
    )
    async def opportunity_add(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OpportunityAddModal())

    @app_commands.command(
        name="opportunity-members",
        description="List members interested in an opportunity",
    )
    @app_commands.describe(name="Exact name of the opportunity")
    async def opportunity_members(self, interaction: discord.Interaction, name: str):
        opportunity = queries.get_opportunity_by_name(name)
        if opportunity is None:
            await interaction.response.send_message(
                f"No opportunity named '{name}' found.", ephemeral=True
            )
            return

        user_ids = queries.list_interested(opportunity.id)
        if not user_ids:
            await interaction.response.send_message(
                f"No one has expressed interest in **{opportunity.name}** yet.",
                ephemeral=True,
            )
            return

        mentions = "\n".join(f"<@{uid}>" for uid in user_ids)
        embed = discord.Embed(
            title=f"Interested in {opportunity.name}", description=mentions
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="opportunity-backfill",
        description="Post the extracted info in open opportunities' channels that don't have it yet",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def opportunity_backfill(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return
        if self._backfill_running:
            await interaction.response.send_message(
                "Un backfill est déjà en cours.", ephemeral=True
            )
            return

        self._backfill_running = True
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            report = await opportunity_service.backfill_scraped_info(
                interaction.guild,
                interaction.client.user,
                queries.list_open_opportunities(),
                config.gemini_api_key,
                config.gemini_model,
            )
        finally:
            self._backfill_running = False

        await interaction.followup.send(report.summary(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(OpportunitiesCog(bot))
