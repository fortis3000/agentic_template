<script lang="ts">
  import { AgentController } from "./lib/agent.svelte";
  import Sidebar from "./lib/Sidebar.svelte";
  import ChatPanel from "./lib/ChatPanel.svelte";
  import TracePanel from "./lib/TracePanel.svelte";
  import FileBrowser from "./lib/FileBrowser.svelte";

  const controller = new AgentController();
</script>

<div class="app-container flex w-screen h-screen overflow-hidden">
  <Sidebar {controller} />

  <main class="main-content flex-grow flex">
    <!-- Chat Area -->
    <section class="chat-section flex-grow">
      <ChatPanel {controller} />
    </section>

    <!-- Info Sidebar Stack -->
    <section class="info-sidebar flex flex-column border-left">
      <div class="trace-section flex-grow overflow-hidden">
        <TracePanel {controller} />
      </div>
      <div class="files-section border-top overflow-hidden">
        <FileBrowser {controller} />
      </div>
    </section>
  </main>
</div>
