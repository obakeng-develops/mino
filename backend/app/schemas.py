from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    phone: str | None = None
    role: str = "operator"


class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class SetupStatus(BaseModel):
    needs_setup: bool
    token_required: bool


class SetupRequest(BaseModel):
    email: str
    name: str
    password: str
    token: str | None = None


class TeamMemberCreate(BaseModel):
    email: str
    name: str
    password: str


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str


class ServerAccessUpdate(BaseModel):
    host_ids: list[str]  # empty = unrestricted (all servers)


class UserSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    autonomy: str
    ask_below_pct: int
    quiet_low_severity: bool
    escalation_contact: str
    phone_number: str | None = None
    llm_provider: str
    llm_model: str
    llm_api_key: str | None = None
    fly_api_token: str | None = None
    fly_apps: list[str] = []


class UserSettingsUpdate(BaseModel):
    autonomy: str | None = None
    ask_below_pct: int | None = Field(default=None, ge=50, le=100)
    quiet_low_severity: bool | None = None
    escalation_contact: str | None = None
    phone_number: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    fly_api_token: str | None = None
    fly_apps: list[str] | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    host_id: str | None = None
    host_name: str | None = None
    name: str
    method: str
    fly_app: str | None = None  # the Fly app a "fly" service's machine belongs to
    health_check_url: str | None = None
    agent_token: str | None = None
    agent_host_info: dict[str, Any] | None = None
    watch_logs: list[str]
    allowed_fix_action: dict[str, Any] | None = None
    watch_only: bool
    status: str
    last_check_at: datetime | None = None
    created_at: datetime


class ServiceUpdate(BaseModel):
    watch_only: bool | None = None
    # Set both to let Mino fix a URL service: the host whose agent runs the fix,
    # and the whitelisted action to run. Without both it stays alert-only.
    host_id: str | None = None
    allowed_fix_action: dict | None = None


class ServiceCreate(BaseModel):
    name: str
    method: str = "url"
    health_check_url: str
    host_id: str | None = None
    allowed_fix_action: dict | None = None


class HostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    token_preview: str
    last_seen_at: datetime | None = None
    created_at: datetime
    autonomy: str | None = None  # null = use the fleet-wide setting
    agent_version: str | None = None
    agent_outdated: bool = False


class HostCreate(BaseModel):
    name: str


class HostUpdate(BaseModel):
    autonomy: str | None = None  # "auto_fix" | "ask_first" | null to clear


class AgentBeatPayload(BaseModel):
    containers: list[dict[str, Any]]
    agent_version: str | None = None


class AgentBeatResponse(BaseModel):
    # All approved actions ({"action", "container"}) for the new agent.
    actions: list[dict[str, Any]] = []
    # Restart-only subset, for older agents that only understand restarts.
    restart: list[dict[str, Any]]
    fetch_logs: list[str]
    tail_logs: bool = False


class AgentLogPayload(BaseModel):
    lines: list[str]


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    timestamp: datetime
    source: str
    code: str
    note: str


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    severity: str
    status: str
    summary: str
    diagnosis: str
    confidence_pct: int
    sure: bool
    started_at: datetime
    resolved_at: datetime | None = None
    duration_seconds: int | None = None
    action_taken: str | None = None
    service_name: str | None = None
    events: list[IncidentEventOut] | None = None
    llm_diagnosis: str | None = None
    llm_suggested_fix: str | None = None
    llm_confidence: str | None = None
    llm_diagnosed_at: datetime | None = None


class IncidentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str
    service_name: str | None = None
    severity: str
    status: str
    summary: str
    diagnosis: str
    confidence_pct: int
    sure: bool
    started_at: datetime
    resolved_at: datetime | None = None
    duration_seconds: int | None = None
    action_taken: str | None = None
    llm_diagnosis: str | None = None
    llm_suggested_fix: str | None = None
    llm_confidence: str | None = None
    llm_diagnosed_at: datetime | None = None


class PaginatedIncidents(BaseModel):
    data: list[IncidentListItem]
    next_cursor: str | None = None
    has_more: bool = False


class LearningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    service_id: str | None = None
    service_name: str | None = None
    rule: str
    learned_from: str
    behavior: str
    incident_count: int
    success_count: int
    updated_at: datetime | None = None  # ~last time this rule recovered the service


class GuardrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    label: str
    description: str
    kind: str
    value: bool
    service_id: str | None = None
    service_name: str | None = None


class GuardrailUpdate(BaseModel):
    value: bool


class ActiveIncidentState(BaseModel):
    incident_id: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    host_id: str | None = None
    method: str | None = None  # agent | docker | url — url can't be restarted
    proposed_action: str | None = None  # restart_container | stop_container | start_container
    view: str  # resting | detecting | diagnosing | asking | fixing | verifying | resolved | takeover
    elapsed: int = 0
    autonomy: str
    can_approve: bool = False
    can_take_over: bool = False
    can_hand_back: bool = False
    timeline: list[dict[str, Any]] = []
    proposed_fix: str | None = None
    status_text: str = "watching"
    status_dot: str = "green"  # green | red | amber | dashed-red | dashed-gray
    llm_diagnosis: str | None = None
    llm_suggested_fix: str | None = None
    llm_confidence: str | None = None
    # Diagnosis attempt finished with nothing usable — UI shows a terminal
    # "unavailable" state instead of an eternal "pending". See #73.
    diagnosis_unavailable: bool = False


class CursorParams(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
