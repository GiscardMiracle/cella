"""
Cella bot - 2026
Permissions utility functions for managing roles and channel access in Discord.
Author: Giscard Adjanon
"""

from typing import Optional

import discord

async def create_opportunity_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    try:
        # Check if the role already exists
        existing_role = discord.utils.get(guild.roles, name=name)
        if existing_role:
            return existing_role

        new_role = await guild.create_role(name=name)
        return new_role
    except discord.Forbidden:
        print("Cella does not have permission to create roles.")
        return None
    except Exception as e:
        print(f"Error occurred while creating role: {e}")
        return None

async def setup_channel_permissions(channel: discord.TextChannel, role: discord.Role):
    try:
        everyone_overwrite = discord.PermissionOverwrite()
        everyone_overwrite.view_channel = False

        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = True
        overwrite.send_messages = True

        await channel.set_permissions(role, overwrite=overwrite)
        await channel.set_permissions(channel.guild.me, overwrite=overwrite)
        await channel.set_permissions(channel.guild.default_role, overwrite=everyone_overwrite)
        return True
    except discord.Forbidden:
        print("Cella does not have permission to set channel permissions.")
        return False
    except Exception as e:
        print(f"Error occurred while setting channel permissions: {e}")
        return False

async def grant_bot_access(channel: discord.TextChannel):
    try:
        overwrite = discord.PermissionOverwrite()
        overwrite.view_channel = True
        overwrite.send_messages = True
        overwrite.read_message_history = True
        await channel.set_permissions(channel.guild.me, overwrite=overwrite)
        return True
    except discord.Forbidden:
        print(f"Cella does not have permission to grant itself access to {channel}.")
        return False
    except Exception as e:
        print(f"Error occurred while granting the bot access to {channel}: {e}")
        return False

async def grant_access(member: discord.Member, role: discord.Role):
    try:
        await member.add_roles(role)
        return True
    except discord.Forbidden:
        print(f"Cella does not have permission to add roles to {member}.")
        return False
    except Exception as e:
        print(f"Error occurred while granting access to {member}: {e}")
        return False

async def revoke_access(member: discord.Member, role: discord.Role):
    try:
        await member.remove_roles(role)
        return True
    except discord.Forbidden:
        print(f"Cella does not have permission to remove roles from {member}.")
        return False
    except Exception as e:
        print(f"Error occurred while revoking access from {member}: {e}")
        return False
