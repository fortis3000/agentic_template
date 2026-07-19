import asyncio
import base64
import contextvars
import functools
import inspect
import io
import json
import re
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

import yaml
from PIL import Image
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from pydantic.types import Base64Bytes

from src.agents.base import AgentInputPart, ImagePart, TextPart
from src.agents.config import AgentYamlConfig, FileConstraints, ImageConstraints
from src.agents.pydantic_ai import PydanticAIAgentGenerator
from src.tools.base import ToolFactory
from src.tools.text_extractor import extract_text
from src.utils.logger import get_logger

logger = get_logger(__name__)


ingestion_queue: asyncio.Queue = asyncio.Queue()
ingestion_worker_tasks: dict[str, asyncio.Task | None] = {"worker": None}


async def ingestion_worker() -> None:
    """Background worker processing document ingestion tasks from the queue."""
    logger.info("Starting background ingestion worker.")
    while True:
        try:
            task_data = await ingestion_queue.get()
        except asyncio.CancelledError:
            logger.info("Ingestion worker cancelled.")
            break

        try:
            filepath = task_data["filepath"]
            file_bytes = task_data["file_bytes"]
            mime_type = task_data["mime_type"]
            config = task_data["config"]
            vectordb = task_data["vectordb"]
            embed_client = task_data["embed_client"]

            logger.info(f"Processing background ingestion for: {filepath}")
            from src.utils.ingestion_helper import ingest_document  # noqa: PLC0415

            await ingest_document(
                filepath=filepath,
                file_bytes=file_bytes,
                mime_type=mime_type,
                config=config,
                vectordb=vectordb,
                embed_client=embed_client,
            )
            logger.info(f"Successfully processed background ingestion for: {filepath}")
        except Exception as e:
            logger.error(f"Error in background ingestion worker: {e}", exc_info=True)
        finally:
            ingestion_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Phoenix OpenTelemetry tracing (only if not running under pytest)
    if "pytest" not in sys.modules:
        try:
            from phoenix.otel import register  # noqa: PLC0415

            register(
                project_name="agentic-template",
                auto_instrument=True,
            )
            logger.info("Arize Phoenix OpenTelemetry tracing initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Arize Phoenix tracing: {e}")

    # Start background ingestion worker
    ingestion_worker_tasks["worker"] = asyncio.create_task(ingestion_worker())

    yield

    # Cancel background ingestion worker on shutdown
    w_task = ingestion_worker_tasks["worker"]
    if w_task:
        w_task.cancel()
        try:
            await w_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Agentic Template UI API", version="1.0.0", lifespan=lifespan)

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
UPLOADS_DIR = WORKSPACE_ROOT / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

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
class RequestImagePart(BaseModel):
    data: Base64Bytes | None = None
    path: Path | None = None
    mime_type: str | None = None


class RequestFilePart(BaseModel):
    data: Base64Bytes | None = None
    path: Path | None = None
    mime_type: str
    filename: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    config_path: str = "configs/agent_config.yaml"
    query: str
    system_variables: dict[str, Any] = {"role": "Senior Assistant"}
    images: list[RequestImagePart] | None = None
    files: list[RequestFilePart] | None = None

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


def process_and_validate_image(
    image_bytes: bytes,
    mime_type: str | None,
    constraints: ImageConstraints,
) -> tuple[bytes, str, bool]:
    """Validates the image MIME type and resolution constraints, and resizes if it exceeds max limits.

    Supports frame-by-frame resizing for animated GIFs.

    Returns:
        A tuple of (processed_image_bytes, resolved_mime_type, resized_any_flag).
    """
    min_w = constraints.min_image_width
    min_h = constraints.min_image_height
    max_w = constraints.max_image_width
    max_h = constraints.max_image_height
    acceptable_types = constraints.acceptable_data_types

    resolved_mime = mime_type or "image/png"
    if resolved_mime not in acceptable_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format: {resolved_mime}. Allowed formats: {', '.join(acceptable_types)}",
        )

    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image content: {str(e)}")

    if width < min_w or height < min_h:
        raise HTTPException(
            status_code=400,
            detail=f"Image resolution {width}x{height} is below the minimum allowed limit of {min_w}x{min_h}.",
        )

    resized_any = False
    if width > max_w or height > max_h:
        ratio = min(max_w / width, max_h / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)

        if img.format == "GIF" and getattr(img, "is_animated", False):
            frames = []
            n_frames = getattr(img, "n_frames", 1)
            for frame_idx in range(n_frames):
                img.seek(frame_idx)
                frame = (
                    img.copy()
                    .convert("RGBA")
                    .resize((new_width, new_height), Image.Resampling.LANCZOS)
                )
                frames.append(frame)
            out_buf = io.BytesIO()
            frames[0].save(
                out_buf,
                save_all=True,
                append_images=frames[1:],
                format="GIF",
                loop=img.info.get("loop", 0),
                duration=img.info.get("duration", 20),
            )
            image_bytes = out_buf.getvalue()
        else:
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            out_buf = io.BytesIO()
            fmt = resolved_mime.split("/")[-1].upper()
            if fmt == "JPG":
                fmt = "JPEG"
            img.save(out_buf, format=fmt)
            image_bytes = out_buf.getvalue()
        logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        resized_any = True

    return image_bytes, resolved_mime, resized_any


