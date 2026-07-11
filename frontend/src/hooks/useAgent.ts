import { useState, useCallback, useRef } from "react";

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ToolCall {
  id: string;
  name: string;
  inputs?: any;
  output?: string;
  status: "running" | "completed" | "error";
  error?: string;
}

export interface Session {
  session_id: string;
  last_message: string;
  updated_at: number;
}

const API_BASE = "http://localhost:8000";

export function useAgent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [configs, setConfigs] = useState<string[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [files, setFiles] = useState<any[]>([]);
  const [selectedConfig, setSelectedConfig] = useState<string>(
    "configs/agent_config.yaml",
  );

  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch all sessions
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error("Failed to fetch sessions", err);
    }
  }, []);

  // Fetch configs
  const fetchConfigs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/configs`);
      const data = await res.json();
      setConfigs(data.configs || []);
      if (data.configs && data.configs.length > 0) {
        setSelectedConfig(data.configs[0]);
      }
    } catch (err) {
      console.error("Failed to fetch configs", err);
    }
  }, []);

  // Fetch files in workspace data/ directory
  const fetchFiles = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/files`);
      const data = await res.json();
      setFiles(data.files || []);
    } catch (err) {
      console.error("Failed to fetch files", err);
    }
  }, []);

  // Load selected session messages
  const loadSession = useCallback(async (id: string) => {
    try {
      setSessionId(id);
      const res = await fetch(`${API_BASE}/api/sessions/${id}`);
      const data = await res.json();
      setMessages(data.history || []);
      setToolCalls([]); // reset tools logs
    } catch (err) {
      console.error("Failed to load session", err);
    }
  }, []);

  // Stop/cancel current execution
  const stopGeneration = useCallback(async () => {
    if (!sessionId) return;
    try {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      await fetch(`${API_BASE}/api/agent/stop/${sessionId}`, {
        method: "POST",
      });
      setIsGenerating(false);
    } catch (err) {
      console.error("Failed to stop generation", err);
    }
  }, [sessionId]);

  // Send a message & read SSE stream
  const sendMessage = useCallback(
    async (query: string) => {
      setIsGenerating(true);
      setToolCalls([]); // clear tool calls for new turn

      // Append user message immediately
      const newMessages: Message[] = [
        ...messages,
        { role: "user", content: query },
      ];
      setMessages(newMessages);

      let currentSessId = sessionId;

      try {
        // 1. Post chat request
        const response = await fetch(`${API_BASE}/api/agent/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: currentSessId,
            config_path: selectedConfig,
            query,
          }),
        });

        const initData = await response.json();
        currentSessId = initData.session_id;
        setSessionId(currentSessId);

        // 2. Open EventSource / Fetch reader for SSE
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const streamUrl = `${API_BASE}/api/agent/stream/${currentSessId}`;
        const streamResponse = await fetch(streamUrl, {
          signal: controller.signal,
        });

        const reader = streamResponse.body?.getReader();
        if (!reader) {
          throw new Error("Unable to read stream");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        // Add assistant placeholder message
        setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || ""; // keep incomplete last part in buffer

          for (const part of parts) {
            if (!part.trim()) continue;

            const lines = part.split("\n");
            let eventType = "";
            let eventDataStr = "";

            for (const line of lines) {
              if (line.startsWith("event: ")) {
                eventType = line.substring(7).trim();
              } else if (line.startsWith("data: ")) {
                eventDataStr = line.substring(6).trim();
              }
            }

            if (!eventDataStr) continue;

            try {
              const data = JSON.parse(eventDataStr);

              if (eventType === "token") {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                    updated[lastIdx].content += data.text;
                  }
                  return updated;
                });
              } else if (eventType === "tool_start") {
                const uniqueId = `${data.tool}-${Date.now()}`;
                setToolCalls((prev) => [
                  ...prev,
                  {
                    id: uniqueId,
                    name: data.tool,
                    inputs: data.inputs,
                    status: "running",
                  },
                ]);
              } else if (eventType === "tool_complete") {
                setToolCalls((prev) =>
                  prev.map((t) =>
                    t.name === data.tool && t.status === "running"
                      ? { ...t, status: "completed", output: data.output }
                      : t,
                  ),
                );
              } else if (eventType === "tool_error") {
                setToolCalls((prev) =>
                  prev.map((t) =>
                    t.name === data.tool && t.status === "running"
                      ? { ...t, status: "error", error: data.error }
                      : t,
                  ),
                );
              } else if (eventType === "done") {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                    updated[lastIdx].content = data.text;
                  }
                  return updated;
                });
              } else if (eventType === "error") {
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: `Error: ${data.text}` },
                ]);
              } else if (eventType === "cancelled") {
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                    if (!updated[lastIdx].content) {
                      updated[lastIdx].content = "Execution cancelled by user.";
                    } else {
                      updated[lastIdx].content += "\n\n*[Execution Cancelled]*";
                    }
                  }
                  return updated;
                });
              }
            } catch (err) {
              console.error("Error parsing event JSON", err);
            }
          }
        }
      } catch (err: any) {
        if (err.name !== "AbortError") {
          console.error("Stream parsing error", err);
        }
      } finally {
        setIsGenerating(false);
        abortControllerRef.current = null;
        fetchSessions();
        fetchFiles();
      }
    },
    [messages, sessionId, selectedConfig, fetchSessions, fetchFiles],
  );

  const startNewSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setToolCalls([]);
  }, []);

  return {
    messages,
    toolCalls,
    sessionId,
    isGenerating,
    configs,
    sessions,
    files,
    selectedConfig,
    setSelectedConfig,
    fetchSessions,
    fetchConfigs,
    fetchFiles,
    loadSession,
    sendMessage,
    stopGeneration,
    startNewSession,
  };
}
