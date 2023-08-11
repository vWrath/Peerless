import datetime
from dataclasses import dataclass, field
from enum import Enum, _is_dunder
from typing import Any, Dict, List, Optional

class BaseData:
    def regular(self):
        raise NotImplementedError()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.regular()})"
    
    __str__ = __repr__

class DataObject(BaseData, dict):
    def __init__(self, data: Dict[str, Any]):
        if isinstance(data, DataObject):
            data = data.regular()
            
        for key, val in data.items():
            if isinstance(val, dict):
                data[key] = DataObject(val)
            elif isinstance(val, list):
                data[key] = DataArray(val)
            elif isinstance(val, str):
                try:
                    data[key] = datetime.datetime.fromisoformat(val)
                except ValueError:
                    pass
        
        super().__init__(data)
        
    def __getattr__(self, __key: Any) -> Any:
        return self.get(__key, None)
    
    def __setattr__(self, __name: str, __value: Any) -> None:
        self[__name] = __value
        
    def __delattr__(self, __name: str) -> None:
        del self[__name]
       
    def __getitem__(self, __key: Any) -> Any:
        try:
            return super().__getitem__(__key)
        except KeyError:
            return
        
    def has(self, __key) -> bool:
        return __key in self.keys()
        
    def regular(self):
        return {
            key: val.regular() if isinstance(val, (DataObject, DataArray))
            else val.isoformat() if isinstance(val, datetime.datetime)
            else val for key, val in self.items()
        }
    
class DataArray(BaseData, list):
    def __init__(self, array: List[Any]):
        for i in range(len(array)):
            if isinstance(array[i], dict):
                array[i] = DataObject(array[i])
            elif isinstance(array[i], list):
                array[i] = DataArray(array[i])
            elif isinstance(array[i], str):
                try:
                    array[i] = datetime.datetime.fromisoformat(array[i])
                except ValueError:
                    pass
        
        super().__init__(array)
        
    def regular(self):
        return [
            x.regular() if isinstance(x, (DataObject, DataArray)) 
            else x.isoformat() if isinstance(x, datetime.datetime)
            else x for x in self
        ]
    
def default_object(obj={}):
    return field(default_factory=lambda: DataObject(obj))

def default_array(arr=[]):
    return field(default_factory=lambda: DataArray(arr))
    
@dataclass
class GuildData():
    _id: str
    
    settings: Optional[DataObject] = default_object({
        "roster_cap": "20",
        "demand_type": "amount",
        "demand_amount": "3",
        "demand_wait": "7",
        "waitlist_type": "queue",
    })
    channels   : Optional[DataObject] = default_object()
    roles      : Optional[DataObject] = default_object()
    store      : Optional[DataObject] = default_object()
    
    notices: Optional[DataObject] = default_object({
        "appoints": True,
        "notice_changes": True,
        "player_demand": True,
        "player_demand_dm": True,
        "player_leave": True,
        "player_leave_dm": True,
        "setting_changes": True,
        "status_changes": True,
        "stat_updates": True,
        "suspensions": True,
        "team_disband": True,
        "team_owner_leave": True,
        "team_swap": True,
    })
    status: Optional[DataObject] = default_object({
        "contracts": True,
        "demands": True,
        "demoting": True,
        "offering": True,
        "promoting": True,
        "releasing": True,
        "scheduling": True,
        "signing": True,
        "standings": True,
        "statistics": True,
        "waitlist": True,
    })
    
    waitlist   : Optional[DataArray] = default_array()
    blacklist  : Optional[DataArray] = default_array()
    statsheets : Optional[DataArray] = default_array([
        {key: {"url": None, "players": []} for key in ["passer", "runner", "receiver", "corner", "defender", "kicker"]}
    ])
    
    teams      : Optional[DataObject] = default_object() # 0-50
    coaches    : Optional[DataObject] = default_object() # 0-5
    
    season     : Optional[DataArray]  = default_object({"week": "1"})
    awards     : Optional[DataObject] = default_object()
    games      : Optional[DataObject] = default_object()
    
    def __post_init__(self):
        self.id = int(self._id)
        
    def find_role(self, role_id: int) -> Optional[dict | str]:
        role_id = str(role_id)
        
        if role_id in self.teams.keys():
            return self.teams[role_id]
        
        if role_id in self.coaches.keys():
            return self.coaches[role_id]
        
        if role_id in self.roles.values():
            keys = list(self.roles.keys())
            vals = list(self.roles.values())
            
            return keys[vals.index(role_id)]
        
    def remove_unused_role(self, role_id: int):
        role_id = str(role_id)
        
        if role_id in self.teams:
            del self.teams[role_id]
        
        elif role_id in self.coaches:
            del self.coaches[role_id]
        
        elif role_id in self.roles:
            keys = list(self.coaches.keys())
            vals = list(self.coaches.values())
            
            key = keys[vals.index(role_id)]
            del self.roles[key]
            
    def __getitem__(self, __key):
        return self.__getattribute__(__key)
        
