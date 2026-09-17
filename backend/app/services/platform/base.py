from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class PlatformName(str, Enum):
    TELEGRAM = "telegram"
    FACEBOOK = "facebook"
    ZALO = "zalo"


@dataclass
class AccountCredentials:
    platform: PlatformName
    username: str
    credentials: dict = field(default_factory=dict)


@dataclass
class GroupInfo:
    group_id: str
    name: str
    member_count: int = 0
    description: str = ""
    platform: PlatformName = PlatformName.TELEGRAM


@dataclass
class UserProfile:
    user_id: str
    display_name: str
    username: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    is_online: bool = False
    last_seen: str | None = None


@dataclass
class MessageContent:
    text: str
    language: str = "vi"
    media_path: str | None = None


@dataclass
class AccountHealthStatus:
    status: str  # green / yellow / red / black
    daily_actions: int = 0
    error_rate: float = 0.0
    last_error: str | None = None


MessageCallback = callable


class PlatformAdapter(ABC):
    @abstractmethod
    async def authenticate(self, credentials: AccountCredentials) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def search_groups(self, query: str, limit: int = 10) -> list[GroupInfo]:
        ...

    @abstractmethod
    async def join_group(self, group_id: str) -> bool:
        ...

    @abstractmethod
    async def send_friend_request(self, user_id: str) -> bool:
        ...

    @abstractmethod
    async def send_message(self, target_id: str, content: MessageContent) -> bool:
        ...

    @abstractmethod
    async def listen_messages(self, callback: MessageCallback) -> None:
        ...

    @abstractmethod
    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        ...

    @abstractmethod
    async def get_group_members(self, group_id: str, limit: int = 100) -> list[UserProfile]:
        ...

    @abstractmethod
    def get_health_status(self) -> AccountHealthStatus:
        ...
