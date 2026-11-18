from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import Session, col, select, update

from auth import CurrentUser
from config import SSH_KEY_PATH
from db import SessionDep
from models import (
    Host,
    HostCreate,
    HostPublic,
    PowerAction,
    PowerEvent,
    PowerEventPublic,
    User,
)
from power import is_host_up, shutdown_now, wake_on_call

router = APIRouter(prefix="/api/hosts", tags=["hosts"])
events_router = APIRouter(prefix="/api/events", tags=["events"])


def get_owned_host(host_id: int, user: CurrentUser, session: SessionDep) -> Host:
    host = session.get(Host, host_id)
    # 404 (not 403) for other users' hosts, so IDs don't leak which hosts exist.
    if host is None or host.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Host not found")
    return host


def record_event(
    session: Session,
    user: User,
    host: Host,
    action: PowerAction,
    success: bool,
    detail: str | None = None,
) -> None:
    assert user.id is not None
    session.add(
        PowerEvent(
            user_id=user.id,
            host_id=host.id,
            host_name=host.name,
            action=action,
            success=success,
            detail=detail,
        )
    )
    session.commit()


@router.get("", response_model=list[HostPublic])
def list_hosts(user: CurrentUser, session: SessionDep):
    return session.exec(
        select(Host).where(Host.owner_id == user.id).order_by(Host.name)
    ).all()


@router.post("", response_model=HostPublic, status_code=status.HTTP_201_CREATED)
def add_host(data: HostCreate, user: CurrentUser, session: SessionDep):
    assert user.id is not None
    host = Host.model_validate(data, update={"owner_id": user.id})
    session.add(host)
    session.commit()
    session.refresh(host)
    return host


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_host(host_id: int, user: CurrentUser, session: SessionDep) -> None:
    host = get_owned_host(host_id, user, session)
    # Detach its history first: SQLite can reuse a deleted host's id, and old
    # events must not end up pointing at a new host.
    session.exec(
        update(PowerEvent)
        .where(col(PowerEvent.host_id) == host.id)
        .values(host_id=None)
    )
    session.delete(host)
    session.commit()


# Plain `def` (not `async def`): these block on sockets/SSH,
# so FastAPI runs them in a threadpool instead of blocking the event loop.
@router.post("/{host_id}/wake")
def wake(host_id: int, user: CurrentUser, session: SessionDep):
    host = get_owned_host(host_id, user, session)
    try:
        wake_on_call(host.mac)
    except OSError as e:
        record_event(session, user, host, PowerAction.wake, False, str(e))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Wake failed: {e}")
    record_event(session, user, host, PowerAction.wake, True)
    return {"status": f"Wake packet sent to {host.name}"}


@router.post("/{host_id}/shutdown")
def shutdown(host_id: int, user: CurrentUser, session: SessionDep):
    host = get_owned_host(host_id, user, session)
    if not SSH_KEY_PATH:
        detail = "Server has no SSH key configured (set CONTROL_PLANE_SSH_KEY)"
        record_event(session, user, host, PowerAction.shutdown, False, detail)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)
    try:
        shutdown_now(
            ip=host.ip,
            key_path=SSH_KEY_PATH,
            username=host.ssh_username,
            os_type=host.os_type,
        )
    except Exception as e:
        record_event(session, user, host, PowerAction.shutdown, False, str(e))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Shutdown failed: {e}")
    record_event(session, user, host, PowerAction.shutdown, True)
    return {"status": f"Shutdown command sent to {host.name}"}


@router.get("/{host_id}/status")
def host_status(host_id: int, user: CurrentUser, session: SessionDep):
    host = get_owned_host(host_id, user, session)
    return {"online": is_host_up(host.ip)}


@events_router.get("", response_model=list[PowerEventPublic])
def list_events(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    host_id: int | None = None,
):
    """Newest first. Optional ?host_id= to show one host's history."""
    query = select(PowerEvent).where(PowerEvent.user_id == user.id)
    if host_id is not None:
        query = query.where(PowerEvent.host_id == host_id)
    query = query.order_by(col(PowerEvent.created_at).desc(), col(PowerEvent.id).desc())
    return session.exec(query.limit(limit)).all()
