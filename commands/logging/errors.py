import io
import traceback
from os import environ as env
from typing import Literal, Optional

import colorlog
import discord
from discord import app_commands
from discord.ext import commands

from resources.exceptions import CheckFailure, RoleIsManaged, RoleNotAssignable, NotEnough
from resources.models import Colors
from resources.peerless import Peerless

logger = colorlog.getLogger('peerless')
FAIL_WEBHOOK = env['FAIL_LOG_WEBHOOK']

class Logger(commands.Cog):
    def __init__(self, bot: Peerless):
        self.bot: Peerless = bot
        self.bot.tree.on_error = self.app_command_error
        
    async def app_command_error(self, interaction: discord.Interaction[Peerless], error: Exception):
        kwargs = None
        
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.__cause__
            
        if isinstance(error, RoleNotAssignable):
            kwargs = {
                "content": f"<:fail:1136341671857102868>**| I can't assign that role! Please drag {interaction.guild.self_role.mention} above {error.role.mention}**\n- *view the picture below on what to do*",
                "file": discord.File(fp="./resources/files/drag.png", description="how to drag a role"),
                "allowed_mentions": discord.AllowedMentions(roles=False),
                "ephemeral": True
            }
        elif isinstance(error, RoleIsManaged):
            kwargs = {
                "content": f"<:fail:1136341671857102868>**| That role is already managed by a bot, this server, discord, or an external application**",
                "ephemeral": True,
            }
        elif isinstance(error, NotEnough):
            mention = interaction.client.command_mentions.get(
                error.command_qual_name, 
                f"**the command ->** `/{error.command_qual_name}`"
            )
            
            kwargs = {
                "content": f"<:fail:1136341671857102868>**| There is no {error.key} available. In order to add more {error.key}, run** {mention}",
                "ephemeral": True,
            }
        
        elif isinstance(error, app_commands.BotMissingPermissions):
            kwargs = {}
            
            if len(error.args) > 1 and isinstance(error.args[1], discord.TextChannel):
                channel = error.args[1]
                
                embed = discord.Embed(
                    title = "Missing Permissions",
                    description = f"i need the following permissions in the channel, {channel.mention}: **{', '.join(error.missing_permissions)}**",
                    color = Colors.red,
                )
                
                kwargs["ephemeral"] = True
            else:
                embed = discord.Embed(
                    title = "Missing Permissions",
                    description = f"i need the following permissions to run this command: **{', '.join(error.missing_permissions)}**",
                    color = Colors.red
                )
            
            kwargs["embed"] = embed
        elif isinstance(error, CheckFailure):
            if error.check == "operator":
                guild_data = interaction.extras['guild_data']
                operator   = guild_data.roles.operator
                
                if not operator:
                    operator = "not setup"
                else:
                    operator = getattr(interaction.guild.get_role(int(guild_data.roles.operator)), "mention", "not setup")
                
                kwargs = {
                    "content": f"<:fail:1136341671857102868>**| You need to have the administrator permission or have the operator role ({operator})**",
                    "ephemeral": True,
                    "allowed_mentions": discord.AllowedMentions(roles=False)
                }
        
        if kwargs:
            if interaction.response.is_done():
                return await interaction.followup.send()
            return await interaction.response.send_message(**kwargs)
        elif self.bot.fail_to_discord:
            return await self.fail(message="", error_class=error.__class__, error=error, tb=error.__traceback__, interaction=interaction)
        else:
            raise error
        
    @commands.Cog.listener(name="on_fail")
    async def fail(self, message: str, error_class, error: Exception, tb, interaction: Optional[discord.Interaction[Peerless]]=None):
        if tb is None:
            return
        
        try:
            webhook = discord.Webhook.from_url(FAIL_WEBHOOK, client=self.bot)
            
            tb = ''.join(traceback.format_exception(error_class, error, tb))
            
            if len(tb) > 1700:
                f = discord.File(io.StringIO(tb), filename="error.txt")
                await webhook.send(content=f"<t:{int(discord.utils.utcnow().timestamp())}:f>", file=f)
            else:
                await webhook.send(content=f"<t:{int(discord.utils.utcnow().timestamp())}:f>\n\n```python\n{tb}```")
        except Exception as e:
            logger.error(str(e))
                
async def setup(bot: Peerless):
    await bot.add_cog(Logger(bot))