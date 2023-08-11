import asyncio
import os
import sys

import colorlog
import discord
from colorthief import ColorThief
from discord.app_commands import Command, CommandTree
from discord.ext import commands

from resources.mongodb import Database

intents = discord.Intents().none()
intents.emojis = True
intents.guilds = True
intents.guild_messages = True
intents.members = True

member_cache_flags = discord.MemberCacheFlags().none()
member_cache_flags.joined = True

class Peerless(commands.AutoShardedBot):
    def __init__(self, token: str, testing: bool, fail_to_discord: bool):
        super().__init__(
            tree_cls = PeerlessTree,
            command_prefix = commands.when_mentioned,
            activity = discord.Activity(type=discord.ActivityType.listening, name="/setup"),
            intents = intents,
            member_cache_flags = member_cache_flags,
            max_messages = None,
            chunk_guilds_at_startup = True,
        )
        
        self.token = token
        self.testing  = testing
        self.fail_to_discord = fail_to_discord
        self.fetch_commands_at_startup = not testing
        
        self.database = None
        self.chunking_guilds  = []
        self.command_mentions = {}
        
    async def setup_hook(self) -> None:
        self.database = await Database.init()
        
        await self.load_commands()
        
        logger = colorlog.getLogger('peerless')
        logger.info(f"Logged in - {self.user.name} ({self.application_id})")
        logger.info(f"Loaded {len([x for x in self.tree.walk_commands() if isinstance(x, Command)])} Commands")
        
        if self.fetch_commands_at_startup:
            guild = discord.Object(1122559657899204719)
            for command in await self.tree.fetch_commands(guild=guild):
                if any([x.type == discord.AppCommandOptionType.subcommand for x in command.options]):
                    for subcommand in command.options:
                        self.command_mentions[subcommand.qualified_name] = subcommand.mention
                else:
                    self.command_mentions[command.name] = command.mention
                
            logger.info(f"Retreived {len(self.command_mentions)} Command IDs")
        
    async def load_commands(self):
        self._cogs_ = ["resources.utils"]
              
        try:
            await self.reload_extension(self._cogs_[-1])
        except commands.ExtensionNotLoaded:
            await self.load_extension(self._cogs_[-1])
        
        for dir_, _, files in os.walk('./commands'):
            for file in files:
                if file.endswith('.py'):
                    self._cogs_.append(dir_[2:].replace("\\" if sys.platform == 'win32' else '/', ".") + f".{file[:-3]}")
                    
                    try:
                        await self.reload_extension(self._cogs_[-1])
                    except commands.ExtensionNotLoaded:
                        await self.load_extension(self._cogs_[-1])
                        
    async def unload_commands(self):
        for i in range(0, len(self._cogs_)):
            try:
                await self.unload_extension(self._cogs_[i])
            except commands.ExtensionNotLoaded:
                pass
            
    async def colorify(self, icon: discord.Asset):
        if icon is None:
            return
        
        try:
            file  = await icon.to_file()
            image = ColorThief(file.fp)
            
            return discord.Color.from_rgb(*image.get_color(1))
        except Exception:
            return
            
async def chunk(interaction: discord.Interaction[Peerless]):
    await interaction.guild.chunk()
    interaction.client.chunking_guilds.remove(interaction.guild.id)
            
class PeerlessTree(CommandTree[Peerless]):
    async def get_or_create_user_data(self, user_id: int):
        user_data = await self.client.database.get_user(user_id)

        if user_data is None:
            await self.client.database.create_user(user_id)
            user_data = await self.client.database.get_user(user_id)
                    
        return user_data
    
    async def get_or_create_guild_data(self, guild_id: int):
        guild_data = await self.client.database.get_guild(guild_id)
        
        if guild_data is None:
            await self.client.database.create_guild(guild_id)
            guild_data = await self.client.database.get_guild(guild_id)
            
        return guild_data
    
    async def interaction_check(self, interaction: discord.Interaction[Peerless]) -> bool:
        if interaction.guild.id in interaction.client.chunking_guilds:
            await interaction.response.send_message(content="<:fail:1136341671857102868>**| This server has not been loaded! Please give me some time to load it.**", ephemeral=True)
            return False
        
        if not interaction.guild.chunked:
            interaction.client.chunking_guilds.append(interaction.guild.id)
            await interaction.client.loop.create_task(chunk(interaction))
            
            await interaction.response.send_message(content="<:fail:1136341671857102868>**| This server has not been loaded! Please give me some time to load it.**", ephemeral=True)
            return False
        
        try:
            async with asyncio.timeout(2):
                user_data = await self.get_or_create_user_data(interaction.user.id)
                
                if interaction.guild:
                    guild_data = await self.get_or_create_guild_data(interaction.guild.id)
                        
                    if not user_data.guilds.get(str(interaction.guild.id)):
                        await interaction.client.database.user_guilds_append(user_data, guild_data)
                        
                    interaction.extras['guild_data'] = guild_data
                interaction.extras['user_data'] = {interaction.user.id: user_data}
                
                if interaction.data.get("resolved") and interaction.data['resolved'].get("members"):
                    for user_id, raw_user_data in interaction.data["resolved"]["members"].items():
                        if raw_user_data.get('bot', False):
                            continue
                        
                        user_data = await self.get_or_create_user_data(user_id)
                            
                        if interaction.guild and not user_data.guilds.get(str(interaction.guild.id)):
                            await interaction.client.database.user_guilds_append(user_data, guild_data)
                            
                        interaction.extras['user_data'][int(user_id)] = user_data
                
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if interaction.type in discord.InteractionType.component:
                await interaction.response.defer(thinking=False)
            elif interaction.type == discord.InteractionType.modal_submit:
                await interaction.response.send_message(content=f"<:fail:1136341671857102868>**| Handling the modal took too long. Please try again.**", ephemeral=True)
            else:
                try:
                    mention = self.client.command_mentions.get(interaction.command.qualified_name, None)
                    await interaction.response.send_message(content=f"<:fail:1136341671857102868>**| Preparing the command took too long. {'Click here to try again -> ' + mention if mention else 'Please try again'}.**", ephemeral=True)
                except discord.HTTPException:
                    pass
            
            return False
        
        return True