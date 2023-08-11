from typing import Literal, Optional

import colorlog
import discord
from discord import app_commands
from discord.ext import commands

from resources.peerless import Peerless

logger = colorlog.getLogger('peerless')

async def owner_only(interaction: discord.Interaction[Peerless]):
    return interaction.user.id in [interaction.client.owner_id, 1104883688279384156, 450136921327271946]

@app_commands.guild_only()
class Sync(commands.Cog):
    def __init__(self, bot: Peerless):
        self.bot: Peerless = bot
        
    async def cog_load(self):
        for command in self.get_app_commands():
            if command._guild_ids is None:
                command._guild_ids = []
            
            if self.bot.testing:
                command._guild_ids.append(1122559657899204719)
            else:
                command._guild_ids.append(1105641316433547304)
                
    @app_commands.command(name='extensions', description='(un)load the cogs & (un)sync the commands')
    @app_commands.describe(command="the command to execute", globally="whether to globally (un)sync the commands")
    @app_commands.check(owner_only)
    async def sync(self, interaction: discord.Interaction[Peerless], 
                   command : Literal['load', 'sync', 'load & sync', 'unload', 'unsync'], 
                   globally: Optional[Literal["yes", "no"]]="no"
                ):
        await interaction.response.defer(ephemeral=True)
        
        globally = True if globally == "yes" else False
        log = "Extensions "
        
        try:
            for command in command.split(' & '):
                log += f"{command.title()}ed & "
                
                if command == "load":
                    await self.bot.load_commands()
                
                elif command == "sync":
                    if globally:
                        app_commands = await self.bot.tree.sync()
                    else:
                        self.bot.tree.copy_global_to(guild=interaction.guild)
                        app_commands = await self.bot.tree.sync(guild=interaction.guild)
                        
                    for command in app_commands:
                        if any([x.type == discord.AppCommandOptionType.subcommand for x in command.options]):
                            for subcommand in command.options:
                                self.bot.command_mentions[subcommand.qualified_name] = subcommand.mention
                        else:
                            self.bot.command_mentions[command.name] = command.mention
                        
                elif command == "unload":
                    await self.bot.unload_commands()
                    
                elif command == "unsync":
                    await self.bot.unload_commands()
                    
                    if globally:
                        app_commands = await self.bot.tree.sync()
                    else:
                        app_commands = await self.bot.tree.sync(guild=interaction.guild)
                        
                    await self.bot.load_commands()
        except Exception as e:
            await interaction.followup.send(content="<:fail:1136341671857102868>")
            raise e
        
        logger.info(log[:-3])
        await interaction.followup.send(content="<:success:1136341672918253698>")
        
async def setup(bot: Peerless):
    cog = Sync(bot)
    
    for command in cog.walk_app_commands():
        if hasattr(command, "callback"):
            setattr(command.callback, "__name__", f"{cog.qualified_name.lower()}_{command.callback.__name__}")
            setattr(command, "guild_only", True)
    
    await bot.add_cog(cog)