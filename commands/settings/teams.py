import discord
from discord import app_commands
from discord.ext import commands

from resources.exceptions import RoleIsManaged, RoleNotAssignable
from resources.models import Colors, GuildData
from resources.peerless import Peerless
from resources.utils import _, is_managed, operator, send_notice, split_embed_text

@app_commands.guild_only()
class Teams(commands.GroupCog, name="teams"):
    def __init__(self, bot: Peerless):
        self.bot: Peerless = bot
        
    @app_commands.command(name="view", description="view the teams")
    @app_commands.checks.bot_has_permissions(view_channel=True, embed_links=True, attach_files=True)
    @operator()
    async def view(self, interaction: discord.Interaction[Peerless]):
        guild_data: GuildData = interaction.extras['guild_data']
        
        # get the helper commands
        setup_mention  = interaction.client.command_mentions.get("setup", "**/setup**")
        add_mention    = interaction.client.command_mentions.get("teams add", "**/teams add**")
        remove_mention = interaction.client.command_mentions.get("teams remove", "**/teams remove**")
        
        # format the embed
        embed = discord.Embed(
            title = "Teams",
            description = f"`  adding:` {add_mention} or {setup_mention}\n`removing:` {remove_mention}",
            color = (await interaction.client.colorify(interaction.guild.icon)) or Colors.blank,
            timestamp = discord.utils.utcnow()
        )
        
        # get the team roles & emojis and sort them
        teams = [
            (
                interaction.guild.get_role(int(x)), 
                interaction.guild.get_emoji(int(y['emoji']))
            ) for x, y in guild_data.teams.items()
        ]
        teams.sort(reverse=True)
        
        # check if any the roles or emojis dont exist on discord
        for role, emoji in teams:
            if not role or not emoji: # if not found, remove from the database
                guild_data.remove_unused_role(role.id)
        
        # if any of teams were not found, update the database
        if len(teams) != len(guild_data.teams):
            await interaction.client.database.update_guild(guild_data, "teams")
        
        justification = len(str(len(teams) + 1))
        value = ""
        
        # format the embed field
        for i, (role, emoji) in enumerate(teams, 1):
            value += f"`{str(i).rjust(justification)}` | {emoji} {role.mention}\n"
            
        if not value:
            value = f"*no teams available*"
            
        embed.add_field(name="Current Teams", value=value)
        await interaction.response.send_message(
            embed = split_embed_text(embed), 
            ephemeral = True
        )
    
    @app_commands.command(name="add", description="add a team & emoji pair")
    @app_commands.describe(role="the role to pair with the team", emoji="the emoji to pair with the team")
    @app_commands.checks.bot_has_permissions(view_channel=True, embed_links=True, attach_files=True)
    @operator()
    async def add(self, interaction: discord.Interaction[Peerless],
        role: discord.Role,
        emoji: str
    ):
        guild_data: GuildData = interaction.extras['guild_data']
        
        # check if at the maxium amount of teams
        if len(guild_data.teams) > 50:
            return await interaction.response.send_message(
                content=f"<:fail:1136341671857102868>**| You have reached the maximum amount of teams (50)**",
                ephemeral = True
            )
        
        # check if that role ID is used by another setting in the database
        if (used_data := guild_data.find_role(role.id)):
            # not a team role
            if isinstance(used_data, str):
                return await interaction.response.send_message(
                    content = f"<:fail:1136341671857102868>**| That role is already connected to the** `{used_data.replace('_', ' ')}` **role**",
                    ephemeral = True
                )
            else: # is a team role
                emoji = interaction.guild.get_emoji(int(used_data['emoji']))
                
                # if the emoji isn't found on discord, remove it from the database and keep going
                if not emoji:
                    guild_data.remove_unused_role(role.id)
                    await interaction.client.database.update_guild(guild_data, "teams")
                else:
                    return await interaction.response.send_message(
                        content = f"<:fail:1136341671857102868>**| That role is already paired with the {emoji} {role.mention}**",
                        ephemeral = True
                    )
                    
        if is_managed(role):
            raise RoleIsManaged(role)
                    
        if not role.is_assignable():
            raise RoleNotAssignable(role)
        
        # finding the emoji on discord by name or ID
        emoji_split = emoji.split(':')
        if len(emoji_split) != 3:
            emoji = discord.utils.find(lambda e: _(e.name).lower() == _(emoji).lower(), interaction.guild.emojis)
        else:
            emoji_id = ''.join([x for x in emoji_split[2] if x.isdigit()])
            if emoji_id:
                emoji = interaction.guild.get_emoji(int(emoji_id))
        
        # if the emoji wasn't found on discord
        if not emoji:
            return await interaction.response.send_message(
                content = f"<:fail:1136341671857102868>**| I could not find that emoji in this server**",
                ephemeral = True
            )
        
        # check if the emoji is already paired with a team
        matched_team = next((int(x) for x, y in guild_data.teams.items() if int(y.emoji) == emoji.id), None)
        
        if matched_team:
            # if the team isn't found on discord, remove it from the database and keep going
            if not (team := interaction.guild.get_role(matched_team)):
                guild_data.remove_unused_role(team.id)
                await interaction.client.database.update_guild(guild_data, "teams")
            else:
                return await interaction.response.send_message(
                    content = f"<:fail:1136341671857102868>**| That emoji is already paired with the {emoji} {team.mention}**",
                    ephemeral = True
                )
        
        # add the team to the database
        guild_data.teams[str(role.id)] = {
            "emoji": str(emoji.id),
            "division": None,
            "elo": None,
            "opponents": [],
        }
        
        # format the embed
        embed = discord.Embed(
            description = f"**{emoji} {role.mention} has been added to the teams**",
            color = role.color if role.color.value else Colors.blank
        )
        
        # send the message & update the database
        await interaction.response.send_message(embed=embed)
        await interaction.client.database.update_guild(guild_data, "teams")
        
        # send the setting change event
        if guild_data.notices.setting_changes:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### Team Added\n- `role:` {role.mention}\n- ` emoji:` {emoji}",
                color = Colors.orange
            )
            
            await send_notice(interaction, "setting_changes" if guild_data.channels.setting_changes else "notices", embed)
    
    @app_commands.command(name="remove", description="remove a team & emoji pair")
    @app_commands.describe(role="the team to unpair")
    @app_commands.checks.bot_has_permissions(view_channel=True, embed_links=True, attach_files=True)
    @operator()
    async def remove(self, interaction: discord.Interaction[Peerless],
        role: discord.Role,
    ):
        guild_data: GuildData = interaction.extras['guild_data']
        role_id = str(role.id)
        
        # check if the role is a team role
        if role_id not in guild_data.teams:
            return await interaction.response.send_message(
                content = f"<:fail:1136341671857102868>**| That role is already not a team**",
                ephemeral = True
            )
        
        # get the teams emoji
        emoji = interaction.guild.get_emoji(int(guild_data.teams[role_id]['emoji'])) or ""
        
        # remove the team from the database
        guild_data.teams.pop(role_id)
        
        # format the embed
        embed = discord.Embed(
            description = f"**removed the {emoji} {role.mention} from the teams**",
            color = role.color if role.color.value else Colors.blank
        )
        
        # send the message & update the database
        await interaction.response.send_message(embed=embed)
        await interaction.client.database.update_guild(guild_data, "teams")
        
        # send the setting change event
        if guild_data.notices.setting_changes:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### Team Removed\n- `team:` {emoji} {role.mention}",
                color = Colors.orange
            )
            
            await send_notice(interaction, "setting_changes" if guild_data.channels.setting_changes else "notices", embed)
        
async def setup(bot: Peerless):
    cog = Teams(bot)
    
    for command in cog.walk_app_commands():
        if hasattr(command, "callback"):
            setattr(command.callback, "__name__", f"{cog.qualified_name.lower()}_{command.callback.__name__}")
    
    await bot.add_cog(cog)