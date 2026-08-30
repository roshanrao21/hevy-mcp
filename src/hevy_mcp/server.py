import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .config import get_settings
from .context import request_hevy_api_key
from .errors import AuthenticationError, AuthorizationError, HevyMcpError, UpstreamError
from .hevy_client import HevyClient
from .models import RoutineInput, ToolResult, WorkoutInput
from .security import SecurityMiddleware, require_confirmation

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Hevy MCP",
    instructions=(
        "Use read tools freely. Mutating tools require an exact CONFIRM token and may be "
        "disabled by server policy. Never invent exercise template IDs. Search templates first. "
        "Do not provide medical diagnoses or claim that workout data proves an injury or illness."
    ),
    json_response=True,
)


def _api_key() -> str:
    key = request_hevy_api_key.get() or settings.hevy_api_key
    if not key:
        raise AuthenticationError("No Hevy API key is available for this request.")
    return key


@asynccontextmanager
async def client() -> AsyncIterator[HevyClient]:
    instance = HevyClient(
        base_url=settings.hevy_base_url,
        api_key=_api_key(),
        timeout_seconds=settings.request_timeout_seconds,
    )
    try:
        yield instance
    finally:
        await instance.close()


def ok(data: Any) -> dict[str, Any]:
    return ToolResult(ok=True, data=data).model_dump(exclude_none=True)


def fail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AuthenticationError):
        code = "AUTHENTICATION_FAILED"
        retryable = False
    elif isinstance(exc, AuthorizationError):
        code = "WRITE_DISABLED"
        retryable = False
    elif isinstance(exc, UpstreamError):
        code = "HEVY_API_ERROR"
        retryable = exc.retryable
    elif isinstance(exc, ValueError):
        code = "INVALID_INPUT"
        retryable = False
    else:
        logger.exception("Unhandled tool error")
        code = "INTERNAL_ERROR"
        retryable = False

    return ToolResult(
        ok=False,
        error={"code": code, "message": str(exc), "retryable": retryable},
    ).model_dump(exclude_none=True)


