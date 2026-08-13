"""
Cella bot - 2026
Modal form for creating a new opportunity.
Author: Giscard Adjanon
"""

import discord
import dateparser

from bot.config import config
from bot.services import opportunity_service


class OpportunityAddModal(discord.ui.Modal, title="New Opportunity"):
    name = discord.ui.TextInput(
        label="Name",
        placeholder="e.g. Erasmus Mundus Scholarship",
        max_length=80,
    )
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    link = discord.ui.TextInput(
        label="Link",
        placeholder="https://...",
    )
    deadline = discord.ui.TextInput(
        label="Deadline",
        placeholder="e.g. 2026-09-15 or September 15 2026",
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        parsed_deadline = dateparser.parse(self.deadline.value)
        if parsed_deadline is None:
            await interaction.followup.send(
                "I couldn't understand that deadline. Try a format like 2026-09-15.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        category = guild.get_channel(config.category_id)
        opportunities_channel = guild.get_channel(config.opportunities_channel_id)

        opportunity = await opportunity_service.create_opportunity(
            guild=guild,
            category=category,
            opportunities_channel=opportunities_channel,
            name=self.name.value,
            description=self.description.value,
            link=self.link.value,
            deadline=parsed_deadline,
            created_by=interaction.user.id,
        )

        if opportunity is None:
            await interaction.followup.send(
                "Couldn't create the opportunity — the name might already be taken.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Opportunity **{opportunity.name}** created in <#{opportunity.channel_id}>.",
            ephemeral=True,
        )
