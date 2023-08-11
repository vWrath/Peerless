from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from resources.exceptions import RoleIsManaged, RoleNotAssignable, NotEnough
from resources.models import Colors, GuildData
from resources.models import SettingCategories as categories
from resources.peerless import Peerless
from resources.utils import BaseModal, BaseView, is_managed, operator, send_notice, split_embed_text

class SelectSection(BaseView):
    @ui.select(cls=ui.Select, placeholder="select a category to view or edit", options=[
        discord.SelectOption(
            label = "Season Settings", 
            emoji = "<:season:1137914547466948610>", 
            value = "season",
            description = "scheduling type, "
        ),
        discord.SelectOption(
            label = "Role Settings", 
            emoji = "<:roles:1138215660720242778>", 
            value = "roles",
            description = "operator, free agent, eligible, waitlist, and more"
        ),
        discord.SelectOption(
            label = "Channel Settings", 
            emoji = "<:channels:1137915021398114395>", 
            value = "channels",
            description = "transactions, notices, schedule, auto-update, and more"
        ),
        discord.SelectOption(
            label = "Notice Settings", 
            emoji = "<:notices:1137914946106179656>", 
            value = "notices",
            description = "league events, team events, suspensions, and more"
        ),
        discord.SelectOption(
            label = "Status Settings", 
            emoji = "<:status:1137917719694561331>", 
            value = "status",
            description = "turn on/off: transactions, league events, and more"
        ),
        discord.SelectOption(
            label = "Other Settings", 
            emoji = "<:settings:1137914457360695338>", 
            value = "settings",
            description = "roster cap, demands, and waitlist"
        ),
    ])
    async def section_select(self, interaction: discord.Interaction[Peerless], _):
        value: str = self.section_select.values[0].lower()
        view       = None
        
        if value in ['roles', 'channels']:
            view = MentionableOne(interaction, value)
        elif value in ['notices', 'status']:
            view = Flipper(interaction, value)
        elif value == 'settings':
            view = OtherSettings(interaction, value)
            
        if view:
            await interaction.response.send_message(
                content = view.content(interaction), 
                view = view,
                allowed_mentions = discord.AllowedMentions(roles=False),
                ephemeral = True
            )
        else:
            await interaction.response.send_message(content="not completed...", ephemeral=True)
        
class MentionableOne(BaseView):
    def __init__(self, interaction: discord.Interaction[Peerless], category: str):
        super().__init__(120, interaction)
        
        self.category = category
        
        for label, value, description, emoji in categories[category]:
            self.change_or_remove.add_option(label=label, value=value, description=description, emoji=emoji)
        
    def content(self, interaction: discord.Interaction[Peerless]) -> str:
        guild_data: GuildData = interaction.extras['guild_data']
         
        content = f"# {self.category[:-1].title()} Settings\n"
        for label, value, _, _ in categories[self.category]:
            mentionable_id = guild_data[self.category][value]
            
            if not mentionable_id:
                mentionable = ""
            else:
                if self.category == "roles":
                    mentionable = getattr(interaction.guild.get_role(int(mentionable_id)), "mention", "")
                elif self.category == "channels":
                    mentionable = getattr(interaction.guild.get_channel(int(mentionable_id)), "mention", "")
            
            content += f"- **{label}:** {mentionable}\n"
            
        return content
        
    @ui.select(cls=ui.Select, placeholder="select an option to change it or remove it")
    async def change_or_remove(self, interaction: discord.Interaction[Peerless], _):
        option = [x for x in self.change_or_remove.options if x.value == self.change_or_remove.values[0]][0]
        view   = MentionableTwo(interaction, self, self.category, option)
        
        await interaction.response.send_message(content=view.content(), view=view, ephemeral=True)
        
