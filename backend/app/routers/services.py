from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.actions import is_allowed_action
from app.deps import allowed_host_ids, get_current_user, get_db_session, host_allowed, require_owner
from app.models import Host, Service, User
from app.schemas import ServiceCreate, ServiceOut, ServiceUpdate
from app.stream import stream_manager

router = APIRouter(prefix="/services", tags=["services"])


def _check_fix(db: Session, user: User, host_id: str | None, action: dict | None):
    """A fix has to name one of this user's hosts and an action on the whitelist.
    Checked here as well as before execution: the whitelist stays the one safety
    boundary, but a bad fix should fail when it is configured rather than go quiet
    until an incident needs it."""
    if action is not None and not is_allowed_action(action):
        raise HTTPException(status_code=400, detail="Fix action is not on the whitelist")
    if host_id is not None:
        host = db.query(Host).filter(Host.id == host_id, Host.user_id == user.id).first()
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")


def _service_out(service: Service) -> ServiceOut:
    return ServiceOut(
        id=service.id,
        user_id=service.user_id,
        host_id=service.host_id,
        host_name=service.host.name if service.host else None,
        name=service.name,
        method=service.method,
        health_check_url=service.health_check_url,
        agent_token=service.agent_token,
        agent_host_info=service.agent_host_info,
        watch_logs=service.watch_logs,
        allowed_fix_action=service.allowed_fix_action,
        watch_only=service.watch_only,
        status=service.status,
        last_check_at=service.last_check_at,
        created_at=service.created_at,
    )


@router.get("", response_model=list[ServiceOut])
def list_services(
    user: User = Depends(get_current_user),
    allowed: set[str] | None = Depends(allowed_host_ids),
):
    return [
        _service_out(s) for s in user.services if host_allowed(allowed, s.host_id)
    ]


@router.post("", response_model=ServiceOut, status_code=201)
def create_service(
    body: ServiceCreate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    _owner: User = Depends(require_owner),
):
    if body.method != "url":
        raise HTTPException(status_code=400, detail="Only 'url' services can be created manually")
    _check_fix(db, user, body.host_id, body.allowed_fix_action)
    service = Service(
        user_id=user.id,
        name=body.name,
        method="url",
        health_check_url=body.health_check_url,
        status="healthy",
        # Both together make the endpoint fixable; either alone leaves it alert-only.
        host_id=body.host_id,
        allowed_fix_action=body.allowed_fix_action,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    # Tell connected clients the service set changed so they refresh (the count
    # on Now, the Sidebar, the onboarding card). See #74.
    stream_manager.broadcast("services_changed", {})
    return _service_out(service)


@router.patch("/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: str,
    update: ServiceUpdate,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    _owner: User = Depends(require_owner),
):
    service = db.query(Service).filter(Service.id == service_id, Service.user_id == user.id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    fields = update.model_dump(exclude_unset=True)
    _check_fix(
        db,
        user,
        fields.get("host_id", service.host_id),
        fields.get("allowed_fix_action", service.allowed_fix_action),
    )
    for key, value in fields.items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return _service_out(service)


@router.delete("/{service_id}", status_code=204)
def delete_service(
    service_id: str,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    _owner: User = Depends(require_owner),
):
    service = db.query(Service).filter(Service.id == service_id, Service.user_id == user.id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    stream_manager.broadcast("services_changed", {})
    return None
