import ipaddress
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from power import normalize_mac


class OsType(StrEnum):
    linux = "linux"
    windows = "windows"


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str


class HostBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    mac: str
    ip: str = Field(min_length=1, max_length=255)
    ssh_username: str = Field(default="admin", min_length=1, max_length=100)
    os_type: OsType = OsType.linux


class Host(HostBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)


class HostCreate(HostBase):
    """What the client sends when adding a host (validated, unlike table models)."""

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        return normalize_mac(v)

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_address(v.strip()))
        except ValueError as e:
            raise ValueError(f"Invalid IP address: '{v}'") from e


class HostPublic(HostBase):
    id: int


class PowerAction(StrEnum):
    wake = "wake"
    shutdown = "shutdown"


class PowerEvent(SQLModel, table=True):
    """One Wake or Shutdown attempt, successful or not."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # None once the host is removed; host_name keeps the history readable.
    host_id: int | None = Field(default=None, foreign_key="host.id", index=True)
    host_name: str
    action: PowerAction
    success: bool
    detail: str | None = None  # error message when success is False


class PowerEventPublic(SQLModel):
    id: int
    created_at: datetime
    host_id: int | None
    host_name: str
    action: PowerAction
    success: bool
    detail: str | None

    @field_validator("created_at")
    @classmethod
    def as_utc(cls, v: datetime) -> datetime:
        # SQLite drops the timezone; values are stored in UTC, so mark them as such.
        # Then the JSON has a trailing "Z" and the browser converts to local time.
        return v if v.tzinfo else v.replace(tzinfo=UTC)