class MentionableTwo(BaseView):
    def __init__(self, interaction: discord.Interaction[Peerless], view_category: BaseView, category: str, option: discord.SelectOption):
        super().__init__(60, interaction)
        
        self.view_category = view_category
        self.category = category
        self.option   = option
        
    def content(self) -> str:
        return f"would you like to **change** or **remove** the `{self.option.label}` {self.category[:-1]}"
    
    @ui.button(label="change")
    async def change(self, interaction: discord.Interaction[Peerless], _):
        self.clear_items()
        
        if self.category == "roles":
            self.mentionable_select = ui.RoleSelect(placeholder=self.category)
            
        elif self.category == "channels":
            self.mentionable_select = ui.ChannelSelect(channel_types=[discord.ChannelType.text], placeholder="channels")
            
        self.mentionable_select.callback = self.change_mentionable
        self.add_item(self.mentionable_select)
        
        try:
            await interaction.response.edit_message(
                content = f"select a {self.category[:-1]} to **set** as the new `{self.option.label}` {self.category[:-1]}", 
                view = self
            )
        except discord.HTTPException:
            pass
    
    async def change_mentionable(self, interaction: discord.Interaction[Peerless]):
        guild_data : GuildData = interaction.extras['guild_data']
        mentionable: app_commands.AppCommandChannel | discord.Role = self.mentionable_select.values[0]
        
        if self.category == "roles":
            mentionable: discord.Role
            
            if (used_data := guild_data.find_role(mentionable.id)):
                # not a team role
                if isinstance(used_data, str):
                    return await interaction.response.send_message(
                        content = f"<:fail:1136341671857102868>**| That role is already connected to the** `{used_data.replace('_', ' ')}` **setting**",
                        ephemeral = True
                    )
                else: # is a team role
                    emoji = interaction.guild.get_emoji(int(used_data['emoji']))
                    
                    # if the emoji isn't found on discord, remove it from the database and keep going
                    if not emoji:
                        guild_data.remove_unused_role(mentionable.id)
                        await interaction.client.database.update_guild(guild_data, "teams")
                    else:
                        return await interaction.response.send_message(
                            content = f"<:fail:1136341671857102868>**| That role is already connected to the {emoji} {mentionable.mention} team**",
                            ephemeral = True
                        )
                        
            if is_managed(mentionable):
                raise RoleIsManaged(mentionable)
                        
            if not mentionable.is_assignable():
                raise RoleNotAssignable(mentionable)
            
        elif self.category == "channels":
            if guild_data[self.category][self.option.value] == str(mentionable.id):
                await interaction.response.send_message(
                    content = f"<:fail:1136341671857102868>**| That is already the** `{self.option.label}` **{self.category[:-1]}**",
                    ephemeral = True
                )
            
            channel: Optional[discord.TextChannel] = mentionable.resolve()
            
            if not channel:
                channel = await interaction.guild.fetch_channel(mentionable.id)
            
            perms  = channel.permissions_for(interaction.guild.me)
            needed = ["view_channel", "send_messages", "embed_links", "attach_files"]
            
            missing = [perm for perm in needed if not getattr(perms, perm)]
            if missing:
                raise app_commands.BotMissingPermissions(missing, channel)
            
            if 'auto update' in self.option.label.lower():
                if self.option.value == 'team_owner_list':
                    if len(guild_data.teams) == 0:
                        raise NotEnough("teams", "teams add")
                    elif len(guild_data.coaches) == 0:
                        raise NotEnough("coaches", "coaches add")
                    
                    team_owners = [(interaction.guild.get_role(int(x)), y) for x, y in guild_data.coaches.items()]
                    
                    for team_owner, abbr in team_owners:
                        if not team_owner:
                            keys = list(guild_data.coaches.keys())
                            vals = list(guild_data.coaches.values())
                            
                            guild_data.remove_unused_role(keys[vals.index(abbr)])
                            
                            if len(guild_data.coaches) == 0:
                                raise NotEnough("coaches", "coaches add")
                            
                    role  = max([x for x in team_owners if x])
                    teams = sorted([
                        (
                            interaction.guild.get_role(int(x)), 
                            interaction.guild.get_emoji(int(y['emoji']))
                        ) for x, y in guild_data.teams.items()
                    ], reverse=True)
        
                    item_list = ""
                    for team, emoji in teams:
                        if not team or not emoji:
                            guild_data.remove_unused_role(team.id)
                            
                            if len(guild_data.teams) == 0:
                                raise NotEnough("teams", "teams add")
                        
                        owner = [x for x in team.members if x in role.members]
                        
                        if owner:
                            item_list += f"{emoji} | {owner[0].mention} `{owner[0].name}`\n"
                        else:
                            team_list += f"{emoji} |\n"
                else:
                    name = self.option.value.removesuffix("_list")
                    
                    # referee, streamer | check if role exists
                    if not guild_data.roles[name]:
                        return await interaction.response.send_message(
                            content = f"<:fail:1136341671857102868>**| There is no {name} role setup**",
                            ephemeral = True,
                        )
                        
                    role = interaction.guild.get_role(int(guild_data.roles[name]))
                    
                    if not role:
                        await interaction.response.send_message(
                            content = f"<:fail:1136341671857102868>**| There is no {name} role setup**",
                            ephemeral = True,
                        )
                        
                        guild_data.remove_unused_role(guild_data.roles[name])
                        await interaction.client.database.update_guild(guild_data, "roles")
                        
                    item_list = ""
                    for member in role.members:
                        item_list += f"{member.mention} `{member.name}`"
                
                embed = discord.Embed(
                    title = f"{role.name}s",
                    description = item_list,
                    color = role.color if role.color.value else Colors.blank,
                    timestamp = discord.utils.utcnow()
                )
                embed.set_footer(text="Last Updated")
                
                await interaction.response.defer()
                
                try:
                    message = await channel.send(embed=embed)
                except discord.HTTPException:
                    return await interaction.response.send_message(
                        content = f"<:fail:1136341671857102868>**| I couldn't send the list into {channel.mention}**",
                        ephemeral = True,
                    )
                    
                guild_data.store[self.option.value + "_message"] = str(message.id)
                    
            mentionable = channel
            
        guild_data[self.category][self.option.value] = str(mentionable.id)
            
        embed = discord.Embed(
            description = f"the `{self.option.label}` {self.category[:-1]} has been **set** to {mentionable.mention} by {interaction.user.mention}",
            color = (await interaction.client.colorify(interaction.guild.icon)) or Colors.blank
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
        
        try:
            await self.view_category.interaction.edit_original_response(content=self.view_category.content(interaction))
        except discord.HTTPException:
            pass
        
        await interaction.client.database.update_guild(guild_data, self.category)
        
        event = "setting_changes"
        if guild_data.notices[event]:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### {self.category.title()}\n- the `{self.option.label}` {self.category[:-1]} has been **set** to {mentionable.mention}",
                color = Colors.orange
            )
            embed.add_field(
                name = "Operator",
                value = f"- {interaction.user.mention} `{interaction.user.name}`"
            )
            
            await send_notice(interaction, event if guild_data.channels[event] else "notices", embed)
        
    @ui.button(label="remove", style=discord.ButtonStyle.red)
    async def remove(self, interaction: discord.Interaction[Peerless], _):
        guild_data: GuildData = interaction.extras['guild_data']
        guild_data[self.category][self.option.value] = None
        
        embed = discord.Embed(
            description = f"the `{self.option.label}` {self.category[:-1]} has been **removed** by {interaction.user.mention}",
            color = (await interaction.client.colorify(interaction.guild.icon)) or Colors.blank
        )
        
        await interaction.response.send_message(embed=embed)
        
        try:
            await self.view_category.interaction.edit_original_response(content=self.view_category.content(interaction))
        except discord.HTTPException:
            pass
        
        await interaction.client.database.update_guild(guild_data, self.category)
        
        event = "setting_changes"
        if guild_data.notices[event]:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### {self.category.title()}\n- the `{self.option.label}` {self.category[:-1]} has been **removed**",
                color = Colors.orange
            )
            embed.add_field(
                name = "Operator",
                value = f"- {interaction.user.mention} `{interaction.user.name}`"
            )
            
            await send_notice(interaction, event if guild_data.channels[event] else "notices", embed)

