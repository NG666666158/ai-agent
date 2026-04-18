export type ProgressUpdate = {
  id: string;
  stage: string;
  message: string;
  detail: string | null;
  created_at: string;
};

export type Step = {
  id: string;
  name: string;
  status: string;
  description: string;
  output: string | null;
};

export type TaskCheckpoint = {
  phase: string;
  current_stage: string;
  current_step_id: string | null;
  last_completed_step_id: string | null;
  last_completed_step_name: string | null;
  resume_reason: string | null;
  context_version: number;
  failure_count: number;
  recovery_attempt: number;
  last_failure_category: string;
  last_failure_resolution: string;
  last_recovery_step_id: string | null;
  last_recovery_step_name: string | null;
  last_recovery_note: string | null;
  resumable: boolean;
  last_saved_at: string;
};

export type RecoveryStrategy =
  | "revise_current_result"
  | "rebuild_plan_or_retry"
  | "replan"
  | "replan_remaining_steps";

export type ReplanEvent = {
  id: string;
  reason: string;
  summary: string;
  detail: string | null;
  failure_category: string;
  trigger_phase: string;
  checkpoint_stage: string | null;
  checkpoint_step_id: string | null;
  resume_from_step_id: string | null;
  resume_from_step_name: string | null;
  recovery_strategy: RecoveryStrategy;
  recovery_attempts: number;
  created_at: string;
};

export type ContextLayer = {
  system_instructions: string;
  session_summary: string;
  recent_messages: string[];
  condensed_recent_messages: string[];
  recalled_memories: string[];
  profile_facts: string[];
  working_memory: string[];
  source_summary: string;
  layer_budget: Record<string, number>;
  build_notes: string[];
  version: number;
};

export type CitationSource = {
  id: string;
  kind: string;
  label: string;
  detail: string;
  source_record_id: string | null;
  source_session_id: string | null;
  source_task_id: string | null;
  excerpt: string | null;
};

export type ParagraphCitation = {
  id: string;
  paragraph_index: number;
  paragraph_text: string;
  source_ids: string[];
  source_labels: string[];
};

export type ExecutionNodeArtifact = {
  label: string;
  content: string;
};

export type ExecutionNode = {
  id: string;
  kind: string;
  title: string;
  status: string;
  summary: string;
  detail: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  artifacts: ExecutionNodeArtifact[];
};

export type ToolInvocation = {
  id: string;
  step_id: string;
  tool_name: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_preview: string | null;
  error: string | null;
  failure_category: string;
  attempt_count: number;
  started_at: string;
  completed_at: string;
};

export type PendingApproval = {
  id: string;
  tool_name: string;
  operation: string;
  message: string;
  risk_note: string;
  permission_level: string;
  input_payload: Record<string, unknown>;
  approved: boolean | null;
  created_at: string;
  resolved_at: string | null;
};

export type MemorySource = {
  task_id: string | null;
  session_id: string | null;
  message_id: string | null;
  source_type: string;
};

export type MemoryVersion = {
  version: number;
  topic: string;
  summary: string;
  details: string;
  tags: string[];
  updated_at: string;
  updated_by: string;
};

export type UserProfileFact = {
  id: string;
  category: string;
  label: string;
  value: string;
  confidence: number;
  status: "ACTIVE" | "MERGED" | "ARCHIVED";
  superseded_by: string | null;
  source_session_id: string | null;
  source_message_id: string | null;
  source_task_id: string | null;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type UserProfileUpdatePayload = {
  label?: string;
  value?: string;
  confidence?: number;
  summary?: string;
  status?: "ACTIVE" | "MERGED" | "ARCHIVED";
};

export type UserProfileMergePayload = {
  target_fact_id: string;
  summary?: string;
};

export type MemoryRecord = {
  id: string;
  topic: string;
  scope: string;
  memory_type: string;
  summary: string;
  details: string;
  created_at: string;
  tags: string[];
  retrieval_score: number | null;
  retrieval_reason: string | null;
  retrieval_channels: string[];
  source: MemorySource;
  versions: MemoryVersion[];
  deleted: boolean;
  deleted_at: string | null;
};

export type MemoryUpdatePayload = {
  scope?: string;
  topic?: string;
  summary?: string;
  details?: string;
  tags?: string[];
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: "USER" | "ASSISTANT" | "SYSTEM";
  content: string;
  task_id: string | null;
  created_at: string;
};

export type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_task_id: string | null;
  message_count: number;
  context_summary?: string;
  summary_updated_at?: string | null;
  source_session_id?: string | null;
  branched_from_message_id?: string | null;
  profile_snapshot?: string[];
};

export type Task = {
  id: string;
  title: string;
  session_id: string | null;
  status: string;
  result: string | null;
  live_result: string | null;
  retry_count: number;
  replan_count: number;
  failure_category: string;
  failure_message: string | null;
  profile_hits: UserProfileFact[];
  progress_updates: ProgressUpdate[];
  steps: Step[];
  tool_invocations: ToolInvocation[];
  pending_approvals: PendingApproval[];
  recalled_memories: MemoryRecord[];
  checkpoint: TaskCheckpoint;
  replan_history: ReplanEvent[];
  context_layers: ContextLayer;
  citation_sources: CitationSource[];
  paragraph_citations: ParagraphCitation[];
  execution_nodes: ExecutionNode[];
  created_at: string;
  updated_at: string;
};

