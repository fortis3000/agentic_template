<script lang="ts">
  import {
    Terminal,
    ChevronDown,
    ChevronRight,
    Play,
    CheckCircle,
    AlertTriangle,
  } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();
  let expandedCalls = $state<Record<string, boolean>>({});

  function toggleExpand(id: string) {
    expandedCalls[id] = !expandedCalls[id];
  }
</script>

<div class="trace-panel flex flex-column h-full">
  <div class="panel-header">
    <h3 class="panel-title flex align-items-center gap-2">
      <Terminal size={18} class="panel-icon" />
      <span>Execution Trace</span>
    </h3>
  </div>

  <div class="trace-content flex-grow overflow-y-auto p-3">
    {#each controller.toolCalls as call}
      {@const isExpanded = !!expandedCalls[call.id]}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="trace-item border-radius-sm mb-2 {call.status}">
        <div
          class="trace-item-header flex align-items-center justify-content-between p-2 pointer"
          onclick={() => toggleExpand(call.id)}
        >
          <div class="flex align-items-center gap-2">
            {#if call.status === "running"}
              <Play size={14} class="tool-icon spinning text-primary" />
            {:else if call.status === "completed"}
              <CheckCircle size={14} class="tool-icon text-success" />
            {:else if call.status === "error"}
              <AlertTriangle size={14} class="tool-icon text-error" />
            {/if}
            <span class="tool-name font-mono text-sm">{call.name}</span>
          </div>
          <div class="flex align-items-center gap-1">
            <span class="tool-status text-xs uppercase">{call.status}</span>
            {#if isExpanded}
              <ChevronDown size={14} />
            {:else}
              <ChevronRight size={14} />
            {/if}
          </div>
        </div>

        {#if isExpanded}
          <div class="trace-item-details p-3 font-mono text-xs border-top">
            {#if call.inputs}
              <div class="mb-2">
                <div class="text-muted font-bold mb-1">Inputs:</div>
                <pre
                  class="p-2 border-radius-xs bg-code overflow-x-auto max-h-48">{JSON.stringify(
                    call.inputs,
                    null,
                    2,
                  )}</pre>
              </div>
            {/if}

            {#if call.status === "completed" && call.output}
              <div>
                <div class="text-success font-bold mb-1">Output:</div>
                <pre
                  class="p-2 border-radius-xs bg-code overflow-x-auto max-h-48">{call.output}</pre>
              </div>
            {/if}

            {#if call.status === "error" && call.error}
              <div>
                <div class="text-error font-bold mb-1">Error:</div>
                <pre
                  class="p-2 border-radius-xs bg-code-error overflow-x-auto max-h-48">{call.error}</pre>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/each}

    {#if controller.toolCalls.length === 0}
      <div class="text-muted text-center p-4 text-sm font-mono">
        Waiting for agent tools execution...
      </div>
    {/if}
  </div>
</div>