class Flipper(BaseView):
    def __init__(self, interaction: discord.Interaction[Peerless], category: str):
        super().__init__(120, interaction)
        
        self.category = category
        
        for label, value in categories[category]:
            self.flip.add_option(label=label, value=value)
        
    def content(self, interaction: discord.Interaction[Peerless]) -> str:
        guild_data: GuildData = interaction.extras['guild_data']
         
        content = f"# {self.category.title() if self.category == 'status' else self.category[:-1].title()} Settings\n"
        for label, value in categories[self.category]:
            content += f"- **{label}:** {'<:success:1136341672918253698>' if guild_data[self.category][value] else '<:fail:1136341671857102868>'}\n"
            
        return content
    
    @ui.select(cls=ui.Select, placeholder="select an option to flip its status")
    async def flip(self, interaction: discord.Interaction[Peerless], _):
        guild_data: GuildData = interaction.extras['guild_data']
        
        option  = [x for x in self.flip.options if x.value == self.flip.values[0]][0]
        current = guild_data[self.category][option.value]
        
        guild_data[self.category][self.flip.values[0]] = not current
        
        try:
            await interaction.response.edit_message(content=self.content(interaction))
            await interaction.followup.send(
                content = f"`{option.label.lower()}` have been **{'disabled' if current else 'enabled'}**"
            )
        except discord.HTTPException:
            pass
        
        await interaction.client.database.update_guild(guild_data, self.category)
        
        event = self.category + "_changes" if self.category == "status" else self.category[:-1] + "_changes"
        if guild_data.notices[event]:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### {self.category.title()}\n- `{option.label}` have been **{'disabled' if current else 'enabled'}**",
                color = Colors.green
            )
            
            await send_notice(interaction, event if guild_data.channels[event] else "notices", embed)

