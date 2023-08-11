from json import dumps, loads
from os import environ as env
from typing import Any, Dict, Optional, Self

import colorlog
import redis.asyncio as redis
from discord.utils import utcnow
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from .models import DataArray, DataObject, GuildData, UserData

MONGODB_URL = env['MONGODB_URL']
logger      = colorlog.getLogger("mongodb")

class Database:
    def __init__(self) -> None:
        self.client   = AsyncIOMotorClient(MONGODB_URL, tz_aware=True)
        self.database = self.client.peerless
        self.guilds   = self.database.guilds
        self.users    = self.database.users
        
        self.redis: Optional[redis.Redis] = None
    
    @classmethod
    async def init(cls: Self) -> Self:
        self = cls()
        
        try:
            self.redis = redis.Redis()
            await self.redis.ping()
            await self.redis.flushdb()
            
            logger.info("Connected to Redis")
        except redis.ConnectionError:
            return logger.error("Couldn't connect to Redis! You probably need to start the server.")
        
        return self
    
    async def close(self):
        if self.redis:
            await self.redis.close()
    
    async def get_redis(self, key: str):
        base_data = await self.redis.hgetall(key)
        
        if base_data:
            data = {}
            for key, val in base_data.items():
                loaded = loads(val.decode())
                
                if isinstance(loaded, dict):
                    data[key.decode()] = loaded
                else:
                    data[key.decode()] = val.decode()
            
            base_data = data
        return base_data
        
    async def set_redis(self, key: str, data: Dict[str, Any]):
        data.pop('_id', None)
        
        category, _id = tuple(key.split(':'))
        logger.debug(f"Cached new data for {category.title()} ID, {_id}")
        
        if self.redis is not None:
            data = {k: dumps(v) if isinstance(v, dict) else v for k, v in DataObject(data).regular().items()} or {'settings': "{}"}
            await self.redis.hset(key, mapping=data)
            
    async def update_redis(self, key: str, category: str, data: Dict[str, Any]):
        data.pop('_id', None)
        
        db, _id = tuple(key.split(':'))
        logger.debug(f"Updated cache data for {db.title()} ID, {_id}")
        
        if self.redis is not None:
            json_data = dumps(DataObject(data).regular())
            await self.redis.hset(key, category, json_data)
        
    async def get_guild(self, guild_id: int, fetch: Optional[bool]=False):
        guild_data = None
        
        if not fetch and self.redis is not None:
            guild_data = await self.get_redis(f"guild:{guild_id}")
            
            if len(guild_data) == 0:
                guild_data = None
            
            if guild_data is not None:
                logger.debug(f"Retreived Guild ID, {guild_id}, from Redis Cache")
                
        if fetch or guild_data is None:
            guild_data = await self.guilds.find_one({'_id': str(guild_id)})
            
            if guild_data is None:
                return
            
            logger.debug(f"Retreived Guild ID, {guild_id}, from MongoDB")
            await self.set_redis(f"guild:{guild_id}", guild_data)
        
        for key, val in guild_data.items():
            if isinstance(val, dict):
                guild_data[key] = DataObject(val)
            elif isinstance(val, list):
                guild_data[key] = DataArray(val)
                
        return GuildData(_id=str(guild_id), **guild_data)
        
    async def create_guild(self, guild_id: int):
        try:
            await self.guilds.insert_one({'_id': str(guild_id)})
        except DuplicateKeyError:
            return logger.error(f"Duplicate Key for Guild ID, {guild_id}")
        
        await self.set_redis(f"guild:{guild_id}", {"settings": {}})
        
    async def update_guild(self, guild_data: GuildData, category: str, *, unset: bool=False):
        new_data = getattr(guild_data, category).regular()
        
        await self.guilds.update_one(
            {'_id': guild_data._id},
            {f"$set": {category: {}}} if unset else {f"$set": {category: new_data}}
        )
        
        if unset:
            await self.update_redis(f"guild:{guild_data._id}", category, {})
        else:
            await self.update_redis(f"guild:{guild_data._id}", category, new_data)
            
    async def get_user(self, user_id: int, fetch: Optional[bool]=False):
        user_data = None
        
        if not fetch and self.redis is not None:
            user_data = await self.get_redis(f"user:{user_id}")
            
            if len(user_data) == 0:
                user_data = None
            
            if user_data is not None:
                logger.debug(f"Retreived User ID, {user_id}, from Redis Cache")
                
        if fetch or user_data is None:
            user_data = await self.users.find_one({'_id': str(user_id)})
            
            if user_data is None:
                return
            
            logger.debug(f"Retreived User ID, {user_id}, from MongoDB")
            await self.set_redis(f"user:{user_id}", user_data)
        
        for key, val in user_data.items():
            if isinstance(val, dict):
                user_data[key] = DataObject(val)
            elif isinstance(val, list):
                user_data[key] = DataArray(val)
                
        return UserData(_id=str(user_id), **user_data)
    
    async def create_user(self, user_id: int):
        try:
            await self.users.insert_one({'_id': str(user_id)})
        except DuplicateKeyError:
            return logger.error(f"Duplicate Key for User ID, {user_id}")
        
        await self.set_redis(f"user:{user_id}", {"guilds": {}})
        
    async def update_user(self, user_data: UserData, category: str, *, unset: bool=False):
        new_data = getattr(user_data, category).regular()
        
        await self.users.update_one(
            {'_id': user_data._id},
            {f"$set": {category: {}}} if unset else {f"$set": {category: new_data}}
        )
        
        if unset:
            await self.update_redis(f"user:{user_data._id}", category, {})
        else:
            await self.update_redis(f"user:{user_data._id}", category, new_data)
            
    async def user_guilds_append(self, user: UserData, guild: GuildData):
        user.guilds[str(guild.id)] = {
            "demands_remaining": str(guild.settings.demand_amount or 3),
            "demands_wait_time": utcnow(),
            "suspension": {
                "suspended_until" : None,
                "banned_until"    : None
            },
            "contract": {
                "role_id": None,
                "terms"  : None,
            }
        }
        
        await self.update_user(user, "guilds")
        
    async def user_guilds_remove(self, user: UserData, guild: GuildData):
        del user.guilds[str(guild.id)]
        await self.update_user(user, "guilds")