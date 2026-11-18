from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from auth import CurrentUser
from config import SSH_KEY_PATH
from db import SessionDep
from models import Host, HostCreate, HostPublic
from power import shutdown_now, wake_on_call

router = APIRouter(prefix="/api/hosts", tags=["hosts"])


def get_owned_host(host_id: int, user: CurrentUser, session: SessionDep) -> Host:
    host = session.get(Host, host_id)
    # 404 (not 403) for other users' hosts, so IDs don't leak which hosts exist.
    if host is None or host.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Host not found")
    return host


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
    session.delete(host)
    session.commit()


# Plain `def` (not `async def`): these block on sockets/SSH,
# so FastAPI runs them in a threadpool instead of blocking the event loop.
@router.post("/{host_id}/wake")
def wake(host_id: int, user: CurrentUser, session: SessionDep):
    host = get_owned_host(host_id, user, session)
    wake_on_call(host.mac)
    return {"status": f"Wake packet sent to {host.name}"}


@router.post("/{host_id}/shutdown")
def shutdown(host_id: int, user: CurrentUser, session: SessionDep):
    host = get_owned_host(host_id, user, session)
    if not SSH_KEY_PATH:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Server has no SSH key configured (set CONTROL_PLANE_SSH_KEY)",
        )
    try:
        shutdown_now(
            ip=host.ip,
            key_path=SSH_KEY_PATH,
            username=host.ssh_username,
            os_type=host.os_type,
        )
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Shutdown failed: {e}")
    return {"status": f"Shutdown command sent to {host.name}"}