class OtherSettings(BaseView):
    def __init__(self, interaction: discord.Interaction[Peerless], category: str):
        super().__init__(120, interaction)
        
        self.category = category
        
        for label, value in categories[category]:
            self.setting.add_option(label=label, value=value)
            
    def content(self, interaction: discord.Interaction[Peerless]) -> str:
        guild_data: GuildData = interaction.extras['guild_data']
         
        content = f"# {self.category[:-1].title()} Settings\n"
        for label, value in categories[self.category]:
            value = guild_data[self.category][value]
            
            if label == "demand-wait":
                content += f"- **{label}:** `{value} days`\n"
            else:
                content += f"- **{label}:** `{value}`\n"
            
        return content
    
    @ui.select(cls=ui.Select, placeholder="select an option to change its setting")
    async def setting(self, interaction: discord.Interaction[Peerless], _):
        option = [x for x in self.setting.options if x.value == self.setting.values[0]][0]
        
        if option.value in ['roster_cap', 'demand_amount']:
            return await interaction.response.send_modal(Number(interaction, self, option))
        
        view = Types(interaction, self, option)
        await interaction.response.send_message(content=view.content(), view=view, ephemeral=True)
        
class Number(BaseModal):
    def __init__(self, interaction: discord.Interaction[Peerless], view: BaseView, option: discord.SelectOption):
        super().__init__("Settings", 60, interaction)
        
        self.view     = view
        self.category = view.category
        self.option   = option
        
        self.number   = ui.TextInput(
            label = f"{option.label}", 
            placeholder = f"type a number between 1-100", 
            min_length = 1, 
            max_length = 3,
        )
        
        self.add_item(self.number)
        
    async def on_submit(self, interaction: discord.Interaction[Peerless]) -> None:
        guild_data: GuildData = interaction.extras['guild_data']
        value: str = self.number.value
        
        if not value.isdigit():
            return await interaction.response.send_message(
                content = f"<:fail:1136341671857102868>**| That was not a number**",
                ephemeral = True
            )
        
        if not 1 < int(value) < 100:
            return await interaction.response.send_message(
                content = f"<:fail:1136341671857102868>**| That was not a number between 1-100**",
                ephemeral = True
            )
            
        guild_data[self.category][self.option.value] = value
        
        embed = discord.Embed(
            description = f"the `{self.option.label}` has been **set** to `{value}` by {interaction.user.mention}",
            color = (await interaction.client.colorify(interaction.guild.icon)) or Colors.blank
        )
            
        await interaction.response.send_message(embed=embed)
        
        try:
            await self.view.interaction.edit_original_response(content=self.view.content(interaction))
        except discord.HTTPException:
            pass
        
        await interaction.client.database.update_guild(guild_data, self.category)
        
        event = "setting_changes"
        if guild_data.notices[event]:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### {self.category.title()}\n- the `{self.option.label}` has been **set** to `{value}`",
                color = Colors.orange
            )
            embed.add_field(
                name = "Operator",
                value = f"- {interaction.user.mention} `{interaction.user.name}`"
            )
            
            await send_notice(interaction, event if guild_data.channels[event] else "notices", embed)

