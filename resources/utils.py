import asyncio
from typing import Any, Optional
from unicodedata import normalize

import colorlog
import discord
from discord.interactions import Interaction

from .exceptions import CheckFailure
from .peerless import Peerless

logger = colorlog.getLogger('peerless')

def _(text: str) -> str:
    return normalize("NFKD", text).encode('ascii', 'ignore').decode('utf-8')

class BaseView(discord.ui.View):
    def __init__(self, timeout: int, interaction: Optional[discord.Interaction[Peerless]]=None):
        super().__init__(timeout=timeout)
        
        self.interaction = interaction
        self.check_func  = None
    
    async def interaction_check(self, interaction: Interaction[Peerless]) -> bool:
        if interaction.channel.type == discord.ChannelType.private:
            return True
        
        if not await interaction.client.tree.interaction_check(interaction):
            return False
        
        if self.check_func is not None and asyncio.iscoroutinefunction(self.check_func):
            return await self.check_func
        elif self.interaction.user != interaction.user:
            try:
                await interaction.response.send_message(content="<:fail:1136341671857102868>**| You don't have permission to do that**", ephemeral=True)
            except discord.HTTPException:
                pass
            
            return False
        
        return True
    
    async def on_timeout(self) -> None:
        if not self.interaction:
            return
                
        for child in self.children:
            child.disabled = True
            
        try:
            await self.interaction.edit_original_response(content="**this message has expired**", view=self)
        except discord.HTTPException:
            pass
        
    async def on_error(self, interaction: Interaction[Peerless], error: Exception, _: discord.ui.Item[Any]) -> None:
        return await interaction.client.tree.on_error(interaction, error)
         
class BaseModal(discord.ui.Modal):
    def __init__(self, title: str, timeout: int, interaction: Optional[discord.Interaction[Peerless]]=None):
        super().__init__(title=title, timeout=timeout)
        
        self.interaction = interaction
        
    async def interaction_check(self, interaction: Interaction[Peerless]) -> bool:
        if interaction.channel.type == discord.ChannelType.private:
            return True
        return await interaction.client.tree.interaction_check(interaction)
        
    async def on_timeout(self) -> None:
        if not self.interaction:
            return
        
        embed = discord.utils.MISSING
        if self.interaction.message and len(self.interaction.message.embeds):
            embed = self.interaction.message.embeds[0]
            
            if not embed.footer or not embed.footer.text:
                embed.set_footer(text="")
            else:
                embed = discord.utils.MISSING
                
        for child in self.children:
            child.disabled = True
            
        try:
            await self.interaction.edit_original_response(view=self, embed=embed)
        except discord.HTTPException:
            pass
        
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.client.tree.on_error(interaction, error)
           
def operator():
    def pred(interaction: discord.Interaction[Peerless]):
        if interaction.user.guild_permissions.administrator:
            return True
        
        guild_data = interaction.extras["guild_data"]
        
        if not guild_data.roles.operator:
            raise CheckFailure("operator")
        if not interaction.user.get_role(int(guild_data.roles.operator)):
            raise CheckFailure("operator")
        
        return True
        
    return discord.app_commands.check(pred)
            