def guard_write(confirmation: str) -> None:
    if not settings.allow_writes:
        raise AuthorizationError(
            "Mutating tools are disabled. Set ALLOW_WRITES=true only after reviewing the risks."
        )
    require_confirmation(confirmation)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def list_workouts(page: int = 1, page_size: int = 5) -> dict[str, Any]:
    """List workouts. page must be >=1; page_size is capped by server policy and Hevy."""
    try:
        if page < 1:
            raise ValueError("page must be at least 1")
        page_size = min(max(page_size, 1), settings.max_page_size, 10)
        async with client() as hevy:
            return ok(await hevy.get("/v1/workouts", params={"page": page, "pageSize": page_size}))
    except Exception as exc:
        return fail(exc)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def get_workout(workout_id: str) -> dict[str, Any]:
    """Get one workout by exact Hevy workout ID."""
    try:
        if not workout_id or len(workout_id) > 128:
            raise ValueError("A valid workout_id is required.")
        async with client() as hevy:
            return ok(await hevy.get(f"/v1/workouts/{workout_id}"))
    except Exception as exc:
        return fail(exc)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def list_routines(page: int = 1, page_size: int = 5) -> dict[str, Any]:
    """List routines. Use get_routine before proposing an update."""
    try:
        if page < 1:
            raise ValueError("page must be at least 1")
        page_size = min(max(page_size, 1), settings.max_page_size, 10)
        async with client() as hevy:
            return ok(await hevy.get("/v1/routines", params={"page": page, "pageSize": page_size}))
    except Exception as exc:
        return fail(exc)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def get_routine(routine_id: str) -> dict[str, Any]:
    """Get one routine by exact Hevy routine ID."""
    try:
        if not routine_id or len(routine_id) > 128:
            raise ValueError("A valid routine_id is required.")
        async with client() as hevy:
            return ok(await hevy.get(f"/v1/routines/{routine_id}"))
    except Exception as exc:
        return fail(exc)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def search_exercise_templates(
    query: str,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Search account exercise templates by title. Call this before any routine/workout mutation."""
    try:
        normalized = " ".join(query.lower().split())
        if len(normalized) < 2:
            raise ValueError("query must contain at least two characters")
        page_size = min(max(page_size, 1), 100)
        async with client() as hevy:
            response = await hevy.get(
                "/v1/exercise_templates",
                params={"page": page, "pageSize": page_size},
            )
        matches = [
            item
            for item in response.get("exercise_templates", [])
            if normalized in str(item.get("title", "")).lower()
        ]
        return ok({"query": query, "matches": matches, "source_page": page})
    except Exception as exc:
        return fail(exc)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def get_exercise_history(
    exercise_template_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Get performed-set history for one exercise template. Dates must be YYYY-MM-DD when supplied."""
    try:
        if not exercise_template_id or len(exercise_template_id) > 128:
            raise ValueError("A valid exercise_template_id is required.")
        params = {k: v for k, v in {"start_date": start_date, "end_date": end_date}.items() if v}
        async with client() as hevy:
            return ok(
                await hevy.get(
                    f"/v1/exercise_history/{exercise_template_id}",
                    params=params or None,
                )
            )
    except Exception as exc:
        return fail(exc)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def create_routine(routine: RoutineInput, confirmation: str) -> dict[str, Any]:
    """Create a routine. Disabled by default and requires confirmation='CONFIRM'. May duplicate on retry."""
    try:
        guard_write(confirmation)
        payload = {"routine": routine.model_dump(exclude_none=True)}
        async with client() as hevy:
            return ok(await hevy.post("/v1/routines", json=payload))
    except Exception as exc:
        return fail(exc)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def update_routine(
    routine_id: str,
    routine: RoutineInput,
    confirmation: str,
) -> dict[str, Any]:
    """Replace an existing routine. Fetch it first; disabled by default; requires confirmation='CONFIRM'."""
    try:
        guard_write(confirmation)
        if not routine_id or len(routine_id) > 128:
            raise ValueError("A valid routine_id is required.")
        payload = {"routine": routine.model_dump(exclude_none=True)}
        async with client() as hevy:
            return ok(await hevy.put(f"/v1/routines/{routine_id}", json=payload))
    except Exception as exc:
        return fail(exc)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def create_workout(workout: WorkoutInput, confirmation: str) -> dict[str, Any]:
    """Create a completed workout. Disabled by default and requires confirmation='CONFIRM'."""
    try:
        guard_write(confirmation)
        payload = {
            "workout": workout.model_dump(
                exclude_none=True,
                mode="json",
            )
        }
        async with client() as hevy:
            return ok(await hevy.post("/v1/workouts", json=payload))
    except Exception as exc:
        return fail(exc)


@mcp.resource("hevy://safety")
def safety_resource() -> str:
    return (
        "Hevy MCP safety policy:\n"
        "- Read operations are preferred.\n"
        "- Writes are disabled by default.\n"
        "- Never invent exercise-template, workout, or routine IDs.\n"
        "- Fetch an existing routine before replacing it.\n"
        "- Create operations can duplicate when retried.\n"
        "- Workout data is not medical evidence; seek qualified care for injury or illness."
    )


@mcp.prompt()
def review_routine_change(current_routine_json: str, proposed_routine_json: str) -> str:
    """Prompt for reviewing a routine change before invoking update_routine."""
    return (
        "Compare the current and proposed Hevy routines. Produce a concise change summary, "
        "identify removed exercises/sets, suspicious weight or repetition jumps, missing template "
        "IDs, and any data-loss risk. Do not call a mutation until the user explicitly approves "
        "the exact final payload.\n\nCURRENT:\n"
        f"{current_routine_json}\n\nPROPOSED:\n{proposed_routine_json}"
    )


async def health(_request):
    return JSONResponse({"status": "ok", "service": "hevy-mcp"})


def build_http_app():
    mcp_app = mcp.streamable_http_app()
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.lifespan,
    )
    return SecurityMiddleware(app, settings)


def main() -> None:
    transport = settings.mcp_transport.lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
        return
    if transport != "streamable-http":
        raise SystemExit("MCP_TRANSPORT must be 'stdio' or 'streamable-http'.")

    uvicorn.run(
        build_http_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
