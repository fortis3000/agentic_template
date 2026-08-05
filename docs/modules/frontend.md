# User Frontend UI Subsystem (`frontend/`)

This document provides complete architectural documentation for the frontend web application, built with **Svelte 5**, **TypeScript**, **Vite**, and **Tailwind CSS**.

---

## 1. Overview & UI Design Goals

The frontend application provides a modern, responsive web workspace for interacting with agents, uploading multimodal context (images & documents), inspecting tool execution logs, and viewing Arize Phoenix trace links.

Key files:
- [`frontend/src/App.svelte`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/App.svelte): Main shell layout and component orchestrator.
- [`frontend/src/lib/agent.svelte.ts`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/lib/agent.svelte.ts): Svelte 5 reactive state controller (`$state`) for agent chat sessions, streaming tokens, and API requests.
- [`frontend/src/lib/ChatPanel.svelte`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/lib/ChatPanel.svelte): Message list, input bar, file/image upload modal, and SSE streaming token renderer.
- [`frontend/src/lib/Sidebar.svelte`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/lib/Sidebar.svelte): Navigation panel, session manager, and model configuration selector.
- [`frontend/src/lib/TracePanel.svelte`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/lib/TracePanel.svelte): Live execution timeline, tool call inputs/outputs, and Arize Phoenix trace drawer link.
- [`frontend/src/lib/FileBrowser.svelte`](file:///Users/user/Documents/projects/agentic_template/agentic_template/frontend/src/lib/FileBrowser.svelte): Workspace file upload and inspection drawer.

---

## 2. Reactive State Architecture (`agent.svelte.ts`)

The application uses Svelte 5 `$state` signals for fine-grained reactivity:

```typescript
// Core reactive state definitions
export class AgentController {
  messages = $state<Message[]>([]);
  isStreaming = $state<boolean>(false);
  activeSessionId = $state<string>('');
  fileUploads = $state<UploadedFile[]>([]);
  traceLink = $state<string>('http://localhost:6006');

  async sendMessage(prompt: string, files: File[]) {
    // 1. Upload files to /api/upload/image or /api/upload/document
    // 2. Dispatch POST /api/chat with streaming enabled
    // 3. Listen to SSE event stream and update messages state reactively
  }
}
```

---

## 3. Component Hierarchy & Flow

```text
           ┌────────────────────────┐
           │       App.svelte       │
           └───────────┬────────────┘
                       │
     ┌─────────────────┼─────────────────┐
     │                 │                 │
┌────┴─────────┐ ┌─────┴────────┐ ┌──────┴─────────┐
│ Sidebar.svelte│ │ChatPanel.svelte│ │TracePanel.svelte│
└──────────────┘ └──────────────┘ └────────────────┘
```

- **Sidebar**: Switches active sessions, displays system prompt overrides, and displays Arize Phoenix status.
- **ChatPanel**: Displays user/assistant message bubbles, rich code blocks, image attachments, and tool call indicators.
- **TracePanel**: Live drawer showing real-time tool execution logs, execution durations, and direct links to Phoenix trace spans.
- **FileBrowser**: Drag-and-drop file upload target supporting PDF, TXT, MD, HTML, and image files.

---

## 4. API Gateway Integration

The frontend communicates with the FastAPI backend (`http://localhost:8000`) over REST and SSE:

- `POST /api/chat`: Sends prompt and multimodal parts; streams token chunks via Server-Sent Events (SSE).
- `POST /api/upload/image`: Validates image formats and uploads to local storage.
- `POST /api/upload/document`: Extracts text content from documents for immediate context inclusion.
- `GET /health`: Polls backend status and Arize Phoenix connection health.

---

## 5. Development & Customization Guide

### Running Frontend Dev Server
```bash
cd frontend
npm install
npm run dev
```
The application will launch on `http://localhost:5173`.

### Extending Components
To add a new UI widget (e.g. custom tool visualization):
1. Add a component under `frontend/src/lib/MyWidget.svelte`.
2. Import and render the component inside `App.svelte` or `ChatPanel.svelte`.
3. Bind reactive properties to `agentController` in `frontend/src/lib/agent.svelte.ts`.
