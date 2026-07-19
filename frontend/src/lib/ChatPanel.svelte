<script lang="ts">
  import {
    Send,
    Square,
    Bot,
    User,
    Image as ImageIcon,
    FileText,
    X,
  } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();
  let input = $state("");
  let messagesEnd = $state<HTMLDivElement | null>(null);

  let fileInput = $state<HTMLInputElement | null>(null);
  let fileFileInput = $state<HTMLInputElement | null>(null);
  let attachedImages = $state<
    { data: string; mime_type: string; name: string; willResize?: boolean }[]
  >([]);
  let attachedFiles = $state<
    { data: string; mime_type: string; filename: string; size: number }[]
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
      (!input.trim() &&
        attachedImages.length === 0 &&
        attachedFiles.length === 0) ||
      controller.isGenerating
    )
      return;
    controller.sendMessage(input, attachedImages, attachedFiles);
    input = "";
    attachedImages = [];
    attachedFiles = [];
    errorMessage = "";
  }

  function handleFileChange(e: Event) {
    errorMessage = "";
    const files = (e.target as HTMLInputElement).files;
    if (!files || files.length === 0) return;

    const acceptableTypes = controller.activeConfigDetails
      ?.acceptable_data_types || ["image/png", "image/jpeg", "image/gif"];
    const minWidth = controller.activeConfigDetails?.min_image_width || 128;
    const minHeight = controller.activeConfigDetails?.min_image_height || 128;
    const maxWidth = controller.activeConfigDetails?.max_image_width || 1024;
    const maxHeight = controller.activeConfigDetails?.max_image_height || 1024;

    const filesArray = Array.from(files);

    const validationPromises = filesArray.map((file) => {
      return new Promise<
        | { data: string; mime_type: string; name: string; willResize: boolean }
        | string
      >((resolve) => {
        if (!acceptableTypes.includes(file.type)) {
          resolve(
            `Unsupported image format: ${file.type}. Allowed formats: ${acceptableTypes.join(", ")}`,
          );
          return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
          const dataUrl = event.target?.result as string;
          const img = new Image();
          img.onload = () => {
            if (img.width < minWidth || img.height < minHeight) {
              resolve(
                `Image resolution ${img.width}x${img.height} for "${file.name}" is below the minimum allowed limit of ${minWidth}x${minHeight}.`,
              );
            } else {
              const willResize = img.width > maxWidth || img.height > maxHeight;
              resolve({
                data: dataUrl,
                mime_type: file.type,
                name: file.name,
                willResize,
              });
            }
          };
          img.src = dataUrl;
        };
        reader.readAsDataURL(file);
      });
    });

    Promise.all(validationPromises).then((results) => {
      const errorResult = results.find((r) => typeof r === "string");
      if (errorResult) {
        errorMessage = errorResult as string;
      } else {
        const validImages = results as {
          data: string;
          mime_type: string;
          name: string;
          willResize: boolean;
        }[];
        const newImages = [...attachedImages];
        validImages.forEach((img) => {
          if (!newImages.some((existing) => existing.name === img.name)) {
            newImages.push(img);
          }
        });
        attachedImages = newImages;
      }
    });

    if (fileInput) fileInput.value = "";
  }

  function removeImage(index: number) {
    attachedImages = attachedImages.filter((_, idx) => idx !== index);
  }

  function handleFileFileChange(e: Event) {
    errorMessage = "";
    const files = (e.target as HTMLInputElement).files;
    if (!files || files.length === 0) return;

    const acceptableTypes = controller.activeConfigDetails
      ?.acceptable_file_types || [
      "application/pdf",
      "text/plain",
      "text/markdown",
      "text/html",
    ];
    const maxSize =
      controller.activeConfigDetails?.max_file_size_bytes || 20971520;
    const maxCount = controller.activeConfigDetails?.max_files_per_message || 5;

    const filesArray = Array.from(files);

    // Check total count
    if (attachedFiles.length + filesArray.length > maxCount) {
      errorMessage = `Too many files. Maximum ${maxCount} files per message.`;
      if (fileFileInput) fileFileInput.value = "";
      return;
    }

    for (const file of filesArray) {
      if (!acceptableTypes.includes(file.type)) {
        errorMessage = `Unsupported file type: ${file.type}. Allowed types: ${acceptableTypes.join(", ")}`;
        if (fileFileInput) fileFileInput.value = "";
        return;
      }
      if (file.size > maxSize) {
        const maxMb = (maxSize / (1024 * 1024)).toFixed(0);
        const fileMb = (file.size / (1024 * 1024)).toFixed(1);
        errorMessage = `File "${file.name}" (${fileMb} MB) exceeds the maximum size of ${maxMb} MB.`;
        if (fileFileInput) fileFileInput.value = "";
        return;
      }
    }

    const readPromises = filesArray.map((file) => {
      return new Promise<{
        data: string;
        mime_type: string;
        filename: string;
        size: number;
      }>((resolve) => {
        const reader = new FileReader();
        reader.onload = (event) => {
          resolve({
            data: event.target?.result as string,
            mime_type: file.type,
            filename: file.name,
            size: file.size,
          });
        };
        reader.readAsDataURL(file);
      });
    });

    Promise.all(readPromises).then((results) => {
      const newFiles = [...attachedFiles];
      results.forEach((f) => {
        if (!newFiles.some((existing) => existing.filename === f.filename)) {
          newFiles.push(f);
        }
      });
      attachedFiles = newFiles;
    });

    if (fileFileInput) fileFileInput.value = "";
  }

  function removeFile(index: number) {
    attachedFiles = attachedFiles.filter((_, idx) => idx !== index);
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };
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
            {#if msg.files && msg.files.length > 0}
              <div class="message-files flex flex-wrap gap-2 mt-2">
                {#each msg.files as file}
                  <div class="file-chip flex align-items-center gap-1">
                    <FileText size={14} />
                    <span class="file-chip-name">{file.filename}</span>
                    <span class="file-chip-size"
                      >({formatFileSize(file.size)})</span
                    >
                  </div>
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

  {#if controller.streamInfoMessage}
    <div
      class="error-banner p-2 text-sm text-warning border-top flex align-items-center justify-content-between"
      style="background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border-top: 1px solid rgba(245, 158, 11, 0.2);"
    >
      <span>{controller.streamInfoMessage}</span>
      <button
        type="button"
        class="close-error-btn flex align-items-center"
        style="color: #f59e0b;"
        onclick={() => (controller.streamInfoMessage = null)}
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
          {#if img.willResize}
            <span
              class="resize-badge absolute bottom-0 left-0"
              title="Image exceeds max limits and will be auto-resized by the server"
            >
              Auto-resize
            </span>
          {/if}
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

  {#if attachedFiles.length > 0}
    <div class="attached-files-preview flex flex-wrap gap-2 p-2 border-top">
      {#each attachedFiles as file, idx}
        <div class="file-preview-chip flex align-items-center gap-2">
          <FileText size={14} class="text-secondary" />
          <span class="file-preview-name text-sm font-mono"
            >{file.filename}</span
          >
          <span class="file-preview-size text-xs text-muted"
            >({formatFileSize(file.size)})</span
          >
          <button
            type="button"
            class="remove-file-btn flex align-items-center justify-content-center"
            onclick={() => removeFile(idx)}
            title="Remove file"
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
    <input
      type="file"
      bind:this={fileFileInput}
      onchange={handleFileFileChange}
      accept=".pdf,.txt,.md,.html"
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
    <button
      type="button"
      class="attach-btn flex align-items-center justify-content-center"
      onclick={() => fileFileInput?.click()}
      disabled={controller.isGenerating}
      title="Attach File (PDF, TXT, MD, HTML)"
    >
      <FileText size={16} />
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
      disabled={(!input.trim() &&
        attachedImages.length === 0 &&
        attachedFiles.length === 0) ||
        controller.isGenerating}
    >
      <Send size={16} />
    </button>
  </form>
</div>
