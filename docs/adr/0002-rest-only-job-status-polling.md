# REST-Only Job Status Polling for Ingestion Service

We evaluated REST polling (`GET /jobs/{id}`), Server-Sent Events (SSE), and WebSockets for tracking document ingestion jobs. We decided to implement canonical REST-only endpoints returning fine-grained lifecycle status (`JobStatus`), processing stage (`JobStage`), and quantitative progress counters (`JobProgress`). This avoids connection state management, firewall/proxy disconnects, and complex client reconnect logic while providing full visibility into ingestion pipelines.

## Room for Improvement & Future Evolution

If real-time UI streaming or high-frequency progress animations become necessary, a Server-Sent Events (`GET /jobs/{id}/events`) or WebSocket stream can be added on top of the canonical REST status models without modifying existing polling contracts.
