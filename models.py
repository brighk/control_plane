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


class HostPublic(HostBase):
    id: int
