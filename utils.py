"""
Agent and MCP setup for the Learning Path Generator.
Reads API keys and webhook URLs from environment variables.
- Demo mode: Gemini only (USE_DEMO_MODE=true or no webhooks).
- Webhook mode: custom tools POST to your Pipedream URLs (Drive + YouTube).
- MCP mode: optional, for MCP-compatible endpoints.
"""
import os
import re
import urllib.parse
from typing import Optional, Any, Callable

from dotenv import load_dotenv
load_dotenv()
# Also load backend env when present (common in this repo)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "backend", ".env"), override=False)

from langchain_core.messages import HumanMessage
from pydantic_core import ValidationError as PydanticValidationError
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent
from langgraph.graph import START, StateGraph
from langgraph.graph.message import MessagesState
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_google_genai import ChatGoogleGenerativeAI
import asyncio
import httpx

from prompt import user_goal_prompt
from webhook_tools import get_webhook_tools
from google_super_mode import run_google_super_mode

cfg = RunnableConfig(recursion_limit=100)

# Prompt addition for demo mode (no YouTube/Drive/Notion tools)
DEMO_PROMPT_ADDITION = """
You do not have access to YouTube or Google Drive/Notion tools. Generate a day-by-day learning path as structured text only.
Include: day number, topic, and suggested resource types or search terms (e.g. "Search: Python basics tutorial"). Format clearly with headers.
"""

def _build_offline_learning_path(topic: str, days: int = 7) -> str:
    t = (topic or "").strip() or "your topic"
    plan = [
        ("Foundations & Setup", f"Search: {t} beginner tutorial", "Install, run basics, first mini-exercise"),
        ("Core Concepts", f"Search: {t} fundamentals explained", "Key concepts, terminology, and mental models"),
        ("Practice & Exercises", f"Search: {t} practice problems", "Hands-on drills and quick feedback loops"),
        ("Building Blocks", f"Search: {t} projects for beginners", "Small project to combine fundamentals"),
        ("Common Pitfalls", f"Search: {t} mistakes to avoid", "Debugging, troubleshooting, and best practices"),
        ("Intermediate Topics", f"Search: {t} intermediate tutorial", "Go beyond basics with practical patterns"),
        ("Capstone & Next Steps", f"Search: {t} capstone project", "Portfolio project + what to learn next"),
    ]
    plan = plan[: max(1, min(days, len(plan)))]

    out = [f"## 🎯 Offline Learning Path: **{t}**", ""]
    for i, (day_topic, search, focus) in enumerate(plan, start=1):
        out.append(f"### Day {i}: {day_topic}")
        out.append(f"- **Focus**: {focus}")
        out.append(f"- **Resource**: {search}")
        out.append("")
    out.append("Tip: When you’re ready, start the backend to enable richer output (playlist/doc generation).")
    return "\n".join(out).strip()


def _build_structured_learning_path(topic: str, days: int = 7) -> list[dict]:
    """
    Deterministic day-wise plan used when LLM quota is unavailable.
    Returns entries with: day, title, focus, youtube_query.
    """
    t = (topic or "").strip() or "your topic"
    template = [
        {
            "title": "Foundations & Setup",
            "focus": "Environment setup, core concepts, and first mini-project.",
            "youtube_query": f"{t} full course for beginners",
        },
        {
            "title": "Core Building Blocks",
            "focus": "Syntax/structure + the key primitives you’ll use daily.",
            "youtube_query": f"{t} fundamentals explained tutorial",
        },
        {
            "title": "Practice: Problem Solving",
            "focus": "Exercises + patterns to build speed and confidence.",
            "youtube_query": f"{t} practice problems walkthrough",
        },
        {
            "title": "Mini Project (Beginner → Intermediate)",
            "focus": "Build a small end-to-end project and learn debugging workflows.",
            "youtube_query": f"{t} beginner project tutorial",
        },
        {
            "title": "Intermediate Concepts",
            "focus": "Common real-world patterns, best practices, and pitfalls.",
            "youtube_query": f"{t} intermediate tutorial best practices",
        },
        {
            "title": "Real-World Integration",
            "focus": "APIs/files/tools; integrate with external services and data.",
            "youtube_query": f"{t} api integration project tutorial",
        },
        {
            "title": "Capstone + Next Steps",
            "focus": "Portfolio capstone, review, and a roadmap for advanced topics.",
            "youtube_query": f"{t} capstone project build",
        },
    ]
    template = template[: max(1, min(days, len(template)))]
    return [
        {
            "day": i + 1,
            "title": template[i]["title"],
            "focus": template[i]["focus"],
            "youtube_query": template[i]["youtube_query"],
        }
        for i in range(len(template))
    ]


