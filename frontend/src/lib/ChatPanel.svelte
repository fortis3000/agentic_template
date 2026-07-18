<script lang="ts">
  import {
    Send,
    Square,
    Bot,
    User,
    Image as ImageIcon,
    X,
  } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();
  let input = $state("");
  let messagesEnd = $state<HTMLDivElement | null>(null);

  let fileInput = $state<HTMLInputElement | null>(null);
  let attachedImages = $state<
    { data: string; mime_type: string; name: string }[]
  >([]);
  let errorMessage = $state("");

  // Scroll to bottom on messages updates
  $effect(() => {
    if (controller.messages) {
      messagesEnd?.scrollIntoView({ behavior: "smooth" });
    }
  });

  function handleSubmit(e: Event) {
    e.preventDefault();
    if (
      (!input.trim() && attachedImages.length === 0) ||
      controller.isGenerating
    )
      return;
    controller.sendMessage(input, attachedImages);
    input = "";
    attachedImages = [];
    errorMessage = "";
  }

  function handleFileChange(e: Event) {
    errorMessage = "";
    const files = (e.target as HTMLInputElement).files;
    if (!files) return;

    const acceptableTypes = controller.activeConfigDetails
      ?.acceptable_data_types || ["image/png", "image/jpeg", "image/gif"];
    const minWidth = controller.activeConfigDetails?.min_image_width || 128;
    const minHeight = controller.activeConfigDetails?.min_image_height || 128;

    Array.from(files).forEach((file) => {
      // 1. Validate mime type
      if (!acceptableTypes.includes(file.type)) {
        errorMessage = `Unsupported image format: ${file.type}. Allowed formats: ${acceptableTypes.join(", ")}`;
        return;
      }

      // 2. Read file to validate dimensions
      const reader = new FileReader();
      reader.onload = (event) => {
        const dataUrl = event.target?.result as string;
        const img = new Image();
        img.onload = () => {
          if (img.width < minWidth || img.height < minHeight) {
            errorMessage = `Image resolution ${img.width}x${img.height} is below the minimum allowed limit of ${minWidth}x${minHeight}.`;
          } else {
            // Check if already attached
            if (
              !attachedImages.some((existing) => existing.name === file.name)
            ) {
              attachedImages = [
                ...attachedImages,
                { data: dataUrl, mime_type: file.type, name: file.name },
              ];
            }
          }
        };
        img.src = dataUrl;
      };
      reader.readAsDataURL(file);
    });

    // Reset file input value so same file can be selected again
    if (fileInput) fileInput.value = "";
  }

  function removeImage(index: number) {
    attachedImages = attachedImages.filter((_, idx) => idx !== index);
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
            {#if msg.images && msg.images.length > 0}
              <div class="message-images flex flex-wrap gap-2 mt-2">
                {#each msg.images as img}
                  <img
                    src={img.data}
                    alt="User uploaded attachment"
                    class="attached-msg-img"
                  />
                {/each}
              </div>
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

  {#if errorMessage}
    <div
      class="error-banner p-2 text-sm text-danger border-top flex align-items-center justify-content-between"
    >
      <span>{errorMessage}</span>
      <button
        type="button"
        class="close-error-btn flex align-items-center"
        onclick={() => (errorMessage = "")}
      >
        <X size={14} />
      </button>
    </div>
  {/if}

  {#if attachedImages.length > 0}
    <div class="attached-images-preview flex flex-wrap gap-2 p-2 border-top">
      {#each attachedImages as img, idx}
        <div class="preview-thumbnail-wrapper relative">
          <img src={img.data} alt={img.name} class="preview-thumbnail" />
          <button
            type="button"
            class="remove-img-btn absolute flex align-items-center justify-content-center"
            onclick={() => removeImage(idx)}
            title="Remove attachment"
          >
            <X size={10} />
          </button>
        </div>
      {/each}
    </div>
  {/if}

  <form
    class="chat-input-container p-3 flex gap-2 align-items-center"
    onsubmit={handleSubmit}
  >
    <input
      type="file"
      bind:this={fileInput}
      onchange={handleFileChange}
      accept={controller.activeConfigDetails?.acceptable_data_types?.join(",")}
      multiple
      style="display: none;"
    />
    <button
      type="button"
      class="attach-btn flex align-items-center justify-content-center"
      onclick={() => fileInput?.click()}
      disabled={controller.isGenerating}
      title="Attach Image"
    >
      <ImageIcon size={16} />
    </button>
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
      disabled={(!input.trim() && attachedImages.length === 0) ||
        controller.isGenerating}
    >
      <Send size={16} />
    </button>
  </form>
</div>
