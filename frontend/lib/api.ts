import type {
  AgentExperienceOverview,
  ChatSession,
  CouncilSettings,
  DebateAnalytics,
  DebateIntelligence,
  DebateMessage,
  DebateRecord,
  ModelsResponse,
  PracticeState,
  SessionSettings,
  UserDebateProfile,
  UserDebateProfileOverview
} from "@/types";

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export const WS_BASE =
  import.meta.env.VITE_WS_BASE_URL?.replace(/\/$/, "") ??
  API_BASE.replace(/^http/, "ws");
const REQUEST_TIMEOUT_MS = 15000;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const hasBody = options.body !== undefined && options.body !== null;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: options.signal ?? controller.signal,
      headers: {
        ...(hasBody ? { "Content-Type": "application/json" } : {}),
        ...(options.headers ?? {})
      }
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        `Backend request timed out after ${REQUEST_TIMEOUT_MS / 1000} seconds at ${API_BASE}.`
      );
    }
    const message =
      error instanceof Error && error.message !== "Failed to fetch" ? ` ${error.message}` : "";
    throw new Error(
      `Backend is not reachable at ${API_BASE}.${message} Start the FastAPI server on port 8000, then try again.`
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = formatApiError(body.detail ?? body.message ?? message);
    } catch {
      // Keep the HTTP status text when no JSON body is available.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function getModels() {
  return request<ModelsResponse>("/api/models");
}

export function getCouncilSettings() {
  return request<CouncilSettings>("/api/council-settings");
}

export function updateCouncilSettings(updates: Partial<CouncilSettings>) {
  return request<CouncilSettings>("/api/council-settings", {
    method: "PATCH",
    body: JSON.stringify(updates)
  });
}

export function getUserDebateProfile() {
  return request<UserDebateProfile>("/api/user-debate-profile");
}

export function getUserDebateProfileOverview() {
  return request<UserDebateProfileOverview>("/api/user-debate-profile/overview");
}

export function resetUserDebateProfile(confirmation: string) {
  return request<UserDebateProfile>("/api/user-debate-profile/reset", {
    method: "POST",
    body: JSON.stringify({ confirmation })
  });
}

export function resetUniversalAgentExperience(confirmation: string) {
  return request<{ deleted: number }>("/api/council-settings/reset-agent-experience", {
    method: "POST",
    body: JSON.stringify({ confirmation })
  });
}

export function getAiDebaterExperiences() {
  return request<AgentExperienceOverview>("/api/ai-debater-experiences");
}

export function listSessions() {
  return request<ChatSession[]>("/api/sessions");
}

export function createSession(payload?: {
  mode?: ChatSession["mode"];
  settings?: Partial<SessionSettings>;
}) {
  return request<ChatSession>("/api/sessions", {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined
  });
}

export function renameSession(sessionId: string, name: string) {
  return request<ChatSession>(`/api/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });
}

export function deleteSession(sessionId: string) {
  return request<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export function deleteAllSessions() {
  return request<{ deleted: number }>("/api/sessions", { method: "DELETE" });
}

export function clearSessionHistory(sessionId: string) {
  return request<void>(`/api/sessions/${sessionId}/clear-history`, { method: "POST" });
}

export function clearSessionMemory(sessionId: string) {
  return request<void>(`/api/sessions/${sessionId}/clear-memory`, { method: "POST" });
}

export function listMessages(sessionId: string) {
  return request<DebateMessage[]>(`/api/sessions/${sessionId}/messages`);
}

export function listDebates(sessionId: string) {
  return request<DebateRecord[]>(`/api/sessions/${sessionId}/debates`);
}

export function renameDebate(sessionId: string, debateId: string, name: string) {
  return request<DebateRecord>(`/api/sessions/${sessionId}/debates/${debateId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });
}

export function deleteDebateStatistics(sessionId: string, debateId: string) {
  return request<void>(`/api/sessions/${sessionId}/debates/${debateId}`, { method: "DELETE" });
}

export function getSessionSettings(sessionId: string) {
  return request<SessionSettings>(`/api/sessions/${sessionId}/settings`);
}

export function getPracticeState(sessionId: string) {
  return request<PracticeState>(`/api/sessions/${sessionId}/practice-state`);
}

export function updateSessionSettings(sessionId: string, updates: Partial<SessionSettings>) {
  return request<SessionSettings>(`/api/sessions/${sessionId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(updates)
  });
}

export function getSessionAnalytics(sessionId: string, debateId?: string) {
  const suffix = debateId ? `?debate_id=${encodeURIComponent(debateId)}` : "";
  return request<DebateAnalytics>(`/api/sessions/${sessionId}/analytics${suffix}`);
}

export function getSessionIntelligence(sessionId: string, debateId?: string) {
  const suffix = debateId ? `?debate_id=${encodeURIComponent(debateId)}` : "";
  return request<DebateIntelligence>(`/api/sessions/${sessionId}/intelligence${suffix}`);
}

export function submitDebateFeedback(
  sessionId: string,
  debateId: string,
  questionKey: string,
  answer: string
) {
  return request<{ id: string }>(`/api/sessions/${sessionId}/debates/${debateId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ question_key: questionKey, answer })
  });
}

export function submitVerdictReview(
  sessionId: string,
  debateId: string,
  action: "challenge" | "override",
  winner: "pro" | "con" | "unclear",
  note: string
) {
  return request<{ id: string }>(`/api/sessions/${sessionId}/debates/${debateId}/verdict-review`, {
    method: "POST",
    body: JSON.stringify({ action, winner, note })
  });
}

export async function recordRuntimeDiary(
  event: string,
  detail: string,
  sessionId?: string
) {
  try {
    await request<{ ok: boolean }>("/api/runtime-diary", {
      method: "POST",
      body: JSON.stringify({
        source: "frontend/browser",
        event,
        detail,
        session_id: sessionId ?? null
      })
    });
  } catch {
    // Diary reporting should never interrupt the user's workflow.
  }
}

function formatApiError(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object") {
          const record = item as Record<string, unknown>;
          const location = Array.isArray(record.loc) ? record.loc.join(".") : "";
          const message = typeof record.msg === "string" ? record.msg : JSON.stringify(record);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join("; ");
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "Request failed.";
    }
  }
  return String(value || "Request failed.");
}
