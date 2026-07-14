import asyncio
import contextvars
import functools
import inspect
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, cast

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from src.agents.pydantic_ai import PydanticAIAgentGenerator
from src.tools.base import ToolFactory
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Initialize Phoenix OpenTelemetry tracing (only if not running under pytest)
if "pytest" not in sys.modules:
    try:
        from phoenix.otel import register

        register(
            project_name="agentic-template",
            auto_instrument=True,
        )
        logger.info("Arize Phoenix OpenTelemetry tracing initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Arize Phoenix tracing: {e}")

app = FastAPI(title="Agentic Template UI API", version="1.0.0")

# Enable CORS for frontend local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# Constants & Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIGS_DIR = WORKSPACE_ROOT / "configs"
SESSIONS_DIR = WORKSPACE_ROOT / "data" / "sessions"
MAX_PREVIEW_LENGTH = 60

# Ensure sessions directory exists
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# ContextVars to track session ID and running loop across the call stack
current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)
current_loop: contextvars.ContextVar[asyncio.AbstractEventLoop | None] = contextvars.ContextVar(
    "current_loop", default=None
)

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_session_id(session_id: str) -> None:
    if not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")


# Active execution state
active_tasks: dict[str, asyncio.Task[None]] = {}
active_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}


# Tools Registry definition
def get_weather(location: str) -> str:
    """Gets the current weather for a location."""
    logger.info(f"[Tool: get_weather] Executing for location: {location}")
    return f"The weather in {location} is sunny and 24°C in {location}."


def dummy_tool(topic: str) -> str:
    """A dummy tool to test tool calling capability."""
    logger.info(f"[Tool: dummy_tool] Executing for topic: {topic}")
    return f"Information about {topic} resolved successfully."


TOOLS_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_weather": get_weather,
    "dummy_tool": dummy_tool,
}