export type SessionDetail = {
  session: Session;
  messages: ChatMessage[];
  tasks: Task[];
};

export type SessionCreatePayload = {
  title?: string;
  source_session_id?: string;
  seed_prompt?: string;
};

export type RuntimeInfo = {
  llm_provider: string;
  openai_model: string;
  minimax_model: string;
  minimax_base_url: string;
  embedding_model: string;
  force_fallback_llm: boolean;
  allow_online_search: boolean;
  web_search_provider: string;
  web_search_endpoint: string;
  web_search_max_results: number;
  vector_backend: string;
  vector_service_url: string;
  vector_collection: string;
};

export type HealthInfo = {
  llm_mode: string;
  llm_provider: string;
  llm_last_error: string;
  embedding_mode: string;
  embedding_provider: string;
  search_mode: string;
  vector_backend: string;
  vector_status: string;
  tools: string[];
};

export type Evaluation = {
  score: number;
  checks: string[];
};

export type TaskTrace = {
  task: Task;
  session: SessionDetail | null;
  memory_ids: string[];
  tool_count: number;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function listTasks(): Promise<Task[]> {
  return api<Task[]>("/api/tasks");
}

export function getTask(taskId: string): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}`);
}

export function getTaskTrace(taskId: string): Promise<TaskTrace> {
  return api<TaskTrace>(`/api/tasks/${taskId}/trace`);
}

export function createTask(payload: Record<string, unknown>): Promise<Task> {
  return api<Task>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function launchTask(payload: Record<string, unknown>): Promise<Task> {
  return api<Task>("/api/tasks/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function confirmTaskApproval(taskId: string, approvalId: string, approved: boolean): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, approved }),
  });
}

export function listSessions(): Promise<Session[]> {
  return api<Session[]>("/api/sessions");
}

export function createSession(payload: SessionCreatePayload = {}): Promise<Session> {
  return api<Session>("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return api<SessionDetail>(`/api/sessions/${sessionId}`);
}

export function refreshSessionSummary(sessionId: string, force = true): Promise<SessionDetail> {
  return api<SessionDetail>(`/api/sessions/${sessionId}/refresh-summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
}

export function searchMemories(query: string, scope: string): Promise<MemoryRecord[]> {
  const url = `/api/memories/search?query=${encodeURIComponent(query)}&scope=${encodeURIComponent(scope)}`;
  return api<MemoryRecord[]>(url);
}

export function listMemories(scope = "", query = "", limit = 50): Promise<MemoryRecord[]> {
  const params = new URLSearchParams();
  if (scope.trim()) {
    params.set("scope", scope.trim());
  }
  if (query.trim()) {
    params.set("query", query.trim());
  }
  params.set("limit", String(limit));
  return api<MemoryRecord[]>(`/api/memories?${params.toString()}`);
}

export function deleteMemory(memoryId: string): Promise<{ deleted: boolean; memory_id: string }> {
  return api<{ deleted: boolean; memory_id: string }>(`/api/memories/${memoryId}`, {
    method: "DELETE",
  });
}

export function updateMemory(memoryId: string, payload: MemoryUpdatePayload): Promise<MemoryRecord> {
  return api<MemoryRecord>(`/api/memories/${memoryId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getRuntimeInfo(): Promise<RuntimeInfo> {
  return api<RuntimeInfo>("/api/system/runtime");
}

export function getHealthInfo(): Promise<HealthInfo> {
  return api<HealthInfo>("/api/system/health");
}

export function getUserProfile(limit = 50, includeInactive = true): Promise<UserProfileFact[]> {
  return api<UserProfileFact[]>(`/api/system/profile?limit=${limit}&include_inactive=${includeInactive}`);
}

export function updateUserProfileFact(factId: string, payload: UserProfileUpdatePayload): Promise<UserProfileFact> {
  return api<UserProfileFact>(`/api/system/profile/${factId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function mergeUserProfileFact(factId: string, payload: UserProfileMergePayload): Promise<UserProfileFact> {
  return api<UserProfileFact>(`/api/system/profile/${factId}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getTaskEvaluation(taskId: string): Promise<Evaluation> {
  return api<Evaluation>(`/api/tasks/${taskId}/evaluation`);
}

export function streamTask(
  taskId: string,
  handlers: {
    onUpdate: (task: Task) => void;
    onError?: () => void;
  },
) {
  const source = new EventSource(`/api/tasks/${taskId}/stream`);
  const handleMessage = (event: MessageEvent<string>) => {
    handlers.onUpdate(JSON.parse(event.data) as Task);
  };

  source.addEventListener("task_update", handleMessage as EventListener);
  source.addEventListener(
    "completed",
    ((event: MessageEvent<string>) => {
      handleMessage(event);
      source.close();
    }) as EventListener,
  );
  source.addEventListener("error", () => {
    handlers.onError?.();
    source.close();
  });

  return source;
}
