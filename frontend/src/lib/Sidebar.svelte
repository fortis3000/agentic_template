<script lang="ts">
  import { MessageSquare, Plus, Settings, Cpu } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();
</script>

<aside class="sidebar flex flex-column">
  <div class="sidebar-brand flex align-items-center gap-2">
    <Cpu size={24} class="brand-icon" />
    <span class="brand-title">Agentic Dashboard</span>
  </div>

  <button
    class="new-chat-btn flex align-items-center justify-content-center gap-2"
    onclick={() => controller.startNewSession()}
  >
    <Plus size={18} />
    <span>New Session</span>
  </button>

  <div class="sidebar-section">
    <label class="section-label flex align-items-center gap-1">
      <Settings size={14} />
      <span>Config Select</span>
    </label>
    <select class="config-select w-full" bind:value={controller.selectedConfig}>
      {#each controller.configs as cfg}
        <option value={cfg}>
          {cfg.split("/").pop()}
        </option>
      {/each}
    </select>
  </div>

  <div class="sidebar-section flex-grow overflow-y-auto">
    <label class="section-label flex align-items-center gap-1 mb-2">
      <MessageSquare size={14} />
      <span>Recent Sessions</span>
    </label>
    <ul class="session-list list-none p-0 m-0">
      {#each controller.sessions as sess}
        {@const isActive = sess.session_id === controller.sessionId}
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <li
          class="session-item {isActive ? 'active' : ''}"
          onclick={() => controller.loadSession(sess.session_id)}
        >
          <div class="session-title text-ellipsis">
            {sess.last_message || `Session ${sess.session_id.substring(0, 8)}`}
          </div>
          <div class="session-meta">
            {new Date(sess.updated_at * 1000).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        </li>
      {/each}
      {#if controller.sessions.length === 0}
        <div class="text-muted p-2 text-center text-sm">No history yet</div>
      {/if}
    </ul>
  </div>
</aside>