@dataclass
class UserData:
    _id: int
    guilds: Optional[DataObject] = default_object()
    
    def __post_init__(self):
        self.id = int(self._id)
        
class Colors:
    red    = 0xFF2323
    orange = 0xFF924F
    yellow = 0xFFDA4F
    green  = 0x7FFF6D
    blue   = 0x6DA7FF
    purple = 0xA984FF
    pink   = 0xFF84FD
    white  = 0xFFFFFF
    black  = 0x010101
    blank  = 0x2B2D31
    
class GetItem(type):
    def __getitem__(cls, key: str):
        return cls.__dict__[key]
    
class SettingCategories(metaclass=GetItem):
    roles = [
        ("free agent", "free_agent", "🛒"),
        ("operator", "operator", "🏗️"),
        ("pickups host/captain", "pickups_host", "👔"),
        ("pickups ping", "pickups_ping", "🏈"),
        ("referee", "referee", "⚖️"),
        ("statisician", "statisician", "📝"),
        ("streamer", "streamer", "🎥"),
        ("suspended", "suspended", "⛔"),
        ("verified/eligible", "eligible", "✅"),
        ("waitlist", "waitlist", "⏰"),
    ]
    channels = [
        ("auto update-referee list", "referee_list", "⚖️"),
        ("auto update-streamer list", "streamer_list", "🎥"),
        ("auto update-teams owner list", "team_owner_list", "👔"),
        ("challenges", "challenges", "⚠️"),
        ("contracts", "contracts", "📋"),
        ("decisions", "decisions", "🧠"),
        ("demands", "demands", "🐍"),
        ("scheduled games (gametime)", "scheduled_games", "🕒"),
        ("lfp", "lfp", "👀"),
        ("notices", "notices", "🔔"),
        ("notice changes", "notice_changes", "‼️"),
        ("pickups", "pickups", "🏈"),
        ("re-scheduled games (gametime)", "rescheduled_games", "🕖"),
        ("schedule", "schedule", "📅"),
        ("setting changes", "setting_changes", "⚙️"),
        ("standings", "standings", "🏆"),
        ("stat updates", "stat_updates", "📝"),
        ("status changes", "status_changes", "🚥"),
        ("suspensions & unsuspensions", "suspensions", "⛔"),
        ("transactions", "transactions", "💵"),
        ("waitlist pinging", "waitlist_pinging", "⏰"),
    ]
    notices = [
        ("appoints", "appoints"),
        ("notice changes", "notice_changes"),
        ("player demand", "player_demand"),
        ("player demand (DM)", "player_demand_dm"),
        ("player leave", "player_leave"),
        ("player leave (DM)", "player_leave_dm"),
        ("setting changes", "setting_changes"),
        ("status changes", "status_changes"),
        ("stat updates", "stat_updates"),
        ("suspensions & unsuspensions", "suspensions"),
        ("team disband", "team_disband"),
        ("team owner leave", "team_owner_leave"),
        ("team swap", "team_swap"),
    ]
    status = [
        ("contracts", "contracts"),
        ("demands", "demands"),
        ("demoting", "demoting"),
        ("offering", "offering"),
        ("promoting", "promoting"),
        ("releasing", "releasing"),
        ("scheduling", "scheduling"),
        ("signing", "signing"),
        ("standings", "standings"),
        ("statistics", "statistics"),
        ("waitlist", "waitlist"),
    ]
    settings = [
        ("roster cap", "roster_cap"),
        ("demand-type", "demand_type"),
        ("demand-amount", "demand_amount"),
        ("demand-wait", "demand_wait"),
        ("waitlist-type", "waitlist_type"),
    ]
    types = {
        "demand_type": [("amount", "amount"), ("wait", "wait")],
        "demand_wait": [(f"{i} days", str(i)) for i in range(1, 15)],
        "waitlist_type": [("ping", "ping"), ("queue", "queue")],
    }