def process_and_validate_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    constraints: FileConstraints,
) -> tuple[str, str, str]:
    """Validates file constraints and extracts text content.

    Returns:
        A tuple of (extracted_text, filename, mime_type).
    """
    acceptable_types = constraints.acceptable_file_types
    max_size = constraints.max_file_size_bytes

    if mime_type not in acceptable_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime_type}. Allowed types: {', '.join(acceptable_types)}",
        )

    if len(file_bytes) > max_size:
        max_mb = max_size / (1024 * 1024)
        file_mb = len(file_bytes) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File '{filename}' size ({file_mb:.1f} MB) exceeds the maximum allowed size of {max_mb:.0f} MB.",
        )

    try:
        extracted_text = extract_text(file_bytes, mime_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to extract text from '{filename}': {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to extract text from '{filename}': {str(e)}",
        )

    return extracted_text, filename, mime_type


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


@app.get("/api/configs/detail")
def get_config_detail(config_path: str):
    """Retrieves parsed config parameters for the given config file."""
    try:
        validated_path = ChatRequest.validate_config_path_field(config_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resolved_path = (WORKSPACE_ROOT / validated_path).resolve()
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        validated_config = AgentYamlConfig.model_validate(config_data)

        return {
            "acceptable_data_types": validated_config.agent.acceptable_data_types,
            "max_image_width": validated_config.agent.max_image_width,
            "max_image_height": validated_config.agent.max_image_height,
            "min_image_width": validated_config.agent.min_image_width,
            "min_image_height": validated_config.agent.min_image_height,
            "acceptable_file_types": validated_config.agent.acceptable_file_types,
            "max_file_size_bytes": validated_config.agent.max_file_size_bytes,
            "max_files_per_message": validated_config.agent.max_files_per_message,
        }
    except Exception as e:
        logger.error(f"Failed to load config details for {config_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")


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

            # 3. Delete uploaded files for the session
            session_upload_dir = UPLOADS_DIR / session_id
            if session_upload_dir.exists():
                shutil.rmtree(session_upload_dir, ignore_errors=True)

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


@app.get("/api/files/uploads/{session_id}")
def get_uploaded_files(session_id: str):
    """Lists uploaded files for a specific session."""
    validate_session_id(session_id)
    session_upload_dir = UPLOADS_DIR / session_id
    if not session_upload_dir.exists():
        return {"files": []}

    files = []
    for file in session_upload_dir.iterdir():
        if file.is_file():
            files.append(
                {
                    "filename": file.name,
                    "size": file.stat().st_size,
                    "uploaded_at": file.stat().st_mtime,
                }
            )
    return {"files": files}


def _process_file_attachments(
    files: list[RequestFilePart],
    file_constraints: FileConstraints,
    session_upload_dir: Path,
) -> list[dict[str, Any]]:
    """Validates, extracts text from, and persists uploaded file attachments."""
    session_upload_dir.mkdir(parents=True, exist_ok=True)
    file_contexts: list[dict[str, Any]] = []

    for file_part in files:
        if not file_part.data and not file_part.path:
            raise HTTPException(
                status_code=400, detail="FilePart must have either data or path defined."
            )

        if file_part.data:
            file_bytes = file_part.data
        else:
            if file_part.path is None:
                raise HTTPException(status_code=400, detail="File path must not be None.")
            abs_path = Path(file_part.path).resolve()
            if not abs_path.exists():
                raise HTTPException(
                    status_code=400, detail=f"File path does not exist: {file_part.path}"
                )
            file_bytes = abs_path.read_bytes()

        extracted_text, fname, fmime = process_and_validate_file(
            file_bytes=file_bytes,
            filename=file_part.filename,
            mime_type=file_part.mime_type,
            constraints=file_constraints,
        )

        # Save raw file to uploads directory
        save_path = session_upload_dir / file_part.filename
        save_path.write_bytes(file_bytes)

        file_contexts.append(
            {
                "filename": fname,
                "mime_type": fmime,
                "size": len(file_bytes),
                "path": str(save_path),
                "extracted_text": extracted_text,
            }
        )

    return file_contexts


@app.post("/api/agent/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):  # noqa: PLR0912, PLR0915
    """Triggers the agent execution in a background task."""
    session_id = request.session_id or str(uuid.uuid4())

    # 1. Load active config once
    resolved_path = (WORKSPACE_ROOT / request.config_path).resolve()
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        validated_config = AgentYamlConfig.model_validate(config_data)
        agent_cfg = validated_config.agent
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load agent config: {str(e)}")

    # 2. Validate and process attached images
    processed_images = []
    resized_any = False
    if request.images:
        constraints = agent_cfg.image_constraints
        for img_part in request.images:
            if not img_part.data and not img_part.path:
                raise HTTPException(
                    status_code=400, detail="ImagePart must have either data or path defined."
                )

            if img_part.data:
                img_bytes = img_part.data
            else:
                if img_part.path is None:
                    raise HTTPException(status_code=400, detail="Image path must not be None.")
                abs_path = Path(img_part.path).resolve()
                if not abs_path.exists():
                    raise HTTPException(
                        status_code=400, detail=f"Image path does not exist: {img_part.path}"
                    )
                img_bytes = abs_path.read_bytes()

            processed_bytes, resolved_mime, was_resized = process_and_validate_image(
                image_bytes=img_bytes,
                mime_type=img_part.mime_type,
                constraints=constraints,
            )
            if was_resized:
                resized_any = True
            processed_images.append(ImagePart(data=processed_bytes, mime_type=resolved_mime))

    # 3. Validate and process attached files
    file_contexts: list[dict[str, Any]] = []
    if request.files:
        file_constraints = agent_cfg.file_constraints
        if len(request.files) > file_constraints.max_files_per_message:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Too many files. Maximum {file_constraints.max_files_per_message}"
                    " files per message."
                ),
            )

        session_upload_dir = UPLOADS_DIR / session_id
        file_contexts = _process_file_attachments(
            files=request.files,
            file_constraints=file_constraints,
            session_upload_dir=session_upload_dir,
        )

        # 4. Enqueue files for background ingestion if embedding_model is configured
        if agent_cfg.embedding_model and file_contexts:
            # Load tools_config.yaml to get vectordb_search settings
            tools_cfg = {}
            tools_config_path = WORKSPACE_ROOT / "configs" / "tools_config.yaml"
            if tools_config_path.exists():
                try:
                    with open(tools_config_path, "r", encoding="utf-8") as f:
                        tools_data = yaml.safe_load(f) or {}
                        tools_cfg = (
                            tools_data.get("tools", {}).get("search_vectordb", {}).get("config", {})
                        )
                except Exception as e:
                    logger.error(f"Failed to load tools config for ingestion: {e}")

            collection_name = tools_cfg.get("collection_name", "default_collection")
            vectordb_cfg = tools_cfg.get("vectordb", {"type": "qdrant", "location": ":memory:"})
            embedding_cfg = tools_cfg.get("embedding_model")

            from src.agents.config import EmbeddingModelConfigSchema  # noqa: PLC0415
            from src.agents.embeddings import EmbeddingModelFactory  # noqa: PLC0415
            from src.tools.vectordb_base import VectorDBFactory  # noqa: PLC0415

            target_coll = collection_name

            class SimpleIngestConfig:
                collection_name = target_coll
                chunking_strategy = "fixed"
                chunk_size = 500
                chunk_overlap = 50
                semantic_threshold = 0.5

            if embedding_cfg:
                emb_schema = EmbeddingModelConfigSchema.model_validate(embedding_cfg)
                embed_client = EmbeddingModelFactory.create(emb_schema)
                dimensions = emb_schema.dimensions or 768
            else:
                embed_client = EmbeddingModelFactory.create(agent_cfg.embedding_model)
                dimensions = agent_cfg.embedding_model.dimensions or 768

            db_type = vectordb_cfg.get("type", "qdrant")
            db_params = {k: v for k, v in vectordb_cfg.items() if k != "type"}
            vectordb = VectorDBFactory.create(db_type, **db_params)

            await vectordb.create_collection(
                SimpleIngestConfig.collection_name,
                dimensions,
            )

            for ctx in file_contexts:
                f_path = Path(ctx["path"])
                if f_path.exists():
                    f_bytes = f_path.read_bytes()
                    await ingestion_queue.put(
                        {
                            "filepath": ctx["path"],
                            "file_bytes": f_bytes,
                            "mime_type": ctx["mime_type"],
                            "config": SimpleIngestConfig,
                            "vectordb": vectordb,
                            "embed_client": embed_client,
                        }
                    )

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
            config=validated_config,
            query=request.query,
            system_variables=request.system_variables,
            images=processed_images,
            resized_any=resized_any,
            file_contexts=file_contexts,
        )
    )
    active_tasks[session_id] = task

    return {"session_id": session_id, "status": "processing"}


