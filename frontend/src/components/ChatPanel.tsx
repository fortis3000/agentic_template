import React, { useState, useRef, useEffect } from "react";
import { Send, Square, Bot, User } from "lucide-react";
import type { Message } from "../hooks/useAgent";
import { marked } from "marked";

interface ChatPanelProps {
  messages: Message[];
  isGenerating: boolean;
  onSendMessage: (query: string) => void;
  onStop: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  isGenerating,
  onSendMessage,
  onStop,
}) => {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating) return;
    onSendMessage(input);
    setInput("");
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const renderContent = (content: string) => {
    // Synchronously parse markdown to HTML with marked
    const html = marked.parse(content || "", { async: false }) as string;
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="chat-panel flex flex-column h-full">
      <div className="panel-header flex align-items-center justify-content-between">
        <h3 className="panel-title flex align-items-center gap-2">
          <Bot size={18} className="panel-icon" />
          <span>Agent Workspace Chat</span>
        </h3>
        {isGenerating && (
          <button
            className="stop-btn flex align-items-center gap-1"
            onClick={onStop}
          >
            <Square size={12} fill="currentColor" />
            <span>Stop Agent</span>
          </button>
        )}
      </div>

      <div className="chat-messages flex-grow overflow-y-auto p-3">
        {messages.map((msg, idx) => {
          const isAssistant = msg.role === "assistant";
          return (
            <div key={idx} className={`message-wrapper ${msg.role}`}>
              <div className="message-avatar flex align-items-center justify-content-center">
                {isAssistant ? <Bot size={16} /> : <User size={16} />}
              </div>
              <div className="message-bubble flex flex-column">
                <div className="message-sender">
                  {isAssistant ? "Agent" : "User"}
                </div>
                <div className="message-text">
                  {msg.content ? (
                    renderContent(msg.content)
                  ) : (
                    <span className="streaming-cursor">█</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {messages.length === 0 && (
          <div className="chat-welcome flex flex-column align-items-center justify-content-center h-full text-center p-4">
            <Bot size={48} className="welcome-logo mb-3" />
            <h2>Welcome to Agentic Codex</h2>
            <p className="text-muted text-sm max-w-sm">
              Ask the agent to perform actions, execute workflows, or call
              custom tools. Everything streams in real-time.
            </p>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form
        className="chat-input-container p-3 flex gap-2"
        onSubmit={handleSubmit}
      >
        <input
          type="text"
          className="chat-input flex-grow"
          placeholder="Ask the agent something..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isGenerating}
        />
        <button
          type="submit"
          className="send-btn flex align-items-center justify-content-center"
          disabled={!input.trim() || isGenerating}
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
};
