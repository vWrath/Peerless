import discord

class PeerlessException(Exception):
    pass

class CheckFailure(discord.app_commands.CheckFailure):
    def __init__(self, check: str):
        self.check = check

class RoleNotAssignable(PeerlessException):
    def __init__(self, role: discord.Role):
        self.role = role
        
class RoleIsManaged(PeerlessException):
    def __init__(self, role: discord.Role):
        self.role = role
        
class NotEnough(PeerlessException):
    def __init__(self, key: str, command_qual_name: str):
        self.key = key
        self.command_qual_name = command_qual_name