async def run_agent_in_background(  # noqa: PLR0912, PLR0915
    session_id: str,
    config: str | AgentYamlConfig | None = None,
    query: str = "",
    system_variables: dict[str, Any] | None = None,
    images: list[ImagePart] | None = None,
    resized_any: bool = False,
    file_contexts: list[dict[str, Any]] | None = None,
    config_path: str | None = None,
):
    """Runs agent execution, saves logs, and pumps events into the active stream queue."""
    token_context = current_session_id.set(session_id)
    loop_context = current_loop.set(asyncio.get_running_loop())
    try:
        target_config = config or config_path
        if not target_config:
            raise ValueError("Must provide either config or config_path")

        if isinstance(target_config, str):
            resolved_path = (WORKSPACE_ROOT / target_config).resolve()
            with open(resolved_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            validated_config = AgentYamlConfig.model_validate(config_data)
        else:
            validated_config = target_config

        # Load existing history
        history = load_session_history(session_id)
        user_message: dict[str, Any] = {"role": "user", "content": query}
        if images:
            serialized_images = []
            for img in images:
                img_bytes = None
                if img.data is not None:
                    img_bytes = img.data
                elif img.path is not None:
                    try:
                        abs_path = Path(img.path).resolve()
                        if abs_path.exists():
                            img_bytes = abs_path.read_bytes()
                    except Exception as e:
                        logger.error(f"Failed to read image path {img.path}: {e}")

                if img_bytes is not None:
                    mime = img.mime_type or "image/png"
                    b64_str = base64.b64encode(img_bytes).decode("utf-8")
                    serialized_images.append(
                        {"data": f"data:{mime};base64,{b64_str}", "mime_type": mime}
                    )
            if serialized_images:
                user_message["images"] = serialized_images

        if file_contexts:
            user_message["files"] = [
                {
                    "filename": fc["filename"],
                    "mime_type": fc["mime_type"],
                    "size": fc["size"],
                    "path": fc["path"],
                }
                for fc in file_contexts
            ]

        history.append(user_message)
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
            validated_config,
            system_variables=system_variables,
            tools_registry=merged_registry,
        )

        # Send info event if images were auto-resized on backend
        if resized_any and session_id in active_streams:
            await active_streams[session_id].put(
                {
                    "event": "info",
                    "text": "Some attached images exceeded the resolution limit and were resized.",
                }
            )

        # Build multimodal inputs list
        prompt_mgr = getattr(agent, "prompt_manager", None)
        user_prompt_src = getattr(agent, "default_user_prompt_source", None)
        user_prompt_fmt = getattr(agent, "default_user_prompt_format", "f-string")

        if prompt_mgr and user_prompt_src:
            user_prompt = prompt_mgr.load_prompt(
                user_prompt_src,
                variables={"query": query},
                format_style=user_prompt_fmt,
            )
        else:
            user_prompt = query

        # Prepend file content blocks to the user prompt
        if file_contexts:
            file_blocks = []
            for fc in file_contexts:
                file_blocks.append(f"[FILE: {fc['filename']}]\n{fc['extracted_text']}\n[/FILE]")
            file_prefix = "\n\n".join(file_blocks) + "\n\n"
            if prompt_mgr and user_prompt_src:
                user_prompt = file_prefix + user_prompt
            else:
                user_prompt = file_prefix + user_prompt

        if file_contexts and session_id in active_streams:
            count = len(file_contexts)
            await active_streams[session_id].put(
                {
                    "event": "info",
                    "text": f"{count} file(s) uploaded and processed.",
                }
            )

        inputs: list[AgentInputPart] = [TextPart(text=user_prompt)]
        if images:
            inputs.extend(images)

        chunks = []
        async for chunk in agent.call_stream(inputs=inputs):
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
            yield 'event: error\ndata: {"error": "No active stream session found", "text": "No active stream session found"}\n\n'

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    queue = active_streams[session_id]
    task = active_tasks.get(session_id)

    async def event_generator():
        while True:
            try:
                # Add timeout to avoid waiting forever if task died silently
                event_data = await asyncio.wait_for(queue.get(), timeout=300.0)
                yield f"event: {event_data['event']}\ndata: {json.dumps(event_data)}\n\n"

                # Terminal events close the SSE stream
                if event_data["event"] in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                yield 'event: error\ndata: {"error": "Stream execution timeout", "text": "Stream execution timeout"}\n\n'
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e), 'text': str(e)})}\n\n"
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
