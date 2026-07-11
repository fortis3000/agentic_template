import React, { useState } from "react";
import {
  Terminal,
  ChevronDown,
  ChevronRight,
  Play,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import type { ToolCall } from "../hooks/useAgent";

interface TracePanelProps {
  toolCalls: ToolCall[];
}

export const TracePanel: React.FC<TracePanelProps> = ({ toolCalls }) => {
  const [expandedCalls, setExpandedCalls] = useState<Record<string, boolean>>(
    {},
  );

  const toggleExpand = (id: string) => {
    setExpandedCalls((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const getStatusIcon = (status: ToolCall["status"]) => {
    switch (status) {
      case "running":
        return <Play size={14} className="tool-icon spinning text-primary" />;
      case "completed":
        return <CheckCircle size={14} className="tool-icon text-success" />;
      case "error":
        return <AlertTriangle size={14} className="tool-icon text-error" />;
    }
  };

  return (
    <div className="trace-panel flex flex-column h-full">
      <div className="panel-header">
        <h3 className="panel-title flex align-items-center gap-2">
          <Terminal size={18} className="panel-icon" />
          <span>Execution Trace</span>
        </h3>
      </div>

      <div className="trace-content flex-grow overflow-y-auto p-3">
        {toolCalls.map((call) => {
          const isExpanded = !!expandedCalls[call.id];
          return (
            <div
              key={call.id}
              className={`trace-item border-radius-sm mb-2 ${call.status}`}
            >
              <div
                className="trace-item-header flex align-items-center justify-content-between p-2 pointer"
                onClick={() => toggleExpand(call.id)}
              >
                <div className="flex align-items-center gap-2">
                  {getStatusIcon(call.status)}
                  <span className="tool-name font-mono text-sm">
                    {call.name}
                  </span>
                </div>
                <div className="flex align-items-center gap-1">
                  <span className="tool-status text-xs uppercase">
                    {call.status}
                  </span>
                  {isExpanded ? (
                    <ChevronDown size={14} />
                  ) : (
                    <ChevronRight size={14} />
                  )}
                </div>
              </div>

              {isExpanded && (
                <div className="trace-item-details p-3 font-mono text-xs border-top">
                  {call.inputs && (
                    <div className="mb-2">
                      <div className="text-muted font-bold mb-1">Inputs:</div>
                      <pre className="p-2 border-radius-xs bg-code overflow-x-auto max-h-48">
                        {JSON.stringify(call.inputs, null, 2)}
                      </pre>
                    </div>
                  )}

                  {call.status === "completed" && call.output && (
                    <div>
                      <div className="text-success font-bold mb-1">Output:</div>
                      <pre className="p-2 border-radius-xs bg-code overflow-x-auto max-h-48">
                        {call.output}
                      </pre>
                    </div>
                  )}

                  {call.status === "error" && call.error && (
                    <div>
                      <div className="text-error font-bold mb-1">Error:</div>
                      <pre className="p-2 border-radius-xs bg-code-error overflow-x-auto max-h-48">
                        {call.error}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {toolCalls.length === 0 && (
          <div className="text-muted text-center p-4 text-sm font-mono">
            Waiting for agent tools execution...
          </div>
        )}
      </div>
    </div>
  );
};