def _extract_first_youtube_video_id(search_response: dict) -> Optional[str]:
    try:
        items = (search_response or {}).get("items") or (search_response or {}).get("data", {}).get("items") or []
        for it in items:
            vid = (it.get("id") or {}).get("videoId") if isinstance(it, dict) else None
            if vid:
                return vid
    except Exception:
        return None
    return None


def _pick_unique_youtube_video_id(search_response: dict, used: set[str]) -> Optional[str]:
    """
    Pick the first videoId from search results that isn't already used.
    """
    try:
        items = (search_response or {}).get("items") or (search_response or {}).get("data", {}).get("items") or []
        for it in items:
            vid = (it.get("id") or {}).get("videoId") if isinstance(it, dict) else None
            if vid and vid not in used:
                return vid
    except Exception:
        return None
    return None


def _desired_days_from_goal(user_goal: str, default_days: int = 7) -> int:
    text = (user_goal or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(?:day|days)\b", text)
    if not m:
        return default_days
    try:
        return max(1, min(int(m.group(1)), 30))
    except Exception:
        return default_days


def _extract_playlist_id(create_playlist_response: dict) -> Optional[str]:
    """
    Normalize playlist-id extraction across response shapes.
    Expected shape (from COMPOSIO_MULTI_EXECUTE_TOOL):
      {"data":{"results":[{"response":{"data":{"id":"..."}}}]}}
    """
    try:
        data = (create_playlist_response or {}).get("data") or {}
        results = data.get("results") or data.get("outputs") or []
        if not results:
            return None
        first = results[0] or {}
        resp = first.get("response") or first.get("output") or {}
        rdata = resp.get("data") or {}
        pid = rdata.get("id")
        if pid:
            return pid
    except Exception:
        return None
    return None


def _extract_drive_file_id(create_file_response: dict) -> Optional[str]:
    """
    Normalize file-id extraction across response shapes.
    Expected shape (from COMPOSIO_MULTI_EXECUTE_TOOL):
      {"data":{"results":[{"response":{"data":{"id":"..."}}}]}}
    """
    try:
        data = (create_file_response or {}).get("data") or {}
        results = data.get("results") or data.get("outputs") or []
        if not results:
            return None
        first = results[0] or {}
        resp = first.get("response") or first.get("output") or {}
        rdata = resp.get("data") or {}
        fid = rdata.get("id")
        if fid:
            return fid
    except Exception:
        return None
    return None


def _extract_multi_response_data(multi_exec_response: dict) -> dict:
    """Return first tool response.data payload from COMPOSIO_MULTI_EXECUTE_TOOL response."""
    try:
        data = (multi_exec_response or {}).get("data") or {}
        results = data.get("results") or []
        if not results:
            return {}
        resp = (results[0] or {}).get("response") or {}
        if resp.get("successful") is True:
            return (resp.get("data") or {})
    except Exception:
        return {}
    return {}


def _extract_notion_parent_id(search_page_response: dict) -> Optional[str]:
    """
    Best-effort extraction of a Notion page id from NOTION_SEARCH_NOTION_PAGE response payload.
    """
    try:
        items = (
            (search_page_response or {}).get("results")
            or (search_page_response or {}).get("data", {}).get("results")
            or []
        )
        if not items:
            return None
        first = items[0] if isinstance(items, list) else None
        if not isinstance(first, dict):
            return None
        return first.get("id")
    except Exception:
        return None


def _extract_notion_page_link(create_page_response: dict) -> Optional[str]:
    """
    Extract Notion page URL from NOTION_CREATE_NOTION_PAGE response payload.
    """
    try:
        url = create_page_response.get("url")
        if url:
            return url
        page_id = create_page_response.get("id")
        if page_id:
            return f"https://www.notion.so/{str(page_id).replace('-', '')}"
    except Exception:
        return None
    return None


def _get_google_api_key() -> str:
    """Get Google API key from env. Returns placeholder when missing."""
    return (os.getenv("GOOGLE_API_KEY") or "YOUR_GOOGLE_API_KEY_HERE").strip()


def _get_google_model_name() -> str:
    """
    Gemini model name.
    Default changed to a currently supported value; override with GOOGLE_MODEL if needed.
    """
    return (os.getenv("GOOGLE_MODEL") or "gemini-2.0-flash").strip()


def _get_composio_api_key() -> Optional[str]:
    v = os.getenv("COMPOSIO_API_KEY")
    return v.strip() if v and v.strip() else None


def _get_composio_user_id() -> Optional[str]:
    v = os.getenv("COMPOSIO_USER_ID")
    return v.strip() if v and v.strip() else None


def _use_composio_mcp() -> bool:
    """
    Use Composio MCP Link when credentials are configured.
    This is the MCP-based way to access Google Drive + YouTube toolkits.
    """
    return _get_composio_api_key() is not None and _get_composio_user_id() is not None


def _use_google_super_mode() -> bool:
    """
    Google Super mode is enabled by default.
    Set USE_GOOGLE_SUPER_MODE=false to disable.
    """
    val = os.getenv("USE_GOOGLE_SUPER_MODE", "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    return True


def _get_composio_base_url() -> str:
    return (os.getenv("COMPOSIO_BASE_URL") or "https://backend.composio.dev").strip().rstrip("/")


async def _create_composio_tool_router_session(
    *,
    user_id: str,
    api_key: str,
    toolkits: list[str],
    timeout_s: float = 30.0,
) -> dict:
    """
    Create a Composio Tool Router session via HTTP API and return the JSON response.
    This is used to obtain the MCP server URL (session.mcp.url).
    """
    url = f"{_get_composio_base_url()}/api/v3.1/tool_router/session"
    payload: dict = {
        "user_id": user_id,
        # Composio expects either an array of toolkits or the explicit { enable: [...] } syntax.
        "toolkits": {"enable": toolkits},
        # Keep connection manager enabled so the MCP session can guide auth if needed.
        "manage_connections": {"enable": True, "enable_wait_for_connections": False},
        "workbench": {"enable": False, "enable_proxy_execution": False},
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        # Composio supports both x-api-key and x-user-api-key depending on key type.
        for header_name in ("x-api-key", "x-user-api-key"):
            resp = await client.post(url, json=payload, headers={header_name: api_key})
            if resp.status_code == 401:
                continue
            resp.raise_for_status()
            return resp.json()
        # If we got here, both attempts were unauthorized.
        raise ValueError(
            "Composio authorization failed (401). Your COMPOSIO_API_KEY is not accepted for Tool Router session creation. "
            "Verify the key in Composio dashboard and ensure it has Tool Router access."
        )


def _get_youtube_webhook_url() -> Optional[str]:
    """Get Pipedream YouTube webhook URL from environment; None if empty."""
    url = os.getenv("YOUTUBE_WEBHOOK_URL")
    if not url or not url.strip():
        return None
    return url.strip()


def _use_demo_mode() -> bool:
    """Use Gemini-only demo mode when USE_DEMO_MODE=true or no webhook URLs set."""
    if os.getenv("USE_DEMO_MODE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if _use_google_super_mode():
        return False
    # If Composio MCP is configured, prefer tool-enabled mode.
    if _use_composio_mcp():
        return False
    if _get_youtube_webhook_url() is None and _get_secondary_webhook()[0] is None:
        return True
    return False


def _use_webhook_mode() -> bool:
    """Use Pipedream webhook tools (POST to your URLs) when at least one webhook URL is set and not in demo mode."""
    return not _use_demo_mode() and (
        _get_youtube_webhook_url() is not None or _get_secondary_webhook()[0] is not None
    )


def _get_secondary_webhook() -> tuple[Optional[str], Optional[str]]:
    """
    Get optional secondary webhook URL and tool name (drive or notion).
    Returns (url, tool_name) or (None, None) if not configured.
    """
    url = os.getenv("SECONDARY_WEBHOOK_URL")
    if not url or not url.strip():
        return None, None
    tool = (os.getenv("SECONDARY_WEBHOOK_TYPE") or "drive").strip().lower()
    if tool not in ("drive", "notion"):
        tool = "drive"
    return url.strip(), tool


def initialize_model(google_api_key: Optional[str] = None) -> ChatGoogleGenerativeAI:
    """Initialize the Google GenAI chat model. Uses GOOGLE_API_KEY from env if key not provided."""
    key = google_api_key or _get_google_api_key()
    return ChatGoogleGenerativeAI(
        model=_get_google_model_name(),
        google_api_key=key,
    )


def _build_demo_agent(progress_callback: Optional[Callable[[str], None]] = None):
    """Build a Gemini-only agent (no MCP tools) for demo mode. Returns a runnable with ainvoke(state) -> {messages}."""
    if progress_callback:
        progress_callback("Using demo mode (Gemini only, no YouTube/Drive/Notion tools)...")
    model = initialize_model(None)

    def call_model(state: MessagesState):
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_edge(START, "call_model")
    return builder.compile()


def _build_webhook_agent(progress_callback: Optional[Callable[[str], None]] = None):
    """Build agent with tools that POST to your Pipedream webhooks (Drive + YouTube)."""
    if progress_callback:
        progress_callback("Using Pipedream webhook tools (Drive + YouTube)...")
    secondary_url, _ = _get_secondary_webhook()
    tools = get_webhook_tools(drive=secondary_url is not None, youtube=_get_youtube_webhook_url() is not None)
    if not tools:
        raise ValueError("No webhook tools available. Set YOUTUBE_WEBHOOK_URL and/or SECONDARY_WEBHOOK_URL in .env")
    if progress_callback:
        progress_callback("Creating AI agent with webhook tools...")
    model = initialize_model(None)
    return create_react_agent(model, tools)


async def setup_agent_with_tools(
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Any:
    """
    Set up the agent: demo mode (Gemini only) or full MCP with YouTube + optional Drive/Notion.
    Demo mode is used when USE_DEMO_MODE=true or YOUTUBE_WEBHOOK_URL is not set.
    """
    try:
        # Prefer Composio MCP Link (real MCP / JSON-RPC toolkits) when configured.
        if _use_composio_mcp():
            if progress_callback:
                progress_callback("Using Composio MCP Link (YouTube + Google Drive)...")

            api_key = _get_composio_api_key() or ""
            user_id = _get_composio_user_id() or ""
            session = await _create_composio_tool_router_session(
                user_id=user_id,
                api_key=api_key,
                toolkits=["youtube", "googledrive", "notion"],
            )
            mcp_url = (session.get("mcp") or {}).get("url")
            if not mcp_url:
                raise ValueError("Composio session did not return an MCP URL (mcp.url).")

            client = MultiServerMCPClient(
                {
                    "composio": {
                        "transport": "streamable_http",
                        "url": mcp_url,
                        "headers": {"x-api-key": api_key},
                    }
                }
            )
            if progress_callback:
                progress_callback("Getting available tools...")
            tools = await client.get_tools()
            if progress_callback:
                progress_callback("Creating AI agent...")
            model = initialize_model(None)
            agent = create_react_agent(model, tools)
            if progress_callback:
                progress_callback("Setup complete! Starting to generate learning path...")
            return agent

        if _use_demo_mode():
            return _build_demo_agent(progress_callback)

        # Use Pipedream webhook tools (POST to your URLs) instead of MCP
        if _use_webhook_mode():
            return _build_webhook_agent(progress_callback)

        # Fallback: MCP (only if you have real MCP endpoints)
        if progress_callback:
            progress_callback("Setting up agent with MCP tools...")

        youtube_url = _get_youtube_webhook_url()
        if not youtube_url:
            return _build_demo_agent(progress_callback)

        tools_config = {
            "youtube": {
                "url": youtube_url,
                "transport": "streamable_http",
            }
        }

        secondary_url, secondary_tool = _get_secondary_webhook()
        if secondary_url and secondary_tool:
            tools_config[secondary_tool] = {
                "url": secondary_url,
                "transport": "streamable_http",
            }
            if progress_callback:
                label = "Google Drive" if secondary_tool == "drive" else "Notion"
                progress_callback(f"Added {label} integration...")

        if progress_callback:
            progress_callback("Initializing MCP client...")
        mcp_client = MultiServerMCPClient(tools_config)

        if progress_callback:
            progress_callback("Getting available tools...")
        def _is_mcp_response_error(e: BaseException) -> bool:
            msg = str(e).lower()
            sub = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            if "jsonrpc" in msg or "jsonrpcmessage" in msg or "error parsing json" in msg:
                return True
            if isinstance(e, PydanticValidationError) and "JSONRPCMessage" in str(e):
                return True
            if sub and _is_mcp_response_error(sub):
                return True
            return False

        try:
            tools = await mcp_client.get_tools()
        except PydanticValidationError as e:
            if _is_mcp_response_error(e):
                raise ValueError(
                    "Your webhook URLs must be MCP (Model Context Protocol) endpoints that speak JSON-RPC, "
                    "not plain HTTP webhooks. The app received a response like {'success': True, ...} instead of "
                    "JSON-RPC (jsonrpc, method, id, result). Use MCP-compatible Pipedream workflows or an MCP server."
                ) from e
            raise
        except Exception as e:
            if _is_mcp_response_error(e):
                raise ValueError(
                    "Webhook URLs returned invalid MCP/JSON-RPC. The endpoints must implement the MCP protocol. "
                    "YOUTUBE_WEBHOOK_URL and SECONDARY_WEBHOOK_URL cannot be ordinary Pipedream webhooks."
                ) from e
            raise

        if progress_callback:
            progress_callback("Creating AI agent...")
        google_api_key = _get_google_api_key()
        mcp_orch_model = initialize_model(google_api_key)
        agent = create_react_agent(mcp_orch_model, tools)

        if progress_callback:
            progress_callback("Setup complete! Starting to generate learning path...")

        return agent
    except Exception as e:
        if progress_callback:
            progress_callback(f"Setup error: {str(e)}")
        raise


def run_agent_sync(
    user_goal: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Connect to the attached backend and generate a learning path.
    The backend should be running on http://localhost:8000 by default.

    If the backend is unreachable, this function falls back to running the agent locally
    (demo/webhook/MCP depending on environment configuration).
    """

    async def _run_local() -> dict:
        if progress_callback:
            progress_callback("Backend unavailable — switching to local agent...")

        # If Composio MCP is available, generate Drive doc + YouTube playlist without relying on LLM quota.
        if _use_composio_mcp():
            if progress_callback:
                progress_callback("Preparing MCP session...")

            api_key = _get_composio_api_key() or ""
            user_id = _get_composio_user_id() or ""
            session = await _create_composio_tool_router_session(
                user_id=user_id,
                api_key=api_key,
                toolkits=["youtube", "googledrive"],
            )
            mcp_url = (session.get("mcp") or {}).get("url")
            if not mcp_url:
                raise ValueError("Composio session did not return an MCP URL (mcp.url).")

            client = MultiServerMCPClient(
                {"composio": {"transport": "streamable_http", "url": mcp_url, "headers": {"x-api-key": api_key}}}
            )
            try:
                tools = await client.get_tools()
                tmap = {t.name: t for t in tools}
                # Search for tools (also gives a session_id for the executor).
                search_raw = await tmap["COMPOSIO_SEARCH_TOOLS"].ainvoke(
                    {"query": "Create a Google Drive document from text and create a YouTube playlist; add videos to it."}
                )
                import json as _json  # local import to avoid polluting module namespace

                search = _json.loads(search_raw) if isinstance(search_raw, str) else (search_raw or {})
                session_id = ((search.get("data") or {}).get("session_id")) or ((search.get("data") or {}).get("sessionId"))
                if not session_id:
                    # Some environments may omit it; fall back to the tool-router session id.
                    session_id = session.get("session_id")
                if not session_id:
                    raise ValueError("Composio did not return a session_id for tool execution.")

                # If connections are missing, initiate and return auth links.
                statuses = (search.get("data") or {}).get("toolkit_connection_statuses") or []
                missing = [
                    s.get("toolkit")
                    for s in statuses
                    if s.get("has_active_connection") is False and s.get("toolkit")
                ]
                # Require only YouTube + Drive at this stage; Notion is fallback-only.
                missing = sorted({m for m in missing if m in ("youtube", "googledrive")})
                if missing:
                    mg_raw = await tmap["COMPOSIO_MANAGE_CONNECTIONS"].ainvoke({"toolkits": missing})
                    mg = _json.loads(mg_raw) if isinstance(mg_raw, str) else (mg_raw or {})
                    results = ((mg.get("data") or {}).get("results")) or {}
                    lines = ["Connections are required before I can create the Drive doc / YouTube playlist:"]
                    for tk in missing:
                        r = results.get(tk) or {}
                        url = r.get("redirect_url")
                        if url:
                            lines.append(f"- Connect {tk}: {url}")
                    lines.append("After connecting, click Generate again.")
                    return {"status": "needs_auth", "messages": [{"role": "ai", "content": "\n".join(lines)}]}

                plan = _build_structured_learning_path(
                    user_goal,
                    days=_desired_days_from_goal(user_goal, default_days=7),
                )

                if progress_callback:
                    progress_callback("Finding videos for each day...")

                # 1) Search YouTube for each day's best video (parallel)
                yt_search_tools = [
                    {
                        "tool_slug": "YOUTUBE_SEARCH_YOU_TUBE",
                        "arguments": {"q": p["youtube_query"], "maxResults": 5, "type": "video"},
                    }
                    for p in plan
                ]
                yt_search_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                    {
                        "session_id": session_id,
                        "current_step": "YOUTUBE_SEARCH",
                        "current_step_metric": f"0/{len(yt_search_tools)}",
                        "tools": yt_search_tools,
                        "sync_response_to_workbench": False,
                        "memory": {},
                        "thought": "Search YouTube for suitable videos for each day.",
                    }
                )
                yt_search = _json.loads(yt_search_raw) if isinstance(yt_search_raw, str) else (yt_search_raw or {})
                results = (yt_search.get("data") or {}).get("results") or []
                video_ids: list[str] = []
                used_vids: set[str] = set()
                for r in results:
                    resp = (r or {}).get("response") or {}
                    data = (resp or {}).get("data") if (resp or {}).get("successful") is True else None
                    vid = _pick_unique_youtube_video_id(data or {}, used_vids)
                    if vid:
                        used_vids.add(vid)
                    video_ids.append(vid or "")

                # 2) Create playlist
                if progress_callback:
                    progress_callback("Creating YouTube playlist...")
                playlist_title = f"Learning Path: {user_goal}".strip()
                create_pl_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                    {
                        "session_id": session_id,
                        "current_step": "YOUTUBE_CREATE_PLAYLIST",
                        "current_step_metric": "0/1",
                        "tools": [
                            {
                                "tool_slug": "YOUTUBE_CREATE_PLAYLIST",
                                "arguments": {
                                    "title": playlist_title[:140],
                                    "description": "Auto-generated learning path playlist.",
                                },
                            }
                        ],
                        "sync_response_to_workbench": False,
                        "memory": {},
                        "thought": "Create a new YouTube playlist for the learning path.",
                    }
                )
                create_pl = _json.loads(create_pl_raw) if isinstance(create_pl_raw, str) else (create_pl_raw or {})
                playlist_id = _extract_playlist_id(create_pl)
                if not playlist_id:
                    # surface any structured error if present
                    err = create_pl.get("error") or ((create_pl.get("data") or {}).get("error"))
                    hint = f" Tool error: {err}" if err else ""
                    raise ValueError(f"Failed to create YouTube playlist (missing playlist id).{hint}")

                # 3) Add videos (skip blanks)
                if progress_callback:
                    progress_callback("Adding videos to playlist...")
                vids_to_add = [vid for vid in video_ids if vid]
                added = 0
                for pos, vid in enumerate(vids_to_add):
                    # sequential + retry is much more reliable than batching for YouTube inserts
                    for attempt in range(3):
                        add_one_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                            {
                                "session_id": session_id,
                                "current_step": "YOUTUBE_ADD_VIDEO",
                                "current_step_metric": f"{added}/{len(vids_to_add)}",
                                "tools": [
                                    {
                                        "tool_slug": "YOUTUBE_ADD_VIDEO_TO_PLAYLIST",
                                        "arguments": {"playlistId": playlist_id, "videoId": vid, "position": pos},
                                    }
                                ],
                                "sync_response_to_workbench": False,
                                "memory": {},
                                "thought": "Add one video to the playlist.",
                            }
                        )
                        add_one = _json.loads(add_one_raw) if isinstance(add_one_raw, str) else (add_one_raw or {})
                        d = add_one.get("data") or {}
                        if (d.get("error_count") or 0) == 0 and (d.get("success_count") or 0) >= 1:
                            added += 1
                            break
                        # retry only transient failures
                        err_blob = ""
                        try:
                            r0 = (d.get("results") or [])[0] or {}
                            err_blob = str(((r0.get("response") or {}).get("error")) or "")
                        except Exception:
                            err_blob = ""
                        if "SERVICE_UNAVAILABLE" in err_blob.upper() and attempt < 2:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        break

                if added == 0 and vids_to_add:
                    raise ValueError("No videos were added to the playlist (all attempts failed).")
                if added < len(vids_to_add) and progress_callback:
                    progress_callback(
                        f"Warning: Added {added}/{len(vids_to_add)} videos to the playlist. You can rerun to try again."
                    )

                # 4) Create Drive document from text
                if progress_callback:
                    progress_callback("Creating Google Drive document...")
                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
                lines = [f"Learning Path: {user_goal}", f"YouTube Playlist: {playlist_url}", ""]
                for p, vid in zip(plan, video_ids, strict=False):
                    url = (
                        f"https://www.youtube.com/watch?v={vid}"
                        if vid
                        else f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(p['youtube_query'])}"
                    )
                    lines.append(f"Day {p['day']}: {p['title']}")
                    lines.append(f"Focus: {p['focus']}")
                    lines.append(f"YouTube: {url}")
                    lines.append("")
                doc_text = "\n".join(lines).strip()

                doc_url: Optional[str] = None
                drive_error: Optional[str] = None
                try:
                    drive_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                        {
                            "session_id": session_id,
                            "current_step": "DRIVE_CREATE_DOC",
                            "current_step_metric": "0/1",
                            "tools": [
                                {
                                    "tool_slug": "GOOGLEDRIVE_CREATE_FILE_FROM_TEXT",
                                    "arguments": {
                                        "file_name": f"Learning Path - {user_goal}"[:180],
                                        "text_content": doc_text,
                                        "mime_type": "application/vnd.google-apps.document",
                                    },
                                }
                            ],
                            "sync_response_to_workbench": False,
                            "memory": {},
                            "thought": "Create the learning path document in Google Drive from text.",
                        }
                    )
                    drive = _json.loads(drive_raw) if isinstance(drive_raw, str) else (drive_raw or {})
                    file_id = _extract_drive_file_id(drive)
                    if file_id:
                        doc_url = f"https://docs.google.com/document/d/{file_id}/edit"
                    else:
                        err = drive.get("error") or ((drive.get("data") or {}).get("error"))
                        drive_error = f"Drive create failed (missing file id). {err or ''}".strip()
                except Exception as e:
                    drive_error = str(e)

                # Fallback: Notion page
                if not doc_url:
                    if progress_callback:
                        progress_callback("Google Drive unavailable — trying Notion fallback...")

                    notion_search_raw = await tmap["COMPOSIO_SEARCH_TOOLS"].ainvoke(
                        {"query": "Create a Notion page from markdown text content."}
                    )
                    notion_search = _json.loads(notion_search_raw) if isinstance(notion_search_raw, str) else (notion_search_raw or {})
                    notion_statuses = (notion_search.get("data") or {}).get("toolkit_connection_statuses") or []
                    notion_missing = any(
                        s.get("toolkit") == "notion" and s.get("has_active_connection") is False
                        for s in notion_statuses
                    )
                    if notion_missing:
                        mg_raw = await tmap["COMPOSIO_MANAGE_CONNECTIONS"].ainvoke({"toolkits": ["notion"]})
                        mg = _json.loads(mg_raw) if isinstance(mg_raw, str) else (mg_raw or {})
                        notion_url = ((((mg.get("data") or {}).get("results") or {}).get("notion") or {}).get("redirect_url"))
                        raise ValueError(
                            f"{drive_error or 'Google Drive failed.'} "
                            f"Notion is not connected. Connect Notion and retry: {notion_url or 'no auth link returned'}"
                        )

                    parent_id = (os.getenv("NOTION_PARENT_PAGE_ID") or "").strip()
                    if not parent_id:
                        # Best effort: pick a page from search results to use as parent.
                        p_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                            {
                                "session_id": session_id,
                                "current_step": "NOTION_FIND_PARENT",
                                "current_step_metric": "0/1",
                                "tools": [
                                    {
                                        "tool_slug": "NOTION_SEARCH_NOTION_PAGE",
                                        "arguments": {"query": user_goal, "page_size": 1},
                                    }
                                ],
                                "sync_response_to_workbench": False,
                                "memory": {},
                                "thought": "Find a parent Notion page.",
                            }
                        )
                        p_obj = _json.loads(p_raw) if isinstance(p_raw, str) else (p_raw or {})
                        p_data = _extract_multi_response_data(p_obj)
                        parent_id = _extract_notion_parent_id(p_data) or ""

                    if not parent_id:
                        raise ValueError(
                            f"{drive_error or 'Google Drive failed.'} "
                            "Notion fallback requires a parent page id. Set NOTION_PARENT_PAGE_ID in .env and retry."
                        )

                    n_raw = await tmap["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(
                        {
                            "session_id": session_id,
                            "current_step": "NOTION_CREATE_PAGE",
                            "current_step_metric": "0/1",
                            "tools": [
                                {
                                    "tool_slug": "NOTION_CREATE_NOTION_PAGE",
                                    "arguments": {
                                        "parent_id": parent_id,
                                        "title": f"Learning Path - {user_goal}"[:180],
                                        "markdown": doc_text,
                                    },
                                }
                            ],
                            "sync_response_to_workbench": False,
                            "memory": {},
                            "thought": "Create Notion page from markdown content.",
                        }
                    )
                    n_obj = _json.loads(n_raw) if isinstance(n_raw, str) else (n_raw or {})
                    n_data = _extract_multi_response_data(n_obj)
                    notion_url = _extract_notion_page_link(n_data)
                    if not notion_url:
                        raise ValueError(
                            f"{drive_error or 'Google Drive failed.'} "
                            "Notion fallback also failed to return page URL."
                        )
                    doc_url = notion_url
                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

                content = (
                    f"Here is your learning path document link:\n{doc_url}\n\n"
                    f"Here is your YouTube playlist link:\n{playlist_url}"
                )
                if progress_callback:
                    progress_callback("Learning path generation complete!")
                return {"status": "success", "messages": [{"role": "ai", "content": content}]}
            finally:
                aclose = getattr(client, "aclose", None)
                if callable(aclose):
                    try:
                        await aclose()
                    except Exception:
                        pass

        # If we're in demo mode without reliable model access, generate an offline plan
        # so the app still works without external services.
        if _use_demo_mode():
            content = _build_offline_learning_path(user_goal, days=7)
            if progress_callback:
                progress_callback("Learning path generation complete!")
            return {"status": "success", "messages": [{"role": "ai", "content": content}]}

        agent = await setup_agent_with_tools(progress_callback=progress_callback)

        prompt_addition = DEMO_PROMPT_ADDITION if _use_demo_mode() else ""
        prompt = f"{user_goal_prompt}\n{prompt_addition}\n\nUser goal: {user_goal}".strip()

        result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]}, config=cfg)
        messages = result.get("messages") or []
        last = messages[-1] if messages else None
        content = getattr(last, "content", None) if last is not None else None
        if not content and isinstance(last, dict):
            content = last.get("content")
        content = content or "No output was generated."

        if progress_callback:
            progress_callback("Learning path generation complete!")

        return {"status": "success", "messages": [{"role": "ai", "content": content}]}

    async def _run():
        try:
            if progress_callback:
                progress_callback("Connecting to the AI Intelligence Backend...")

            # Google Super architecture (Calendar + Tasks + Drive execution loop), enabled by default.
            if _use_google_super_mode():
                super_result = await run_google_super_mode(
                    goal=user_goal,
                    progress_callback=progress_callback,
                )
                # Enhance existing output with current MCP flow (playlist + doc),
                # without breaking if the enhancement path fails.
                if _use_composio_mcp():
                    try:
                        if progress_callback:
                            progress_callback("Enhancing output with playlist/document flow...")
                        base_result = await _run_local()
                        super_msg = ((super_result.get("messages") or [{}])[0]).get("content", "")
                        base_msg = ((base_result.get("messages") or [{}])[0]).get("content", "")
                        merged = (
                            "## Google Super Execution\n"
                            f"{super_msg}\n\n"
                            "## Learning Path Output\n"
                            f"{base_msg}"
                        ).strip()
                        return {
                            "status": "success",
                            "messages": [{"role": "ai", "content": merged}],
                            "metadata": {
                                "google_super": super_result.get("metadata") or {},
                                "learning_path": base_result.get("metadata") or {},
                            },
                        }
                    except Exception as e:
                        # Keep super output even if enhancement fails.
                        super_msg = ((super_result.get("messages") or [{}])[0]).get("content", "")
                        merged = (
                            "## Google Super Execution\n"
                            f"{super_msg}\n\n"
                            "## Learning Path Output\n"
                            f"Enhancement skipped due to error: {str(e)}"
                        ).strip()
                        return {"status": "success", "messages": [{"role": "ai", "content": merged}]}
                return super_result

            # If Composio MCP is configured, run locally so the agent can call MCP tools
            # to create the Drive doc + YouTube playlist.
            if _use_composio_mcp():
                return await _run_local()

            backend_url = (os.getenv("BACKEND_URL") or "http://localhost:8000/mcp/execute").strip()
            
            payload = {
                "action": "generate_learning_path",
                "input": {
                    "topic": user_goal,
                    "composio_api_key": _get_composio_api_key(),
                    "google_api_key": _get_google_api_key(),
                }
            }

            if progress_callback:
                progress_callback("Orchestrating study plan creation with AI Agent...")

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(backend_url, json=payload)
                response.raise_for_status()
                result = response.json()

            if progress_callback:
                progress_callback("Learning path generation complete!")

            return result
        except httpx.RequestError as e:
            # This includes connect errors like "All connection attempts failed"
            if progress_callback:
                progress_callback(f"Backend connection failed: {str(e)}")
            return await _run_local()
        except Exception as e:
            if progress_callback:
                error_msg = f"Error connecting to backend: {str(e)}"
                progress_callback(error_msg)
                if "404" in str(e):
                    progress_callback("Please ensure the FastAPI backend is running on port 8000.")
            raise

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
