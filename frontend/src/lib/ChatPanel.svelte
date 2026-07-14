<script lang="ts">
  import { Send, Square, Bot, User } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();
  let input = $state("");
  let messagesEnd = $state<HTMLDivElement | null>(null);

  // Scroll to bottom on messages updates
  $effect(() => {
    if (controller.messages) {
      messagesEnd?.scrollIntoView({ behavior: "smooth" });
    }
  });

  function handleSubmit(e: Event) {
    e.preventDefault();
    if (!input.trim() || controller.isGenerating) return;
    controller.sendMessage(input);
    input = "";
  }
</script>

<div class="chat-panel flex flex-column h-full">
  <div class="panel-header flex align-items-center justify-content-between">
    <h3 class="panel-title flex align-items-center gap-2">
      <Bot size={18} class="panel-icon" />
      <span>Agent Workspace Chat</span>
    </h3>
    {#if controller.isGenerating}
      <button
        class="stop-btn flex align-items-center gap-1"
        onclick={() => controller.stopGeneration()}
      >
        <Square size={12} fill="currentColor" />
        <span>Stop Agent</span>
      </button>
    {/if}
  </div>

  <div class="chat-messages flex-grow overflow-y-auto p-3">
    {#each controller.messages as msg}
      {@const isAssistant = msg.role === "assistant"}
      <div class="message-wrapper {msg.role}">
        <div
          class="message-avatar flex align-items-center justify-content-center"
        >
          {#if isAssistant}
            <Bot size={16} />
          {:else}
            <User size={16} />
          {/if}
        </div>
        <div class="message-bubble flex flex-column">
          <div class="message-sender">{isAssistant ? "Agent" : "User"}</div>
          <div class="message-text">
            {#if msg.content}
              <!-- eslint-disable-next-line svelte/no-at-html-tags -->
              {@html controller.renderMarkdown(msg.content)}
            {:else}
              <span class="streaming-cursor">█</span>
            {/if}
          </div>
        </div>
      </div>
    {/each}

    {#if controller.messages.length === 0}
      <div
        class="chat-welcome flex flex-column align-items-center justify-content-center h-full text-center p-4"
      >
        <Bot size={48} class="welcome-logo mb-3" />
        <h2>Welcome to Agentic Dashboard</h2>
        <p class="text-muted text-sm max-w-sm">
          Ask the agent to perform actions, execute workflows, or call custom
          tools. Everything streams in real-time.
        </p>
      </div>
    {/if}
    <div bind:this={messagesEnd}></div>
  </div>

  <form class="chat-input-container p-3 flex gap-2" onsubmit={handleSubmit}>
    <input
      type="text"
      class="chat-input flex-grow"
      placeholder="Ask the agent something..."
      bind:value={input}
      disabled={controller.isGenerating}
    />
    <button
      type="submit"
      class="send-btn flex align-items-center justify-content-center"
      disabled={!input.trim() || controller.isGenerating}
    >
      <Send size={16} />
    </button>
  </form>
</div>