def make_stream_tool(tool_func: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps a tool function to broadcast its execution events to the active SSE stream."""
    tool_name = getattr(tool_func, "__name__", "unknown_tool")

    if inspect.iscoroutinefunction(tool_func):

        @functools.wraps(tool_func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            sess_id = current_session_id.get()
            if sess_id and sess_id in active_streams:
                await active_streams[sess_id].put(
                    {
                        "event": "tool_start",
                        "tool": tool_name,
                        "inputs": {"args": args, "kwargs": kwargs},
                    }
                )

            try:
                res = await tool_func(*args, **kwargs)
                if sess_id and sess_id in active_streams:
                    await active_streams[sess_id].put(
                        {
                            "event": "tool_complete",
                            "tool": tool_name,
                            "output": str(res),
                        }
                    )
                return res
            except Exception as e:
                if sess_id and sess_id in active_streams:
                    await active_streams[sess_id].put(
                        {
                            "event": "tool_error",
                            "tool": tool_name,
                            "error": str(e),
                        }
                    )
                raise

        return async_wrapped
    else:

        @functools.wraps(tool_func)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            sess_id = current_session_id.get()
            loop = current_loop.get()

            if sess_id and sess_id in active_streams and loop:
                loop.call_soon_threadsafe(
                    active_streams[sess_id].put_nowait,
                    {
                        "event": "tool_start",
                        "tool": tool_name,
                        "inputs": {"args": args, "kwargs": kwargs},
                    },
                )

            try:
                res = tool_func(*args, **kwargs)
                if sess_id and sess_id in active_streams and loop:
                    loop.call_soon_threadsafe(
                        active_streams[sess_id].put_nowait,
                        {
                            "event": "tool_complete",
                            "tool": tool_name,
                            "output": str(res),
                        },
                    )
                return res
            except Exception as e:
                if sess_id and sess_id in active_streams and loop:
                    loop.call_soon_threadsafe(
                        active_streams[sess_id].put_nowait,
                        {
                            "event": "tool_error",
                            "tool": tool_name,
                            "error": str(e),
                        },
                    )
                raise

        return sync_wrapped


# Helper to wrap registry tools
STREAM_TOOLS_REGISTRY = {name: make_stream_tool(func) for name, func in TOOLS_REGISTRY.items()}


# Models
class ChatRequest(BaseModel):
    session_id: str | None = None
    config_path: str = "configs/agent_config.yaml"
    query: str
    system_variables: dict[str, Any] = {"role": "Senior Assistant"}

    @field_validator("session_id")
    @classmethod
    def validate_session_id_field(cls, v: str | None) -> str | None:
        if v is not None and not SESSION_ID_PATTERN.match(v):
            raise ValueError(
                "session_id must only contain alphanumeric characters, underscores, and hyphens"
            )
        return v

    @field_validator("config_path")
    @classmethod
    def validate_config_path_field(cls, v: str) -> str:
        path = Path(v)
        if not path.is_absolute():
            resolved = (WORKSPACE_ROOT / path).resolve()
        else:
            resolved = path.resolve()

        configs_dir_resolved = CONFIGS_DIR.resolve()
        if not resolved.is_relative_to(configs_dir_resolved):
            raise ValueError("config_path must be located under the configs directory")
        if not resolved.exists():
            raise ValueError(f"config file does not exist: {v}")
        if resolved.suffix.lower() not in (".yaml", ".yml"):
            raise ValueError("config file must be a YAML file (.yaml or .yml)")
        return v


# Session helper functions
def get_session_file(session_id: str) -> Path:
    if not SESSION_ID_PATTERN.match(session_id):
        raise ValueError("Invalid session ID format")
    resolved_path = (SESSIONS_DIR / f"{session_id}.json").resolve()
    if not resolved_path.is_relative_to(SESSIONS_DIR.resolve()):
        raise ValueError("Invalid session ID path traversal detected")
    return resolved_path


def load_session_history(session_id: str) -> list[dict[str, Any]]:
    try:
        file_path = get_session_file(session_id)
    except ValueError as e:
        logger.error(f"Invalid session ID in load_session_history: {e}")
        return []
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read session file {file_path}: {e}")
        return []


def save_session_history(session_id: str, history: list[dict[str, Any]]) -> None:
    try:
        file_path = get_session_file(session_id)
    except ValueError as e:
        logger.error(f"Invalid session ID in save_session_history: {e}")
        return
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save session file {file_path}: {e}")


# Endpoints
@app.get("/api/configs")
def get_configs():
    """Lists all available YAML configurations in the configs folder."""
    configs = []
    if CONFIGS_DIR.exists():
        for file in CONFIGS_DIR.glob("*.yaml"):
            configs.append(str(file.relative_to(WORKSPACE_ROOT)))
        for file in CONFIGS_DIR.glob("*.yml"):
            configs.append(str(file.relative_to(WORKSPACE_ROOT)))
    return {"configs": sorted(configs)}


@app.get("/api/sessions")
def get_sessions():
    """Lists session histories."""
    sessions = []
    for file in SESSIONS_DIR.glob("*.json"):
        session_id = file.stem
        history = load_session_history(session_id)
        last_message = ""
        if history:
            last_message = history[-1].get("content", "")
        sessions.append(
            {
                "session_id": session_id,
                "last_message": last_message[:MAX_PREVIEW_LENGTH] + "..."
                if len(last_message) > MAX_PREVIEW_LENGTH
                else last_message,
                "updated_at": file.stat().st_mtime,
            }
        )
    # Sort by updated_at descending
    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    """Retrieves full conversation history for a specific session."""
    validate_session_id(session_id)
    history = load_session_history(session_id)
    return {"session_id": session_id, "history": history}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    """Deletes a session history file and cleans up active execution/stream if any."""
    validate_session_id(session_id)

    # 1. Cancel and remove active task/stream if running
    if session_id in active_tasks:
        active_tasks[session_id].cancel()
        active_tasks.pop(session_id, None)

    active_streams.pop(session_id, None)

    # 2. Delete the session history file
    try:
        file_path = get_session_file(session_id)
        if file_path.exists():
            file_path.unlink()
            return {"session_id": session_id, "status": "deleted"}
        else:
            raise HTTPException(status_code=404, detail="Session history not found")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete session file: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/files")
def get_files():
    """Lists files in the data/ folder for the File Explorer panel."""
    data_dir = WORKSPACE_ROOT / "data"
    files = []
    if data_dir.exists():
        for file in data_dir.rglob("*"):
            # Exclude directories and sessions folder
            if file.is_file() and not file.is_relative_to(SESSIONS_DIR):
                files.append(
                    {
                        "name": file.name,
                        "path": str(file.relative_to(WORKSPACE_ROOT)),
                        "size": file.stat().st_size,
                    }
                )
    return {"files": files}


@app.post("/api/agent/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Triggers the agent execution in a background task."""
    session_id = request.session_id or str(uuid.uuid4())

    # Cancel any active running task for this session first
    if session_id in active_tasks:
        active_tasks[session_id].cancel()
        try:
            await active_tasks[session_id]
        except asyncio.CancelledError:
            pass

    # Set up message queue and active streaming
    active_streams[session_id] = asyncio.Queue()

    # Launch background task
    task = asyncio.create_task(
        run_agent_in_background(
            session_id=session_id,
            config_path=request.config_path,
            query=request.query,
            system_variables=request.system_variables,
        )
    )
    active_tasks[session_id] = task

    return {"session_id": session_id, "status": "processing"}


async def run_agent_in_background(
    session_id: str,
    config_path: str,
    query: str,
    system_variables: dict[str, Any],
):
    """Runs agent execution, saves logs, and pumps events into the active stream queue."""
    token_context = current_session_id.set(session_id)
    loop_context = current_loop.set(asyncio.get_running_loop())
    try:
        # Load existing history
        history = load_session_history(session_id)
        history.append({"role": "user", "content": query})
        save_session_history(session_id, history)

        # Initialize the generator and agent
        generator = PydanticAIAgentGenerator(prompt_base_dir="src/prompts")

        # Load and wrap dynamic tools using ToolFactory
        tools_config_path = str(WORKSPACE_ROOT / "configs" / "tools_config.yaml")
        dynamic_tools = ToolFactory.load_from_yaml(tools_config_path)
        wrapped_dynamic_tools = {
            name: make_stream_tool(func) for name, func in dynamic_tools.items()
        }

        # Merge them into a copy of STREAM_TOOLS_REGISTRY
        merged_registry = {**STREAM_TOOLS_REGISTRY, **wrapped_dynamic_tools}

        agent = generator.create_agent(
            config_path,
            system_variables=system_variables,
            tools_registry=merged_registry,
        )

        chunks = []
        async for chunk in agent.call_stream(inputs=cast(Any, {"query": query})):
            chunks.append(chunk)
            if session_id in active_streams:
                await active_streams[session_id].put({"event": "token", "text": chunk})

        final_text = "".join(chunks)
        history.append({"role": "assistant", "content": final_text})
        save_session_history(session_id, history)

        if session_id in active_streams:
            await active_streams[session_id].put({"event": "done", "text": final_text})

    except asyncio.CancelledError:
        logger.info(f"Agent execution for session {session_id} was cancelled.")
        if session_id in active_streams:
            await active_streams[session_id].put(
                {"event": "cancelled", "text": "Execution cancelled by user."}
            )
    except Exception as e:
        logger.error(f"Error running agent: {e}")
        if session_id in active_streams:
            await active_streams[session_id].put({"event": "error", "text": str(e)})
    finally:
        current_session_id.reset(token_context)
        current_loop.reset(loop_context)


@app.get("/api/agent/stream/{session_id}")
async def stream_agent(session_id: str):
    """SSE endpoint returning real-time agent generation and tool-calling events."""
    validate_session_id(session_id)
    if session_id not in active_streams:
        # If no active queue, return immediate done
        async def empty_stream():
            yield 'event: error\ndata: {"error": "No active stream session found"}\n\n'

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    queue = active_streams[session_id]
    task = active_tasks.get(session_id)

    async def event_generator():
        while True:
            try:
                # Add timeout to avoid waiting forever if task died silently
                event_data = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield f"event: {event_data['event']}\ndata: {json.dumps(event_data)}\n\n"

                # Terminal events close the SSE stream
                if event_data["event"] in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                yield 'event: error\ndata: {"error": "Stream execution timeout"}\n\n'
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                break

        # Clean up queue when stream closes, only if they haven't been overwritten
        if active_streams.get(session_id) is queue:
            active_streams.pop(session_id, None)
        if active_tasks.get(session_id) is task:
            active_tasks.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )


@app.post("/api/agent/stop/{session_id}")
def stop_agent(session_id: str):
    """Cancels the active running task for a session."""
    validate_session_id(session_id)
    if session_id in active_tasks:
        task = active_tasks[session_id]
        task.cancel()
        return {"status": "cancelled"}
    return {"status": "idle", "message": "No running agent execution found for session."}
