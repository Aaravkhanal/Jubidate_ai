"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { SessionSpawner } from "@/components/orchestration/SessionSpawner";
import { DebateRoom, type RoomPanel } from "@/components/DebateRoom";
import { GlobalWorkspace } from "@/components/GlobalWorkspace";
import { Sidebar, type SidebarWorkspaceView } from "@/components/Sidebar";
import {
  getAiDebaterExperiences,
  clearSessionHistory,
  clearSessionMemory,
  createSession,
  deleteAllSessions,
  deleteDebateStatistics,
  deleteSession,
  getCouncilSettings,
  getModels,
  getPracticeState,
  getSessionAnalytics,
  getSessionIntelligence,
  getUserDebateProfileOverview,
  getSessionSettings,
  listDebates,
  listMessages,
  listSessions,
  recordRuntimeDiary,
  renameDebate,
  resetUniversalAgentExperience,
  resetUserDebateProfile,
  renameSession,
  startRESTDebate,
  submitDebateFeedback,
  submitVerdictReview,
  updateCouncilSettings,
  updateSessionModels,
  updateSessionSettings,
  WS_BASE
} from "@/lib/api";
import type {
  AgentExperienceOverview,
  ChatSession,
  CouncilSettings,
  DebateAnalytics,
  DebateIntelligence,
  DebateAssignment,
  DebateEvent,
  DebateMessage,
  DebateRecord,
  ModelsResponse,
  PracticeSettings,
  PracticeState,
  SessionSettings,
  UserDebateProfileOverview
} from "@/types";

const MAX_SESSIONS = 10;
const USER_INPUT_MAX_CHARS = 5500;
const WEBSOCKET_CONNECT_RETRIES = 2;
const WEBSOCKET_RETRY_DELAY_MS = 1200;
const DEFAULT_PRACTICE_SETTINGS: PracticeSettings = {
  human_side: "Auto",
  practice_flow: "Free",
  structured_rounds: 3,
  use_user_profile: true,
  trainer_style: "Coach",
  training_focus: "Full Debate",
  opponent_difficulty: "Adaptive"
};

function defaultNewChatDraft(): NewChatDraft {
  return {
    mode: "ai_vs_human",
    overall_model: "gemini-2.5-flash",
    debaters_per_team: 1,
    ai_a_model: "",
    ai_b_model: "",
    judge_model: "",
    rounds: 3,
    practice_settings: {
      human_side: "Auto",
      practice_flow: "Free",
      structured_rounds: 3,
      use_user_profile: true,
      trainer_style: "Coach",
      training_focus: "Full Debate",
      opponent_difficulty: "Normal"
    }
  };
}

type ClearTarget = { session: ChatSession; mode: "history" | "memory" };
type DebateDeleteTarget = { session: ChatSession; debate: DebateRecord };
type NewChatDraft = {
  mode: ChatSession["mode"];
  overall_model: string;
  debaters_per_team: number;
  practice_settings: PracticeSettings;
  ai_a_model: string;
  ai_b_model: string;
  judge_model: string;
  rounds: number;
};

