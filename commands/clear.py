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
class Clear(commands.Cog):
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
                
    @app_commands.command(name='clear', description='clears the redis cache')
    @app_commands.check(owner_only)
    async def redis_cache(self, interaction: discord.Interaction[Peerless]):
        await interaction.response.defer(ephemeral=True)
        await interaction.client.database.redis.flushall(asynchronous=True)
        await interaction.followup.send(content="<:success:1136341672918253698>")
        
async def setup(bot: Peerless):
    cog = Clear(bot)
    
    for command in cog.walk_app_commands():
        if hasattr(command, "callback"):
            setattr(command.callback, "__name__", f"{cog.qualified_name.lower()}_{command.callback.__name__}")
            setattr(command, "guild_only", True)
    
    await bot.add_cog(cog)