import React from "react";
import { MessageSquare, Plus, Settings, Cpu } from "lucide-react";
import type { Session } from "../hooks/useAgent";

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  configs: string[];
  selectedConfig: string;
  onSelectConfig: (cfg: string) => void;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  currentSessionId,
  configs,
  selectedConfig,
  onSelectConfig,
  onSelectSession,
  onNewSession,
}) => {
  return (
    <aside className="sidebar flex flex-column">
      <div className="sidebar-brand flex align-items-center gap-2">
        <Cpu size={24} className="brand-icon" />
        <span className="brand-title">Agentic Codex</span>
      </div>

      <button className="new-chat-btn flex align-items-center justify-content-center gap-2" onClick={onNewSession}>
        <Plus size={18} />
        <span>New Session</span>
      </button>

      <div className="sidebar-section">
        <label className="section-label flex align-items-center gap-1">
          <Settings size={14} />
          <span>Config Select</span>
        </label>
        <select
          className="config-select w-full"
          value={selectedConfig}
          onChange={(e) => onSelectConfig(e.target.value)}
        >
          {configs.map((cfg) => (
            <option key={cfg} value={cfg}>
              {cfg.split("/").pop()}
            </option>
          ))}
        </select>
      </div>

      <div className="sidebar-section flex-grow overflow-y-auto">
        <label className="section-label flex align-items-center gap-1 mb-2">
          <MessageSquare size={14} />
          <span>Recent Sessions</span>
        </label>
        <ul className="session-list list-none p-0 m-0">
          {sessions.map((sess) => {
            const isActive = sess.session_id === currentSessionId;
            return (
              <li
                key={sess.session_id}
                className={`session-item ${isActive ? "active" : ""}`}
                onClick={() => onSelectSession(sess.session_id)}
              >
                <div className="session-title text-ellipsis">
                  {sess.last_message || `Session ${sess.session_id.substring(0, 8)}`}
                </div>
                <div className="session-meta">
                  {new Date(sess.updated_at * 1000).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </li>
            );
          })}
          {sessions.length === 0 && (
            <div className="text-muted p-2 text-center text-sm">No history yet</div>
          )}
        </ul>
      </div>
    </aside>
  );
};
