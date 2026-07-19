<script lang="ts">
  import { FolderOpen, FileText, RefreshCw, File } from "@lucide/svelte";
  import type { AgentController } from "./agent.svelte.ts";

  let { controller }: { controller: AgentController } = $props();

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  const getFileIcon = (name: string) => {
    return (
      name.endsWith(".txt") ||
      name.endsWith(".md") ||
      name.endsWith(".json") ||
      name.endsWith(".pdf") ||
      name.endsWith(".html")
    );
  };
</script>

<div class="file-browser flex flex-column h-full">
  <div class="panel-header flex align-items-center justify-content-between">
    <h3 class="panel-title flex align-items-center gap-2">
      <FolderOpen size={18} class="panel-icon" />
      <span>Workspace Files</span>
    </h3>
    <button
      class="refresh-btn p-1 flex align-items-center justify-content-center border-radius-sm pointer"
      onclick={() => controller.fetchFiles()}
      title="Refresh file list"
    >
      <RefreshCw size={14} />
    </button>
  </div>

  <div class="file-content flex-grow overflow-y-auto p-3">
    <ul class="file-list list-none p-0 m-0">
      {#each controller.files as file}
        <li
          class="file-item flex align-items-center justify-content-between p-2 border-radius-sm mb-1"
        >
          <div class="flex align-items-center gap-2 text-ellipsis flex-grow">
            {#if getFileIcon(file.name)}
              <FileText size={16} class="text-secondary" />
            {:else}
              <File size={16} class="text-muted" />
            {/if}
            <span
              class="file-name font-mono text-sm text-ellipsis"
              title={file.path}
            >
              {file.name}
            </span>
          </div>
          <span
            class="file-size text-xs text-muted font-mono whitespace-nowrap ml-2"
          >
            {formatBytes(file.size)}
          </span>
        </li>
      {/each}
      {#if controller.files.length === 0}
        <div class="text-muted text-center p-4 text-sm font-mono">
          No files in workspace data/ folder yet.
        </div>
      {/if}
    </ul>
  </div>
</div>
