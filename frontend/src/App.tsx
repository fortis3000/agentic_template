import React, { useEffect } from "react";
import { useAgent } from "./hooks/useAgent";
import { Sidebar } from "./components/Sidebar";
import { ChatPanel } from "./components/ChatPanel";
import { TracePanel } from "./components/TracePanel";
import { FileBrowser } from "./components/FileBrowser";

export const App: React.FC = () => {
  const {
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
  } = useAgent();

  // Load initial configurations, session histories, and files
  useEffect(() => {
    fetchConfigs();
    fetchSessions();
    fetchFiles();
  }, [fetchConfigs, fetchSessions, fetchFiles]);

  return (
    <div className="app-container flex w-screen h-screen overflow-hidden">
      <Sidebar
        sessions={sessions}
        currentSessionId={sessionId}
        configs={configs}
        selectedConfig={selectedConfig}
        onSelectConfig={setSelectedConfig}
        onSelectSession={loadSession}
        onNewSession={startNewSession}
      />

      <main className="main-content flex-grow flex">
        {/* Chat Area */}
        <section className="chat-section flex-grow">
          <ChatPanel
            messages={messages}
            isGenerating={isGenerating}
            onSendMessage={sendMessage}
            onStop={stopGeneration}
          />
        </section>

        {/* Info Sidebar Stack */}
        <section className="info-sidebar flex flex-column border-left">
          <div className="trace-section flex-grow overflow-hidden">
            <TracePanel toolCalls={toolCalls} />
          </div>
          <div className="files-section border-top overflow-hidden">
            <FileBrowser files={files} onRefresh={fetchFiles} />
          </div>
        </section>
      </main>
    </div>
  );
};

export default App;