async def send_notice(
    interaction: discord.Interaction[Peerless], 
    event: str, 
    embed: discord.Embed,
    checked_events: Optional[list]=[]
):
    checked_events.append(event)
    guild_data = await interaction.client.database.get_guild(interaction.guild.id)
    
    if guild_data.channels[event] is None:
        if guild_data.store[event + "_webhook"]:
            guild_data.store[event + "_webhook"] = None
            await interaction.client.database.update_guild(guild_data, "store")
        
        return
    
    event_channel = interaction.guild.get_channel(int(guild_data.channels[event]))
    
    if not event_channel or event_channel.type != discord.ChannelType.text:
        if guild_data.store[event + "_webhook"]:
            guild_data.store[event + "_webhook"] = None
            await interaction.client.database.update_guild(guild_data, "store")
            
        guild_data.channels[event] = None
        return await interaction.client.database.update_guild(guild_data, "channels")
    
    webhook = None
    
    if guild_data.store[event + "_webhook"]:
        webhook = discord.Webhook.partial(
            *guild_data.store[f"{event}_webhook"].split(":"), 
            client=interaction.client, 
            bot_token=interaction.client.token
        )
        
    if not webhook:
        for evnt, channel in guild_data.channels.items():
            if evnt not in checked_events and str(event_channel.id) == channel:
                return await send_notice(interaction, evnt, embed, checked_events)
            
        if len(checked_events) > 1:
            event = checked_events[0]
            
        perms = event_channel.permissions_for(interaction.guild.me)
        
        if not perms.manage_webhooks:
            return await interaction.followup.send(content=f"<:fail:1136341671857102868>**| I tried to send a notice, but I don't have the permission,** `manage webhooks`**, for the channel** {event_channel.mention}")
            
        try:
            webhook = await event_channel.create_webhook(name="Peerless Notices", avatar=await interaction.client.user.display_avatar.read(), reason="used for notices")
        except discord.HTTPException as e:
            return logger.error(f"Failed to create a notice webhook in guild, {interaction.guild.id}. ({e.text})")
        
        guild_data.store[f"{event}_webhook"] = f"{webhook.id}:{webhook.token}"
        await interaction.client.database.update_guild(guild_data, "store")
        
    try:
        await webhook.send(embed=embed)
    except discord.NotFound:
        guild_data.store[event + "_webhook"] = None
        await interaction.client.database.update_guild(guild_data, "store")
        
        await send_notice(interaction, event, embed, checked_events)
    except discord.Forbidden:
        await interaction.followup.send(
            content=f"<:fail:1136341671857102868>**| Unexpected error while trying to send a notice**"
        )
        
        logger.error(f"Failed to send a notice in guild, {interaction.guild.id}. ({e.text})")
    except discord.HTTPException as e:
        logger.error(f"Failed to send a notice in guild, {interaction.guild.id}. ({e.text})")
    
def split_embed_text(embed: discord.Embed, separator: Optional[str]="\n"):
    if len(embed.description) > 2000:
        description = embed.description.split(separator)
        
        if len(description) == 1:
            embed.insert_field_at(0, name="\u2063", value=embed.description[2000:], inline=False)
            embed.description = embed.description[:2000]
        else:
            current_text = ""
            for c in range(len(description)):
                if len(current_text) + len(description[c]) + len(separator) < 2000:
                    current_text += f"{description[c]}{separator}"
                else:
                    embed.description = current_text.strip()
                    current_text = f"{description[c]}{separator}"
                    
                    embed.insert_field_at(0, name="\u2063", value=separator.join(description[c:]), inline=False)
                    break
    
    for field in embed.fields:
        index  = embed.fields.index(field)
        values = []
        text   = field.value.split(separator)
        
        if len(text) == 1:
            values = [text[0][i:i + 1024] for i in range(0, len(text[0]), 1024)]
        else:
            current_text = ""
            for char in text:
                if len(current_text) + len(char) + len(separator) < 1024:
                    current_text += f"{char}{separator}"
                else:
                    values.append(current_text.strip())
                    current_text = f"{char}{separator}"
                    
            if current_text:
                values.append(current_text)
        
        embed.set_field_at(index, name=field.name, value=values[0], inline=False if len(values) > 1 else field.inline)
        
        if len(values) > 1:
            for i in range(1, len(values)):
                embed.insert_field_at(index + i, name="\u2063", value=values[i], inline=False)
                
    return embed

def is_managed(role: discord.Role):
    if role.managed:
        return True
    elif role.is_default():
        return True
    elif not role.tags:
        return False
    
    elif role.tags.is_bot_managed():
        return True
    elif role.tags.is_premium_subscriber():
        return True
    elif role.tags.is_integration():
        return True
    elif role.tags.is_available_for_purchase():
        return True
    elif role.tags.is_guild_connection():
        return True
    
    else:
        return False

async def setup(_):
    pass