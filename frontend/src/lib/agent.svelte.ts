import { marked } from "marked";
import DOMPurify from "dompurify";

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

export interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
}

const API_BASE = "http://localhost:8000";

export class AgentController {
  // Reactive states using Svelte 5 runes
  messages = $state<Message[]>([]);
  toolCalls = $state<ToolCall[]>([]);
  sessionId = $state<string | null>(null);
  isGenerating = $state<boolean>(false);
  configs = $state<string[]>([]);
  sessions = $state<Session[]>([]);
  files = $state<WorkspaceFile[]>([]);
  selectedConfig = $state<string>("configs/agent_config.yaml");

  private abortController: AbortController | null = null;

  constructor() {
    this.fetchConfigs();
    this.fetchSessions();
    this.fetchFiles();
  }

  // Fetch all available agent config files
  async fetchConfigs() {
    try {
      const res = await fetch(`${API_BASE}/api/configs`);
      const data = await res.json();
      this.configs = data.configs || [];
      if (data.configs && data.configs.length > 0 && !this.selectedConfig) {
        this.selectedConfig = data.configs[0];
      }
    } catch (err) {
      console.error("Failed to fetch configs", err);
    }
  }

  // Fetch session list
  async fetchSessions() {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      const data = await res.json();
      this.sessions = data.sessions || [];
    } catch (err) {
      console.error("Failed to fetch sessions", err);
    }
  }

  // Fetch generated files in workspace data/ folder
  async fetchFiles() {
    try {
      const res = await fetch(`${API_BASE}/api/files`);
      const data = await res.json();
      this.files = data.files || [];
    } catch (err) {
      console.error("Failed to fetch files", err);
    }
  }

  // Load a session's messages
  async loadSession(id: string) {
    try {
      this.sessionId = id;
      const res = await fetch(`${API_BASE}/api/sessions/${id}`);
      const data = await res.json();
      this.messages = data.history || [];
      this.toolCalls = []; // reset tool log trace
    } catch (err) {
      console.error("Failed to load session", err);
    }
  }

  // Delete a session
  async deleteSession(id: string) {
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        // If the deleted session was the active one, clear current session details
        if (this.sessionId === id) {
          this.startNewSession();
        }
        // Refresh sessions list
        this.fetchSessions();
      } else {
        console.error("Failed to delete session on backend");
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  }

  // Cancel running execution
  async stopGeneration() {
    if (!this.sessionId) return;
    try {
      if (this.abortController) {
        this.abortController.abort();
      }
      await fetch(`${API_BASE}/api/agent/stop/${this.sessionId}`, {
        method: "POST",
      });
      this.isGenerating = false;
    } catch (err) {
      console.error("Failed to stop generation", err);
    }
  }

  // Reset state for new chat session
  startNewSession() {
    this.sessionId = null;
    this.messages = [];
    this.toolCalls = [];
  }

  // Send message and process SSE events stream
  async sendMessage(query: string) {
    this.isGenerating = true;
    this.toolCalls = []; // reset tools

    // Add user message
    this.messages = [...this.messages, { role: "user", content: query }];

    let currentSessId = this.sessionId;

    try {
      // 1. Post request to initialize execution task
      const response = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: currentSessId,
          config_path: this.selectedConfig,
          query,
        }),
      });

      const initData = await response.json();
      currentSessId = initData.session_id;
      this.sessionId = currentSessId;

      // 2. Setup AbortController and connect to SSE stream
      this.abortController = new AbortController();
      const streamUrl = `${API_BASE}/api/agent/stream/${currentSessId}`;
      const streamResponse = await fetch(streamUrl, {
        signal: this.abortController.signal,
      });

      const reader = streamResponse.body?.getReader();
      if (!reader) {
        throw new Error("Unable to read stream");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      // Add assistant empty bubble
      this.messages = [...this.messages, { role: "assistant", content: "" }];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || ""; // keep tail in buffer

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
              const lastIdx = this.messages.length - 1;
              if (lastIdx >= 0 && this.messages[lastIdx].role === "assistant") {
                this.messages[lastIdx].content += data.text;
                // Re-assign to trigger Svelte reactivity
                this.messages = [...this.messages];
              }
            } else if (eventType === "tool_start") {
              const uniqueId = `${data.tool}-${Date.now()}`;
              this.toolCalls = [
                ...this.toolCalls,
                {
                  id: uniqueId,
                  name: data.tool,
                  inputs: data.inputs,
                  status: "running",
                },
              ];
            } else if (eventType === "tool_complete") {
              this.toolCalls = this.toolCalls.map((t) =>
                t.name === data.tool && t.status === "running"
                  ? { ...t, status: "completed", output: data.output }
                  : t,
              );
            } else if (eventType === "tool_error") {
              this.toolCalls = this.toolCalls.map((t) =>
                t.name === data.tool && t.status === "running"
                  ? { ...t, status: "error", error: data.error }
                  : t,
              );
            } else if (eventType === "done") {
              const lastIdx = this.messages.length - 1;
              if (lastIdx >= 0 && this.messages[lastIdx].role === "assistant") {
                this.messages[lastIdx].content = data.text;
                this.messages = [...this.messages];
              }
            } else if (eventType === "error") {
              this.messages = [
                ...this.messages,
                { role: "assistant", content: `Error: ${data.text}` },
              ];
            } else if (eventType === "cancelled") {
              const lastIdx = this.messages.length - 1;
              if (lastIdx >= 0 && this.messages[lastIdx].role === "assistant") {
                if (!this.messages[lastIdx].content) {
                  this.messages[lastIdx].content =
                    "Execution cancelled by user.";
                } else {
                  this.messages[lastIdx].content +=
                    "\n\n*[Execution Cancelled]*";
                }
                this.messages = [...this.messages];
              }
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
      this.isGenerating = false;
      this.abortController = null;
      this.fetchSessions();
      this.fetchFiles();
    }
  }

  // Render markdown helper
  renderMarkdown(content: string): string {
    const rawHtml = marked.parse(content || "", { async: false }) as string;
    return DOMPurify.sanitize(rawHtml);
  }
}
