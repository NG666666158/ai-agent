export type Task = {
  id: string;
  title: string;
  status: string;
  result: string | null;
  steps: Array<{
    id: string;
    name: string;
    status: string;
    description: string;
    output: string | null;
  }>;
};

export type MemoryRecord = {
  id: string;
  topic: string;
  scope: string;
  summary: string;
  details: string;
  created_at: string;
  tags: string[];
};

export type RuntimeInfo = {
  openai_model: string;
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
  search_mode: string;
  vector_backend: string;
  vector_status: string;
  tools: string[];
};

export type Evaluation = {
  score: number;
  checks: string[];
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

export function createTask(payload: Record<string, unknown>): Promise<Task> {
  return api<Task>("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function searchMemories(query: string, scope: string): Promise<MemoryRecord[]> {
  const url = `/api/memories/search?query=${encodeURIComponent(query)}&scope=${encodeURIComponent(scope)}`;
  return api<MemoryRecord[]>(url);
}

export function getRuntimeInfo(): Promise<RuntimeInfo> {
  return api<RuntimeInfo>("/api/system/runtime");
}

export function getHealthInfo(): Promise<HealthInfo> {
  return api<HealthInfo>("/api/system/health");
}

export function getTaskEvaluation(taskId: string): Promise<Evaluation> {
  return api<Evaluation>(`/api/tasks/${taskId}/evaluation`);
}
