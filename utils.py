"""
Agent and MCP setup for the Learning Path Generator.
Reads API keys and webhook URLs from environment variables.
- Demo mode: Gemini only (USE_DEMO_MODE=true or no webhooks).
- Webhook mode: custom tools POST to your Pipedream URLs (Drive + YouTube).
- MCP mode: optional, for MCP-compatible endpoints.
"""
import os
from typing import Optional, Any, Callable

from dotenv import load_dotenv
load_dotenv()

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

cfg = RunnableConfig(recursion_limit=100)

# Prompt addition for demo mode (no YouTube/Drive/Notion tools)
DEMO_PROMPT_ADDITION = """
You do not have access to YouTube or Google Drive/Notion tools. Generate a day-by-day learning path as structured text only.
Include: day number, topic, and suggested resource types or search terms (e.g. "Search: Python basics tutorial"). Format clearly with headers.
"""


def _get_google_api_key() -> str:
    """Get hardcoded Google API key as requested."""
    return "AIzaSyCPbpDMiW6x-LGeR6Q7HPNpKiDyz1g2SYo"


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
        model="gemini-2.5-flash",
        google_api_key=key,
    )


def _build_demo_agent(progress_callback: Optional[Callable[[str], None]] = None):
    """Build a Gemini-only agent (no MCP tools) for demo mode. Returns a runnable with ainvoke(state) -> {messages}."""
    if progress_callback:
        progress_callback("Using demo mode (Gemini only, no YouTube/Drive/Notion tools)... ✅")
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
        progress_callback("Using Pipedream webhook tools (Drive + YouTube)... ✅")
    secondary_url, _ = _get_secondary_webhook()
    tools = get_webhook_tools(drive=secondary_url is not None, youtube=_get_youtube_webhook_url() is not None)
    if not tools:
        raise ValueError("No webhook tools available. Set YOUTUBE_WEBHOOK_URL and/or SECONDARY_WEBHOOK_URL in .env")
    if progress_callback:
        progress_callback("Creating AI agent with webhook tools... ✅")
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
        if _use_demo_mode():
            return _build_demo_agent(progress_callback)

        # Use Pipedream webhook tools (POST to your URLs) instead of MCP
        if _use_webhook_mode():
            return _build_webhook_agent(progress_callback)

        # Fallback: MCP (only if you have real MCP endpoints)
        if progress_callback:
            progress_callback("Setting up agent with MCP tools... ✅")

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
                progress_callback(f"Added {label} integration... ✅")

        if progress_callback:
            progress_callback("Initializing MCP client... ✅")
        mcp_client = MultiServerMCPClient(tools_config)

        if progress_callback:
            progress_callback("Getting available tools... ✅")
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
            progress_callback("Creating AI agent... ✅")
        google_api_key = _get_google_api_key()
        mcp_orch_model = initialize_model(google_api_key)
        agent = create_react_agent(mcp_orch_model, tools)

        if progress_callback:
            progress_callback("Setup complete! Starting to generate learning path... ✅")

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
    The backend should be running on http://localhost:8000.
    """
    async def _run():
        try:
            if progress_callback:
                progress_callback("Connecting to the AI Intelligence Backend... ✅")

            # Hardcoded backend endpoint
            backend_url = "http://localhost:8000/mcp/execute"
            
            payload = {
                "action": "generate_learning_path",
                "input": {
                    "topic": user_goal,
                    "composio_api_key": "ak_sRchiR71nshYZflar7f2", # Redundant if backend is hardcoded, but safe
                    "google_api_key": "AIzaSyCPbpDMiW6x-LGeR6Q7HPNpKiDyz1g2SYo"
                }
            }

            if progress_callback:
                progress_callback("Orchestrating study plan creation with AI Agent... ✅")

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(backend_url, json=payload)
                response.raise_for_status()
                result = response.json()

            if progress_callback:
                progress_callback("Learning path generation complete! ✅")

            return result
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
