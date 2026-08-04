export interface User {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  role: 'owner' | 'operator';
}

export interface TeamMember {
  id: string;
  email: string;
  name: string;
  role: 'owner' | 'operator';
}

export interface UserSettings {
  id: string;
  autonomy: 'auto_fix' | 'ask_first';
  ask_below_pct: number;
  quiet_low_severity: boolean;
  escalation_contact: string;
  phone_number: string | null;
  llm_provider: string;
  llm_model: string;
  llm_api_key: string | null;
  fly_api_token: string | null;
  fly_apps: string[];
}

export interface Service {
  id: string;
  user_id: string;
  host_id: string | null;
  host_name: string | null;
  name: string;
  method: 'docker' | 'agent' | 'url' | 'fly';
  fly_app: string | null;
  health_check_url: string | null;
  agent_token: string | null;
  agent_host_info: Record<string, any> | null;
  watch_logs: string[];
  allowed_fix_command: string | null;
  watch_only: boolean;
  status: string;
  last_check_at: string | null;
  created_at: string;
}

export interface Host {
  id: string;
  name: string;
  token_preview: string;
  token?: string;
  install_backend_url?: string;
  last_seen_at: string | null;
  created_at: string;
  autonomy: 'auto_fix' | 'ask_first' | null;
  agent_version: string | null;
  agent_outdated: boolean;
}

export interface FleetIncident {
  started_at: string;
  resolved_at: string | null;
  severity: 'down' | 'degraded';
  status: string;
}

export interface FleetService {
  id: string;
  name: string;
  status: string;
  watch_only: boolean;
  uptime_pct: number;
  incidents: FleetIncident[];
}

export interface FleetServer {
  name: string;
  down: number;
  degraded: number;
  services: FleetService[];
}

export interface Fleet {
  window_hours: number;
  servers: FleetServer[];
}

export interface IncidentEvent {
  id: string;
  timestamp: string;
  source: string;
  code: string;
  note: string;
}

export interface Incident {
  id: string;
  service_id: string;
  service_name: string | null;
  severity: 'down' | 'degraded';
  status: 'open' | 'resolved' | 'escalated' | 'took_over';
  summary: string;
  diagnosis: string;
  confidence_pct: number;
  sure: boolean;
  started_at: string;
  resolved_at: string | null;
  duration_seconds: number | null;
  action_taken: string | null;
  events?: IncidentEvent[];
  llm_diagnosis: string | null;
  llm_suggested_fix: string | null;
  llm_confidence: 'low' | 'medium' | 'high' | null;
  llm_diagnosed_at: string | null;
}

export interface PaginatedIncidents {
  data: Incident[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface Learning {
  id: string;
  service_id: string | null;
  service_name: string | null;
  rule: string;
  learned_from: string;
  behavior: 'auto_fix' | 'ask_first';
  incident_count: number;
  success_count: number;
  updated_at: string | null;
}

export interface Guardrail {
  id: string;
  key: string;
  label: string;
  description: string;
  kind: 'toggle' | 'locked';
  value: boolean;
  service_id: string | null;
  service_name: string | null;
}

export interface TimelineItem {
  kind: 'done' | 'active' | 'wait' | 'pending';
  text: string;
  time: string;
}

export interface ActiveIncidentState {
  incident_id: string | null;
  service_id: string | null;
  service_name: string | null;
  host_id?: string | null;
  method?: 'agent' | 'docker' | 'url' | 'fly' | null;
  proposed_action?:
    | 'restart_container'
    | 'stop_container'
    | 'start_container'
    | 'register_proxy_route'
    | null;
  view: 'resting' | 'detecting' | 'diagnosing' | 'asking' | 'fixing' | 'verifying' | 'resolved' | 'takeover';
  elapsed: number;
  autonomy: 'auto_fix' | 'ask_first';
  can_approve: boolean;
  can_take_over: boolean;
  can_hand_back: boolean;
  timeline: TimelineItem[];
  proposed_fix: string | null;
  status_text: string;
  status_dot: 'green' | 'red' | 'amber' | 'dashed-red' | 'dashed-gray';
  llm_diagnosis: string | null;
  llm_suggested_fix: string | null;
  llm_confidence: 'low' | 'medium' | 'high' | null;
  diagnosis_unavailable?: boolean;
}