class Types(BaseView):
    def __init__(self, interaction: discord.Interaction[Peerless], view: BaseView, option: discord.SelectOption):
        super().__init__(120, interaction)
        
        self.view     = view
        self.category = view.category
        self.option   = option
        
        for label, value in categories.types[self.option.value]:
            self.new_type.add_option(label=label, value=value)
            
    def content(self) -> str:
        option = self.option.value.split('_')[0]
        return f"select a new type for {'the `' + option if option == 'waitlist' else '`' + option + 's'}`"
    
    @ui.select(cls=ui.Select, placeholder="types")
    async def new_type(self, interaction: discord.Interaction[Peerless], _):
        guild_data: GuildData = interaction.extras['guild_data']
        option = [x for x in self.new_type.options if x.value == self.new_type.values[0]][0]
        
        guild_data[self.category][self.option.value] = option.value
        
        embed = discord.Embed(
            description = f"the `{self.option.label}` has been **set** to `{option.label}` by {interaction.user.mention}",
            color = (await interaction.client.colorify(interaction.guild.icon)) or Colors.blank
        )
            
        await interaction.response.send_message(embed=embed)
        
        try:
            await self.view.interaction.edit_original_response(content=self.view.content(interaction))
        except discord.HTTPException:
            pass
        
        await interaction.client.database.update_guild(guild_data, self.category)
        
        event = "setting_changes"
        if guild_data.notices[event]:
            embed = discord.Embed(
                description = f"*Setting Changed*\n### {self.category.title()}\n- the `{self.option.label}` has been **set** to `{option.label}`",
                color = Colors.orange
            )
            embed.add_field(
                name = "Operator",
                value = f"- {interaction.user.mention} `{interaction.user.name}`"
            )
            
            await send_notice(interaction, event if guild_data.channels[event] else "notices", embed)

class Settings(commands.Cog):
    def __init__(self, bot: Peerless):
        self.bot: Peerless = bot
    
    @app_commands.command(name="settings", description="view or edit settings")
    @app_commands.checks.bot_has_permissions(view_channel=True, embed_links=True, attach_files=True)
    @operator()
    async def settings(self, interaction: discord.Interaction[Peerless]):
        await interaction.response.send_message(
            view = SelectSection(300, interaction), 
            ephemeral = True
        )
        
async def setup(bot: Peerless):
    cog = Settings(bot)
    
    for command in cog.walk_app_commands():
        if hasattr(command, "callback"):
            setattr(command.callback, "__name__", f"{cog.qualified_name.lower()}_{command.callback.__name__}")
    
    await bot.add_cog(cog)