export default function Home() {
  const [workspaceView, setWorkspaceView] = useState<SidebarWorkspaceView>("session");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, DebateMessage[]>>({});
  const [partialBySession, setPartialBySession] = useState<
    Record<string, Record<string, DebateMessage>>
  >({});
  const [draftBySession, setDraftBySession] = useState<Record<string, string>>({});
  const [settingsBySession, setSettingsBySession] = useState<Record<string, SessionSettings>>({});
  const [modelBySession, setModelBySession] = useState<Record<string, string>>({});
  const [statusBySession, setStatusBySession] = useState<Record<string, string>>({});
  const [assignmentsBySession, setAssignmentsBySession] = useState<
    Record<string, DebateAssignment[]>
  >({});
  const [debatesBySession, setDebatesBySession] = useState<Record<string, DebateRecord[]>>({});
  const [selectedDebateBySession, setSelectedDebateBySession] = useState<Record<string, string>>(
    {}
  );
  const [analyticsBySession, setAnalyticsBySession] = useState<Record<string, DebateAnalytics>>({});
  const [intelligenceBySession, setIntelligenceBySession] = useState<Record<string, DebateIntelligence>>({});
  const [practiceStateBySession, setPracticeStateBySession] = useState<Record<string, PracticeState>>({});
  const [analyticsHistoryBySession, setAnalyticsHistoryBySession] = useState<
    Record<string, DebateAnalytics[]>
  >({});
  const [runningBySession, setRunningBySession] = useState<Record<string, boolean>>({});
  const [teamPreparingBySession, setTeamPreparingBySession] = useState<Record<string, boolean>>({});
  const [currentRoundBySession, setCurrentRoundBySession] = useState<Record<string, number>>({});
  const [activeSpeakerBySession, setActiveSpeakerBySession] = useState<Record<string, string>>({});
  const [totalRoundsBySession, setTotalRoundsBySession] = useState<Record<string, number>>({});
  const [streamingStatusBySession, setStreamingStatusBySession] = useState<Record<string, string>>({});
  const [realtimeAnalyticsBySession, setRealtimeAnalyticsBySession] = useState<Record<string, any>>({});
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [councilSettings, setCouncilSettings] = useState<CouncilSettings | null>(null);
  const [agentExperienceOverview, setAgentExperienceOverview] =
    useState<AgentExperienceOverview | null>(null);
  const [userProfileOverview, setUserProfileOverview] =
    useState<UserDebateProfileOverview | null>(null);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatTab, setNewChatTab] = useState<"mode" | "settings">("mode");
  const [newChatDraft, setNewChatDraft] = useState<NewChatDraft>(defaultNewChatDraft());
  const [creatingSession, setCreatingSession] = useState(false);
  const [practiceStartTarget, setPracticeStartTarget] = useState<{
    sessionId: string;
    content: string;
    modelName: string;
  } | null>(null);
  const [practiceSideChoice, setPracticeSideChoice] = useState<"Auto" | "Pro" | "Con">("Auto");
  const [activePanel, setActivePanel] = useState<RoomPanel>("chat");
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChatSession | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deleteAllError, setDeleteAllError] = useState<string | null>(null);
  const [clearTarget, setClearTarget] = useState<ClearTarget | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);
  const [deleteDebateTarget, setDeleteDebateTarget] = useState<DebateDeleteTarget | null>(null);
  const [deleteDebateError, setDeleteDebateError] = useState<string | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);
  const [renamingDebateId, setRenamingDebateId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deletingAllSessions, setDeletingAllSessions] = useState(false);
  const [deletingDebateId, setDeletingDebateId] = useState<string | null>(null);
  const [clearingSessionId, setClearingSessionId] = useState<string | null>(null);
  const socketRefs = useRef<Record<string, WebSocket>>({});
  const retryTimerRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const modelBySessionRef = useRef<Record<string, string>>({});
  const selectedIdRef = useRef<string | null>(null);

  const selectedSession = sessions.find((session) => session.id === selectedId) ?? null;
  const selectedMessages = selectedId ? messagesBySession[selectedId] ?? [] : [];
  const selectedPartials = selectedId ? partialBySession[selectedId] ?? {} : {};
  const selectedDraft = selectedId ? draftBySession[selectedId] ?? "" : "";
  const selectedSettings = selectedId ? settingsBySession[selectedId] ?? null : null;
  const selectedModelName = selectedId
    ? modelBySession[selectedId] || selectedSettings?.overall_model || ""
    : "";
  const selectedStatus = selectedId
    ? statusBySession[selectedId] ?? "Ready for a message."
    : "No session selected.";
  const selectedAssignments = selectedId ? assignmentsBySession[selectedId] ?? [] : [];
  const selectedDebates = selectedId ? debatesBySession[selectedId] ?? [] : [];
  const selectedDebateId = selectedId ? selectedDebateBySession[selectedId] ?? "" : "";
  const selectedAnalytics = selectedId ? analyticsBySession[selectedId] ?? null : null;
  const selectedIntelligence = selectedId ? intelligenceBySession[selectedId] ?? null : null;
  const selectedPracticeState = selectedId ? practiceStateBySession[selectedId] ?? null : null;
  const selectedAnalyticsHistory = selectedId ? analyticsHistoryBySession[selectedId] ?? [] : [];
  const selectedRunning = selectedId ? Boolean(runningBySession[selectedId]) : false;
  const selectedTeamPreparing = selectedId ? Boolean(teamPreparingBySession[selectedId]) : false;
  const selectedCurrentRound = selectedId ? currentRoundBySession[selectedId] ?? 0 : 0;
  const selectedTotalRounds = selectedId ? totalRoundsBySession[selectedId] ?? 0 : 0;
  const selectedActiveSpeaker = selectedId ? activeSpeakerBySession[selectedId] ?? "" : "";
  const selectedStreamingStatus = selectedId ? streamingStatusBySession[selectedId] ?? "" : "";
  const selectedRealtimeAnalytics = selectedId ? realtimeAnalyticsBySession[selectedId] ?? null : null;

  useEffect(() => {
    modelBySessionRef.current = modelBySession;
  }, [modelBySession]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    const theme = councilSettings?.theme ?? "Dark";
    const html = document.documentElement;
    localStorage.setItem("jubidate-theme", theme);
    if (theme === "Light") {
      html.classList.add("light");
      return;
    }
    if (theme === "System") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      html.classList.toggle("light", !mq.matches);
      const handler = (e: MediaQueryListEvent) => html.classList.toggle("light", !e.matches);
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
    html.classList.remove("light");
  }, [councilSettings?.theme]);

  const refreshSessions = useCallback(async () => {
    const nextSessions = await listSessions();
    setSessions(nextSessions);
    return nextSessions;
  }, []);

  const refreshModels = useCallback(async () => {
    const nextModels = await getModels();
    setModels(nextModels);
    return nextModels;
  }, []);

  const refreshAgentExperienceOverview = useCallback(async () => {
    const nextOverview = await getAiDebaterExperiences();
    setAgentExperienceOverview(nextOverview);
    return nextOverview;
  }, []);

  const refreshUserProfileOverview = useCallback(async () => {
    const nextOverview = await getUserDebateProfileOverview();
    setUserProfileOverview(nextOverview);
    return nextOverview;
  }, []);

  const refreshMessages = useCallback(async (sessionId: string) => {
    const nextMessages = await listMessages(sessionId);
    setMessagesBySession((current) => ({ ...current, [sessionId]: nextMessages }));
  }, []);

  const refreshDebates = useCallback(async (sessionId: string) => {
    const nextDebates = await listDebates(sessionId);
    setDebatesBySession((current) => ({ ...current, [sessionId]: nextDebates }));
    setSelectedDebateBySession((current) => {
      const currentId = current[sessionId];
      if (currentId && nextDebates.some((debate) => debate.id === currentId)) {
        return current;
      }
      return { ...current, [sessionId]: nextDebates[0]?.id ?? "" };
    });
    return nextDebates;
  }, []);

  const refreshSettings = useCallback(async (sessionId: string) => {
    const nextSettings = await getSessionSettings(sessionId);
    setSettingsBySession((current) => ({ ...current, [sessionId]: nextSettings }));
    if (nextSettings.overall_model) {
      setModelBySession((current) => ({ ...current, [sessionId]: nextSettings.overall_model }));
    }
  }, []);

  const refreshAnalytics = useCallback(async (sessionId: string, debateId?: string) => {
    const nextAnalytics = await getSessionAnalytics(sessionId, debateId);
    if (nextAnalytics.turn_count === 0) {
      setAnalyticsBySession((current) => removeKey(current, sessionId));
      setAnalyticsHistoryBySession((current) => ({ ...current, [sessionId]: [] }));
      return;
    }
    setAnalyticsBySession((current) => ({ ...current, [sessionId]: nextAnalytics }));
    if (nextAnalytics.source?.debate_id) {
      setSelectedDebateBySession((current) => ({
        ...current,
        [sessionId]: nextAnalytics.source?.debate_id ?? ""
      }));
    }
    setAnalyticsHistoryBySession((current) => ({
      ...current,
      [sessionId]: mergeAnalyticsHistory(current[sessionId] ?? [], nextAnalytics)
    }));
  }, []);

  const refreshIntelligence = useCallback(async (sessionId: string, debateId?: string) => {
    const nextIntelligence = await getSessionIntelligence(sessionId, debateId);
    setIntelligenceBySession((current) => ({ ...current, [sessionId]: nextIntelligence }));
  }, []);

  const refreshPracticeState = useCallback(async (sessionId: string) => {
    const nextPracticeState = await getPracticeState(sessionId);
    setPracticeStateBySession((current) => ({ ...current, [sessionId]: nextPracticeState }));
    return nextPracticeState;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      try {
        const [sessionList, modelData, councilData, experienceData, profileData] = await Promise.all([
          listSessions(),
          refreshModels(),
          getCouncilSettings().catch(() => null),
          refreshAgentExperienceOverview().catch(() => null),
          refreshUserProfileOverview().catch(() => null)
        ]);
        if (cancelled) {
          return;
        }
        setModels(modelData);
        if (councilData) setCouncilSettings(councilData);
        if (experienceData) setAgentExperienceOverview(experienceData);
        if (profileData) setUserProfileOverview(profileData);

        setSessions(sessionList);
        setSelectedId(sessionList[0]?.id ?? null);
        recordRuntimeDiary(
          "frontend boot",
          `Loaded ${sessionList.length} session(s), ${modelData.available_model_count} verified model(s), and the global training overview.`
        );
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Startup failed.");
        recordRuntimeDiary(
          "frontend boot failed",
          exc instanceof Error ? exc.message : "Startup failed."
        );
      }
    }

    boot();
    return () => {
      cancelled = true;
    };
  }, [refreshAgentExperienceOverview, refreshModels, refreshUserProfileOverview]);

  useEffect(() => {
    return () => {
      Object.values(retryTimerRefs.current).forEach((timer) => clearTimeout(timer));
      Object.values(socketRefs.current).forEach((socket) => socket.close());
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    const requestSessionId = selectedId;
    setActivePanel("chat");
    refreshMessages(selectedId).catch((exc) => {
      if (selectedIdRef.current === requestSessionId) {
        setError(exc instanceof Error ? exc.message : "Could not load messages.");
      }
    });
    refreshSettings(selectedId).catch((exc) => {
      if (selectedIdRef.current === requestSessionId) {
        setError(exc instanceof Error ? exc.message : "Could not load settings.");
      }
    });
    refreshDebates(selectedId).catch(() => undefined);
    refreshAnalytics(selectedId).catch(() => undefined);
    refreshIntelligence(selectedId).catch(() => undefined);
    refreshPracticeState(selectedId).catch(() => undefined);
  }, [selectedId, refreshMessages, refreshSettings, refreshDebates, refreshAnalytics, refreshIntelligence, refreshPracticeState]);

  useEffect(() => {
    if (!models || !selectedId) {
      return;
    }
    const savedModel = settingsBySession[selectedId]?.overall_model ?? "";
    setModelBySession((current) => {
      const currentName = savedModel || current[selectedId];
      if (models.models.some((model) => model.name === currentName)) {
        return current[selectedId] === currentName ? current : { ...current, [selectedId]: currentName };
      }
      return { ...current, [selectedId]: models.models[0]?.name ?? "" };
    });
  }, [models, selectedId, settingsBySession]);

  function openNewSessionModal(mode: ChatSession["mode"] = "ai_vs_ai") {
    const base = defaultNewChatDraft();
    setNewChatDraft({ ...base, mode, overall_model: models?.models[0]?.name || base.overall_model });
    setNewChatTab("mode");
    setNewChatOpen(true);
    setWorkspaceView("session");
  }

  async function handleNewSession() {
    openNewSessionModal("ai_vs_human");
  }

  async function handleCreateSessionFromDraft(overrideDraft?: NewChatDraft, topicOverride?: string) {
    if (creatingSession) {
      return;
    }
    setError(null);
    setCreatingSession(true);
    try {
      const activeDraft = overrideDraft || newChatDraft;
      const settings: Partial<SessionSettings> = {
        overall_model: activeDraft.overall_model,
        debaters_per_team: activeDraft.debaters_per_team,
        practice_settings: activeDraft.practice_settings
      };
      
      const created = await createSession({ mode: activeDraft.mode, settings });
      const dynamicNames = [
        "Strategy Session",
        "Strategic Session",
        "Intelligence Session",
        "Tactical Simulation",
        "Strategic Alignment"
      ];
      const prefix = dynamicNames[Math.floor(Math.random() * dynamicNames.length)];
      const match = created.name.match(/#(\d+)$/);
      const num = match ? match[1] : "";
      const newName = `${prefix}${num ? ` #${num}` : ""}`;
      const renamed = await renameSession(created.id, newName);

      // Connect models to the orchestration backend
      if (activeDraft.ai_a_model || activeDraft.ai_b_model || activeDraft.judge_model) {
        await updateSessionModels(renamed.id, {
          ai_a_model: activeDraft.ai_a_model,
          ai_b_model: activeDraft.ai_b_model,
          judge_model: activeDraft.judge_model,
          rounds: activeDraft.rounds || 3,
        });
        
        // Optimistically update the session model state locally
        setModelBySession((current) => ({
          ...current,
          [renamed.id]: activeDraft.overall_model,
        }));
      }

      setSessions((current) => [renamed, ...current]);
      setSelectedId(renamed.id);
      setStatusBySession((current) => ({ ...current, [renamed.id]: "Ready for a message." }));
      setPracticeStateBySession((current) => ({ ...current, [renamed.id]: { active: false } }));
      
      // Auto-start debate if a topic was specified from the SessionSpawner
      if (topicOverride) {
        try {
          const res = await startRESTDebate({
            session_id: renamed.id,
            topic: topicOverride
          });
          setDebatesBySession((current) => ({ ...current, [renamed.id]: [res.debate] }));
          setSelectedDebateBySession((current) => ({ ...current, [renamed.id]: res.debate.id }));
          setMessagesBySession((current) => ({ ...current, [renamed.id]: res.messages }));
        } catch (e) {
          console.error("Failed to start debate immediately:", e);
        }
      }

      setActivePanel("chat");
      setWorkspaceView("session");
      setNewChatOpen(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not create session.");
    } finally {
      setCreatingSession(false);
    }
  }

  function handleSelect(id: string) {
    setSelectedId(id);
    setWorkspaceView("session");
    setPracticeStartTarget(null);
    setDeleteTarget(null);
    setClearTarget(null);
    setDeleteDebateTarget(null);
    setDeleteAllOpen(false);
    setError(null);
  }

  function handleHome() {
    setSelectedId(null);
    setWorkspaceView("session");
    setPracticeStartTarget(null);
    setDeleteTarget(null);
    setClearTarget(null);
    setDeleteDebateTarget(null);
    setDeleteAllOpen(false);
    setError(null);
  }

  async function handleRename(session: ChatSession, name: string) {
    const cleaned = name.trim();
    if (!cleaned || cleaned === session.name) {
      return false;
    }

    const previousSessions = sessions;
    const optimisticSession = {
      ...session,
      name: cleaned,
      updated_at: new Date().toISOString()
    };
    setError(null);
    setRenamingSessionId(session.id);
    setSessions((current) =>
      current.map((item) => (item.id === session.id ? optimisticSession : item))
    );

    try {
      const renamed = await renameSession(session.id, cleaned);
      setSessions((current) =>
        current.map((item) => (item.id === renamed.id ? renamed : item))
      );
      return true;
    } catch (exc) {
      setSessions(previousSessions);
      setError(exc instanceof Error ? exc.message : "Could not rename session.");
      return false;
    } finally {
      setRenamingSessionId(null);
    }
  }

  async function handleConfirmDelete(targetOverride?: ChatSession, suppressFuture = false) {
    const target = targetOverride ?? deleteTarget;
    if (!target || deletingSessionId) {
      return;
    }

    setDeletingSessionId(target.id);
    setDeleteError(null);
    setError(null);

    try {
      if (suppressFuture) {
        await handleUpdateCouncilSettings({
          confirmation_preferences: {
            ...(councilSettings?.confirmation_preferences ?? {
              delete_chat: false,
              clear_chat_history: false,
              clear_chat_memory: false
            }),
            delete_chat: true
          }
        });
      }
      clearSocketRetry(target.id);
      socketRefs.current[target.id]?.close();
      delete socketRefs.current[target.id];
      await deleteSession(target.id);
      const sessionList = await refreshSessions();
      setMessagesBySession((current) => removeKey(current, target.id));
      setPartialBySession((current) => removeKey(current, target.id));
      setDraftBySession((current) => removeKey(current, target.id));
      setSettingsBySession((current) => removeKey(current, target.id));
      setModelBySession((current) => removeKey(current, target.id));
      setStatusBySession((current) => removeKey(current, target.id));
      setAssignmentsBySession((current) => removeKey(current, target.id));
      setDebatesBySession((current) => removeKey(current, target.id));
      setSelectedDebateBySession((current) => removeKey(current, target.id));
      setAnalyticsBySession((current) => removeKey(current, target.id));
      setAnalyticsHistoryBySession((current) => removeKey(current, target.id));
      setIntelligenceBySession((current) => removeKey(current, target.id));
      setPracticeStateBySession((current) => removeKey(current, target.id));
      setRunningBySession((current) => removeKey(current, target.id));
      setTeamPreparingBySession((current) => removeKey(current, target.id));
      if (selectedIdRef.current === target.id) {
        setSelectedId(sessionList[0]?.id ?? null);
      }
      setDeleteTarget(null);
      refreshAgentExperienceOverview().catch(() => undefined);
      refreshUserProfileOverview().catch(() => undefined);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Could not delete session.";
      setDeleteError(message);
      setError(message);
    } finally {
      setDeletingSessionId(null);
    }
  }

  async function handleConfirmDeleteAll() {
    if (deletingAllSessions) {
      return;
    }

    setDeletingAllSessions(true);
    setDeleteAllError(null);
    setError(null);

    try {
      Object.keys(retryTimerRefs.current).forEach((sessionId) => clearSocketRetry(sessionId));
      Object.values(socketRefs.current).forEach((socket) => socket.close());
      socketRefs.current = {};
      modelBySessionRef.current = {};
      await deleteAllSessions();
      setSessions([]);
      setSelectedId(null);
      setMessagesBySession({});
      setPartialBySession({});
      setDraftBySession({});
      setSettingsBySession({});
      setModelBySession({});
      setStatusBySession({});
      setAssignmentsBySession({});
      setDebatesBySession({});
      setSelectedDebateBySession({});
      setAnalyticsBySession({});
      setIntelligenceBySession({});
      setPracticeStateBySession({});
      setAnalyticsHistoryBySession({});
      setRunningBySession({});
      setTeamPreparingBySession({});
      setDeleteAllOpen(false);
      await refreshSessions();
      refreshAgentExperienceOverview().catch(() => undefined);
      refreshUserProfileOverview().catch(() => undefined);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Could not delete all chats.";
      setDeleteAllError(message);
      setError(message);
    } finally {
      setDeletingAllSessions(false);
    }
  }

  async function handleConfirmClear(targetOverride?: ClearTarget, suppressFuture = false) {
    const target = targetOverride ?? clearTarget;
    if (!target || clearingSessionId) {
      return;
    }

    const { session, mode } = target;
    setClearingSessionId(session.id);
    setClearError(null);
    setError(null);

    try {
      if (suppressFuture) {
        await handleUpdateCouncilSettings({
          confirmation_preferences: {
            ...(councilSettings?.confirmation_preferences ?? {
              delete_chat: false,
              clear_chat_history: false,
              clear_chat_memory: false
            }),
            [mode === "history" ? "clear_chat_history" : "clear_chat_memory"]: true
          }
        });
      }
      clearSocketRetry(session.id);
      socketRefs.current[session.id]?.close();
      delete socketRefs.current[session.id];
      if (mode === "history") {
        await clearSessionHistory(session.id);
      } else {
        await clearSessionMemory(session.id);
      }
      setMessagesBySession((current) => ({ ...current, [session.id]: [] }));
      setPartialBySession((current) => ({ ...current, [session.id]: {} }));
      setAssignmentsBySession((current) => ({ ...current, [session.id]: [] }));
      setDebatesBySession((current) => ({ ...current, [session.id]: [] }));
      setSelectedDebateBySession((current) => ({ ...current, [session.id]: "" }));
      setAnalyticsBySession((current) => removeKey(current, session.id));
      setAnalyticsHistoryBySession((current) => ({ ...current, [session.id]: [] }));
      setIntelligenceBySession((current) => removeKey(current, session.id));
      setPracticeStateBySession((current) => ({ ...current, [session.id]: { active: false } }));
      setStatusBySession((current) => ({
        ...current,
        [session.id]:
          mode === "history"
            ? "Visible chat history cleared. Memory kept."
            : "Chat history and memory cleared."
      }));
      setClearTarget(null);
      refreshSessions().catch(() => undefined);
      refreshAgentExperienceOverview().catch(() => undefined);
      refreshUserProfileOverview().catch(() => undefined);
    } catch (exc) {
      const message =
        exc instanceof Error
          ? exc.message
          : mode === "history"
            ? "Could not clear chat history."
            : "Could not clear chat memory.";
      setClearError(message);
      setError(message);
    } finally {
      setClearingSessionId(null);
    }
  }

  async function handleDebateChange(debateId: string) {
    if (!selectedId) {
      return;
    }
    const sessionId = selectedId;
    setSelectedDebateBySession((current) => ({ ...current, [sessionId]: debateId }));
    setAnalyticsHistoryBySession((current) => ({ ...current, [sessionId]: [] }));
    try {
      await refreshAnalytics(sessionId, debateId || undefined);
      await refreshIntelligence(sessionId, debateId || undefined);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not load debate statistics.");
    }
  }

  async function handleRenameDebate(debate: DebateRecord, name: string) {
    const cleaned = name.trim();
    if (!selectedId || !cleaned || cleaned === debate.name) {
      return false;
    }
    const sessionId = selectedId;
    setRenamingDebateId(debate.id);
    setError(null);

    try {
      const renamed = await renameDebate(sessionId, debate.id, cleaned);
      setDebatesBySession((current) => ({
        ...current,
        [sessionId]: (current[sessionId] ?? []).map((item) =>
          item.id === renamed.id ? renamed : item
        )
      }));
      return true;
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not rename debate.");
      return false;
    } finally {
      setRenamingDebateId(null);
    }
  }

  async function handleConfirmDeleteDebate() {
    if (!deleteDebateTarget || deletingDebateId) {
      return;
    }
    const { session, debate } = deleteDebateTarget;
    setDeletingDebateId(debate.id);
    setDeleteDebateError(null);
    setError(null);

    try {
      await deleteDebateStatistics(session.id, debate.id);
      const nextDebates = await refreshDebates(session.id);
      const nextSelected = nextDebates[0]?.id ?? "";
      setAnalyticsHistoryBySession((current) => ({ ...current, [session.id]: [] }));
      if (nextSelected) {
        await refreshAnalytics(session.id, nextSelected);
        await refreshIntelligence(session.id, nextSelected);
      } else {
        setAnalyticsBySession((current) => removeKey(current, session.id));
        setIntelligenceBySession((current) => removeKey(current, session.id));
      }
      setDeleteDebateTarget(null);
      refreshSessions().catch(() => undefined);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "Could not delete debate statistics.";
      setDeleteDebateError(message);
      setError(message);
    } finally {
      setDeletingDebateId(null);
    }
  }

  async function handleUpdateSettings(updates: Partial<SessionSettings>) {
    if (!selectedId) {
      return;
    }
    const sessionId = selectedId;
    setSettingsBySession((current) => ({
      ...current,
      ...(current[sessionId] ? { [sessionId]: { ...current[sessionId], ...updates } } : {})
    }));
    if (typeof updates.overall_model === "string") {
      setModelBySession((current) => ({ ...current, [sessionId]: updates.overall_model ?? "" }));
    }
    try {
      const saved = await updateSessionSettings(sessionId, updates);
      setSettingsBySession((current) => ({ ...current, [sessionId]: saved }));
      setModelBySession((current) => ({ ...current, [sessionId]: saved.overall_model }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save settings.");
      refreshSettings(sessionId).catch(() => undefined);
    }
  }

  async function handleUpdateCouncilSettings(updates: Partial<CouncilSettings>) {
    setCouncilSettings((current) => (current ? { ...current, ...updates } : current));
    try {
      const saved = await updateCouncilSettings(updates);
      setCouncilSettings(saved);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save Council Settings.");
      getCouncilSettings().then(setCouncilSettings).catch(() => undefined);
    }
  }

  async function handleResetUniversalIdentities(confirmation: string) {
    const result = await resetUniversalAgentExperience(confirmation);
    if (selectedId) {
      await refreshIntelligence(selectedId, selectedDebateBySession[selectedId] || undefined);
    }
    await refreshAgentExperienceOverview();
    return result;
  }

  async function handleResetUserDebateProfile(confirmation: string) {
    const result = await resetUserDebateProfile(confirmation);
    if (selectedId) {
      await refreshPracticeState(selectedId);
    }
    await refreshUserProfileOverview();
    return result;
  }

  async function handleSubmitFeedback(questionKey: string, answer: string) {
    if (!selectedId) {
      return;
    }
    const debateId = selectedDebateBySession[selectedId];
    if (!debateId || !answer.trim()) {
      return;
    }
    await submitDebateFeedback(selectedId, debateId, questionKey, answer.trim());
    await refreshIntelligence(selectedId, debateId);
    refreshAgentExperienceOverview().catch(() => undefined);
  }

  async function handleVerdictReview(
    action: "challenge" | "override",
    winner: "pro" | "con" | "unclear",
    note: string
  ) {
    if (!selectedId) {
      return;
    }
    const debateId = selectedDebateBySession[selectedId];
    if (!debateId) {
      return;
    }
    await submitVerdictReview(selectedId, debateId, action, winner, note.trim());
    await refreshDebates(selectedId);
    await refreshAnalytics(selectedId, debateId);
    await refreshIntelligence(selectedId, debateId);
  }

  function handleDraftChange(value: string) {
    if (!selectedId) {
      return;
    }
    setDraftBySession((current) => ({ ...current, [selectedId]: value }));
  }

  function handleModelChange(modelName: string) {
    if (!selectedId) {
      return;
    }
    setModelBySession((current) => ({ ...current, [selectedId]: modelName }));
    handleUpdateSettings({ overall_model: modelName }).catch(() => undefined);
  }

  function clearSocketRetry(sessionId: string) {
    const timer = retryTimerRefs.current[sessionId];
    if (timer) {
      clearTimeout(timer);
      delete retryTimerRefs.current[sessionId];
    }
  }

  function openInteractionSocket(
    sessionId: string,
    content: string,
    modelName: string,
    attempt: number,
    options: { eventType?: "start_interaction" | "end_practice_debate"; practiceSide?: string } = {}
  ) {
    clearSocketRetry(sessionId);
    let serverStarted = false;
    let sentStart = false;
    let finished = false;
    const websocket = new WebSocket(`${WS_BASE}/ws/debates/${sessionId}`);
    socketRefs.current[sessionId] = websocket;

    websocket.onopen = () => {
      websocket.send(
        JSON.stringify({
          type: options.eventType ?? "start_interaction",
          topic: content,
          model: modelName,
          practice_side: options.practiceSide
        })
      );
      sentStart = true;
      recordRuntimeDiary("websocket opened", `Started interaction with ${modelName}.`, sessionId);
      setDraftBySession((current) => ({ ...current, [sessionId]: "" }));
      setStatusBySession((current) => ({
        ...current,
        [sessionId]: attempt > 0 ? "Reconnected. Council is working." : "Council is working."
      }));
    };

    websocket.onmessage = (event) => {
      serverStarted = true;
      let payload: DebateEvent;
      try {
        payload = JSON.parse(event.data) as DebateEvent;
      } catch {
        recordRuntimeDiary("websocket parse error", "Received malformed WebSocket message.", sessionId);
        return;
      }
      if (
        payload.type === "debate_completed" ||
        payload.type === "interaction_completed" ||
        payload.type === "error"
      ) {
        finished = true;
      }
      if (payload.type === "error") {
        recordRuntimeDiary("websocket server error", formatErrorMessage(payload.message), sessionId);
      }
      handleDebateEvent(sessionId, payload);
    };

    websocket.onerror = () => {
      recordRuntimeDiary("websocket error", "Browser reported a WebSocket error.", sessionId);
      if (!sentStart && !serverStarted && attempt < WEBSOCKET_CONNECT_RETRIES) {
        setStatusBySession((current) => ({
          ...current,
          [sessionId]: "Connection issue detected. Waiting for reconnect..."
        }));
        return;
      }
      if (!finished) {
        setError("WebSocket connection failed.");
        setStatusBySession((current) => ({ ...current, [sessionId]: "Connection failed." }));
      }
    };

    websocket.onclose = () => {
      if (socketRefs.current[sessionId] === websocket) {
        delete socketRefs.current[sessionId];
      }
      if (finished) {
        recordRuntimeDiary("websocket closed", "Interaction completed and socket closed.", sessionId);
        return;
      }
      recordRuntimeDiary(
        "websocket closed early",
        serverStarted
          ? "Connection closed before the council finished."
          : "Connection closed before the council started.",
        sessionId
      );
      if (!sentStart && !serverStarted && attempt < WEBSOCKET_CONNECT_RETRIES) {
        setStatusBySession((current) => ({
          ...current,
          [sessionId]: `Connection failed. Retrying (${attempt + 1}/${WEBSOCKET_CONNECT_RETRIES})...`
        }));
        clearSocketRetry(sessionId);
        retryTimerRefs.current[sessionId] = setTimeout(() => {
          const retryModelName = modelBySessionRef.current[sessionId] || modelName;
          openInteractionSocket(sessionId, content, retryModelName, attempt + 1, options);
        }, WEBSOCKET_RETRY_DELAY_MS);
        return;
      }
      setRunningBySession((current) => ({ ...current, [sessionId]: false }));
      setPartialBySession((current) => ({ ...current, [sessionId]: {} }));
      setStatusBySession((current) => ({
        ...current,
        [sessionId]: serverStarted
          ? "Connection dropped. Saved messages were reloaded."
          : "Connection closed before the council started."
      }));
      setError(
        serverStarted
          ? "WebSocket disconnected before the council finished. I reloaded saved messages; send again if you want to continue."
          : "WebSocket connection closed before the council started."
      );
      refreshMessages(sessionId).catch(() => undefined);
      refreshDebates(sessionId).catch(() => undefined);
      refreshAnalytics(sessionId).catch(() => undefined);
      refreshIntelligence(sessionId).catch(() => undefined);
    };
  }

  function handleSend() {
    if (!selectedId || !selectedSession || runningBySession[selectedId]) {
      return;
    }
    const content = (draftBySession[selectedId] ?? "").trim();
    const modelName = selectedModelName;
    if (!content) {
      return;
    }
    if (content.length > USER_INPUT_MAX_CHARS) {
      setError(`Please shorten your message to ${USER_INPUT_MAX_CHARS} characters or less.`);
      return;
    }
    if (!modelName) {
      setError("Choose one unlocked model before sending.");
      return;
    }

    const sessionId = selectedId;
    if (selectedSession.mode === "ai_vs_human" && !selectedPracticeState?.active) {
      const defaultSide = selectedSettings?.practice_settings?.human_side ?? "Auto";
      setPracticeSideChoice(defaultSide);
      setPracticeStartTarget({ sessionId, content, modelName });
      return;
    }
    setError(null);
    setStatusBySession((current) => ({ ...current, [sessionId]: "Connecting the council..." }));
    setPartialBySession((current) => ({ ...current, [sessionId]: {} }));
    setAssignmentsBySession((current) => ({ ...current, [sessionId]: [] }));
    setRunningBySession((current) => ({ ...current, [sessionId]: true }));
    openInteractionSocket(sessionId, content, modelName, 0);
  }

  function startPracticeFromDialog() {
    if (!practiceStartTarget) {
      return;
    }
    const { sessionId, content, modelName } = practiceStartTarget;
    setPracticeStartTarget(null);
    setError(null);
    setStatusBySession((current) => ({ ...current, [sessionId]: "Starting practice debate..." }));
    setPartialBySession((current) => ({ ...current, [sessionId]: {} }));
    setAssignmentsBySession((current) => ({ ...current, [sessionId]: [] }));
    setRunningBySession((current) => ({ ...current, [sessionId]: true }));
    openInteractionSocket(sessionId, content, modelName, 0, { practiceSide: practiceSideChoice });
  }

  function handleEndPracticeDebate() {
    if (!selectedId || !selectedModelName || runningBySession[selectedId]) {
      return;
    }
    const sessionId = selectedId;
    setError(null);
    setStatusBySession((current) => ({ ...current, [sessionId]: "Ending practice debate..." }));
    setRunningBySession((current) => ({ ...current, [sessionId]: true }));
    openInteractionSocket(sessionId, "", selectedModelName, 0, {
      eventType: "end_practice_debate"
    });
  }

  function handleDebateEvent(sessionId: string, event: DebateEvent) {
    if (event.type === "debate_started") {
      setAssignmentsBySession((current) => ({ ...current, [sessionId]: event.assignments }));
      setDebatesBySession((current) => {
        const currentDebates = current[sessionId] ?? [];
        const withoutCurrent = currentDebates.filter((debate) => debate.id !== event.debate.id);
        return { ...current, [sessionId]: [event.debate, ...withoutCurrent] };
      });
      setSelectedDebateBySession((current) => ({ ...current, [sessionId]: event.debate.id }));
      setAnalyticsBySession((current) => removeKey(current, sessionId));
      setAnalyticsHistoryBySession((current) => ({ ...current, [sessionId]: [] }));
      setStatusBySession((current) => ({
        ...current,
        [sessionId]: event.positions
          ? `${event.positions.pro} ${event.positions.con}`
          : `Pro argues that this position is correct: ${event.topic}. Con argues that this position is wrong or too weak: ${event.topic}.`
      }));
      return;
    }

    if (event.type === "practice_started") {
      setPracticeStateBySession((current) => ({ ...current, [sessionId]: event.state }));
      setDebatesBySession((current) => {
        const currentDebates = current[sessionId] ?? [];
        const withoutCurrent = currentDebates.filter((debate) => debate.id !== event.debate.id);
        return { ...current, [sessionId]: [event.debate, ...withoutCurrent] };
      });
      setSelectedDebateBySession((current) => ({ ...current, [sessionId]: event.debate.id }));
      setStatusBySession((current) => ({
        ...current,
        [sessionId]: event.state.side_reason || "Practice debate started."
      }));
      return;
    }

    if (event.type === "practice_state_updated") {
      setPracticeStateBySession((current) => ({ ...current, [sessionId]: event.state }));
      if (event.state.ending) {
        setStatusBySession((current) => ({
          ...current,
          [sessionId]: "Practice debate is ending. Judge and Trainer are reviewing."
        }));
      }
      return;
    }

    if (event.type === "team_preparation_started") {
      setTeamPreparingBySession((current) => ({ ...current, [sessionId]: true }));
      setStatusBySession((current) => ({ ...current, [sessionId]: event.message }));
      return;
    }

    if (event.type === "team_preparation_completed") {
      setTeamPreparingBySession((current) => ({ ...current, [sessionId]: false }));
      setStatusBySession((current) => ({ ...current, [sessionId]: event.message }));
      refreshIntelligence(sessionId, event.debate_id).catch(() => undefined);
      return;
    }

    if (event.type === "interaction_started") {
      setAssignmentsBySession((current) => ({ ...current, [sessionId]: [] }));
      setStatusBySession((current) => ({
        ...current,
        [sessionId]:
          event.mode === "practice"
            ? "AI Strategist is responding."
            : "Chat response in progress."
      }));
      return;
    }

    if (event.type === "message_started") {
      setPartialBySession((current) => ({
        ...current,
        [sessionId]: {
          ...(current[sessionId] ?? {}),
          [event.stream_id]: event.message
        }
      }));
      return;
    }

    if (event.type === "message_delta") {
      setPartialBySession((current) => {
        const sessionPartials = current[sessionId] ?? {};
        const existing = sessionPartials[event.stream_id];
        if (!existing) {
          return current;
        }
        return {
          ...current,
          [sessionId]: {
            ...sessionPartials,
            [event.stream_id]: {
              ...existing,
              content: existing.content + event.delta
            }
          }
        };
      });
      return;
    }

    if (event.type === "message_replaced") {
      setPartialBySession((current) => {
        const sessionPartials = current[sessionId] ?? {};
        const existing = sessionPartials[event.stream_id];
        if (!existing) {
          return current;
        }
        return {
          ...current,
          [sessionId]: {
            ...sessionPartials,
            [event.stream_id]: {
              ...existing,
              content: event.content
            }
          }
        };
      });
      return;
    }

    if (event.type === "message_completed") {
      setMessagesBySession((current) => {
        const currentMessages = current[sessionId] ?? [];
        return {
          ...current,
          [sessionId]: [
            ...currentMessages.filter((message) => message.id !== event.message.id),
            event.message
          ].sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0))
        };
      });
      setPartialBySession((current) => {
        const sessionPartials = { ...(current[sessionId] ?? {}) };
        delete sessionPartials[event.stream_id];
        return { ...current, [sessionId]: sessionPartials };
      });
      return;
    }

    if (event.type === "analysis_updated") {
      setAnalyticsBySession((current) => ({ ...current, [sessionId]: event.analysis }));
      setAnalyticsHistoryBySession((current) => ({
        ...current,
        [sessionId]: mergeAnalyticsHistory(current[sessionId] ?? [], event.analysis)
      }));
      refreshIntelligence(sessionId, event.analysis.source?.debate_id).catch(() => undefined);
      return;
    }

    if (event.type === "practice_completed") {
      setPracticeStateBySession((current) => ({ ...current, [sessionId]: { active: false } }));
      refreshUserProfileOverview().catch(() => undefined);
      return;
    }

    if (event.type === "debate_completed" || event.type === "interaction_completed") {
      if (event.type === "debate_completed") {
        setPracticeStateBySession((current) => ({ ...current, [sessionId]: { active: false } }));
      }
      setStatusBySession((current) => ({
        ...current,
        [sessionId]:
          event.type === "debate_completed"
            ? "Strategic outcome complete."
            : event.mode === "practice"
              ? "AI Strategist response complete."
              : "Response complete."
      }));
      setRunningBySession((current) => ({ ...current, [sessionId]: false }));
      socketRefs.current[sessionId]?.close();
      refreshSessions().catch(() => undefined);
      refreshModels().catch(() => undefined);
      refreshMessages(sessionId).catch(() => undefined);
      refreshDebates(sessionId).catch(() => undefined);
      refreshAnalytics(sessionId).catch(() => undefined);
      refreshIntelligence(sessionId).catch(() => undefined);
      refreshPracticeState(sessionId).catch(() => undefined);
      refreshAgentExperienceOverview().catch(() => undefined);
      refreshUserProfileOverview().catch(() => undefined);
      return;
    }

    if (event.type === "error") {
      setError(formatErrorMessage(event.message));
      setStatusBySession((current) => ({ ...current, [sessionId]: "Stopped." }));
      setRunningBySession((current) => ({ ...current, [sessionId]: false }));
      socketRefs.current[sessionId]?.close();
      refreshModels().catch(() => undefined);
      refreshAgentExperienceOverview().catch(() => undefined);
      return;
    }
  }

  return (
    <div className="flex h-screen min-h-screen flex-col md:flex-row">
      <Sidebar
        sessions={sessions}
        selectedId={selectedId}
        maxSessions={MAX_SESSIONS}
        workspaceView={workspaceView}
        onNew={handleNewSession}
        onDeleteAll={() => {
          setDeleteAllError(null);
          setDeleteAllOpen(true);
        }}
        onSelect={handleSelect}
        onHome={handleHome}
        onAiExperiences={() => {
          setWorkspaceView("aiExperiences");
          setError(null);
        }}
        onUserProfile={() => {
          setWorkspaceView("userProfile");
          setError(null);
        }}
        onCouncilSettings={() => {
          setWorkspaceView("councilSettings");
          setError(null);
        }}
      />
      {workspaceView === "aiExperiences" || workspaceView === "userProfile" ? (
        <GlobalWorkspace
          view={workspaceView === "aiExperiences" ? "aiExperiences" : "userProfile"}
          sessions={sessions}
          models={models}
          experiences={agentExperienceOverview}
          profileOverview={userProfileOverview}
          onCreateSession={openNewSessionModal}
        />
      ) : workspaceView === "session" && !selectedSession ? (
        <GlobalWorkspace
          view="welcome"
          sessions={sessions}
          models={models}
          experiences={agentExperienceOverview}
          profileOverview={userProfileOverview}
          onCreateSession={openNewSessionModal}
        />
      ) : (
        <DebateRoom
          selectedSession={selectedSession}
          messages={selectedMessages}
          partialMessages={selectedPartials}
          models={models}
          topic={selectedDraft}
          status={selectedStatus}
          error={error}
          assignments={selectedAssignments}
          currentRound={selectedCurrentRound}
          totalRounds={selectedTotalRounds}
          activeSpeaker={selectedActiveSpeaker}
          streamingStatus={selectedStreamingStatus}
          debates={selectedDebates}
          selectedDebateId={selectedDebateId}
          analytics={selectedAnalytics}
          realtimeAnalytics={selectedRealtimeAnalytics}
          analyticsHistory={selectedAnalyticsHistory}
          intelligence={selectedIntelligence}
          practiceState={selectedPracticeState}
          isTeamPreparing={selectedTeamPreparing}
          showCouncilSettings={workspaceView === "councilSettings"}
          councilSettings={councilSettings}
          settings={selectedSettings}
          isRunning={selectedRunning}
          selectedModelName={selectedModelName}
          activePanel={activePanel}
          renamingSessionId={renamingSessionId}
          onPanelChange={setActivePanel}
          onTopicChange={handleDraftChange}
          onModelChange={handleModelChange}
          onDebateChange={handleDebateChange}
          onSend={handleSend}
          onEndPractice={handleEndPracticeDebate}
          onNewDebate={() => setNewChatOpen(true)}
          onSettingsChange={handleUpdateSettings}
          onCouncilSettingsChange={handleUpdateCouncilSettings}
          onResetUniversalIdentities={handleResetUniversalIdentities}
          onResetUserDebateProfile={handleResetUserDebateProfile}
          onFeedbackSubmit={handleSubmitFeedback}
          onVerdictReview={handleVerdictReview}
          onRename={handleRename}
          onRenameDebate={handleRenameDebate}
          onDeleteRequest={(session) => {
            if (councilSettings?.confirmation_preferences?.delete_chat) {
              handleConfirmDelete(session).catch(() => undefined);
              return;
            }
            setDeleteError(null);
            setDeleteTarget(session);
          }}
          onDeleteDebateRequest={(session, debate) => {
            setDeleteDebateError(null);
            setDeleteDebateTarget({ session, debate });
          }}
          onClearRequest={(session, mode) => {
            const key = mode === "history" ? "clear_chat_history" : "clear_chat_memory";
            if (councilSettings?.confirmation_preferences?.[key]) {
              handleConfirmClear({ session, mode }).catch(() => undefined);
              return;
            }
            setClearError(null);
            setClearTarget({ session, mode });
          }}
        />
      )}
      {newChatOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={() => setNewChatOpen(false)} />
          <div className="relative w-full max-w-4xl bg-zinc-950 border border-white/10 rounded-2xl p-6 shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto">
            <SessionSpawner
              models={models}
              onSpawn={(draft, topic) => {
                setNewChatDraft(draft);
                handleCreateSessionFromDraft(draft, topic);
              }}
              onCancel={() => setNewChatOpen(false)}
              isCreating={creatingSession}
              initialDraft={newChatDraft}
            />
          </div>
        </div>
      ) : null}
      {practiceStartTarget ? (
        <PracticeStartDialog
          side={practiceSideChoice}
          onSideChange={setPracticeSideChoice}
          onCancel={() => setPracticeStartTarget(null)}
          onConfirm={startPracticeFromDialog}
        />
      ) : null}
      {deleteTarget ? (
        <ConfirmDialog
          title="Delete chat"
          body={`Delete "${deleteTarget.name}"? This removes its messages and settings.`}
          confirmLabel="Delete"
          suppressLabel="Do Not Display This Message Next Time"
          isWorking={deletingSessionId === deleteTarget.id}
          error={deleteError}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={(suppress) => handleConfirmDelete(undefined, Boolean(suppress))}
        />
      ) : null}
      {deleteAllOpen ? (
        <ConfirmDialog
          title="Delete all chats"
          body="Delete every chat session? Messages, debates, per-chat settings, and chat-scoped memories will be removed. Council Settings and universal experience will stay."
          confirmLabel="Delete All Chats"
          isWorking={deletingAllSessions}
          error={deleteAllError}
          onCancel={() => setDeleteAllOpen(false)}
          onConfirm={() => handleConfirmDeleteAll()}
        />
      ) : null}
      {clearTarget ? (
        <ConfirmDialog
          title={
            clearTarget.mode === "history"
              ? "Clear chat history"
              : "Clear chat memory and history"
          }
          body={
            clearTarget.mode === "history"
              ? `Clear visible history for "${clearTarget.session.name}"? Messages, debates, and graphs will disappear from this chat, but Council Assistant memory will still be kept for future follow-ups.`
              : `Clear memory and visible history for "${clearTarget.session.name}"? Messages, debates, graphs, and saved chat memory for this chat will be permanently removed.`
          }
          confirmLabel={clearTarget.mode === "history" ? "Clear History" : "Clear Memory"}
          suppressLabel="Do Not Display This Message Next Time"
          isWorking={clearingSessionId === clearTarget.session.id}
          error={clearError}
          onCancel={() => setClearTarget(null)}
          onConfirm={(suppress) => handleConfirmClear(undefined, Boolean(suppress))}
        />
      ) : null}
      {deleteDebateTarget ? (
        <ConfirmDialog
          title="Delete debate statistics"
          body={`Delete graphs and statistics for "${deleteDebateTarget.debate.name}"? The messages will stay visible in Strategic Chats.`}
          confirmLabel="Delete Statistics"
          isWorking={deletingDebateId === deleteDebateTarget.debate.id}
          error={deleteDebateError}
          onCancel={() => setDeleteDebateTarget(null)}
          onConfirm={() => handleConfirmDeleteDebate()}
        />
      ) : null}
    </div>
  );
}

function mergeAnalyticsHistory(history: DebateAnalytics[], next: DebateAnalytics) {
  const filtered = history.filter((item) => item.round !== next.round);
  return [...filtered, next].sort((left, right) => left.round - right.round);
}

function removeKey<T>(record: Record<string, T>, key: string) {
  const next = { ...record };
  delete next[key];
  return next;
}

function formatErrorMessage(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatErrorMessage(item)).join("; ");
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "Something went wrong.";
    }
  }
  return String(value || "Something went wrong.");
}

