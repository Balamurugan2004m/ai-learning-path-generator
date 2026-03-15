from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from prompt import user_goal_prompt
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Optional, Tuple, Any, Callable, Dict
import asyncio
import re

cfg = RunnableConfig(recursion_limit=100)


def parse_user_goal(user_goal: str) -> Dict[str, Optional[str]]:
    """
    Heuristically parse the free-form user goal into structured fields.

    Extracts:
    - topic: main thing the user wants to learn
    - days: total number of days (as string)
    - level: one of: beginner, intermediate, advanced, basics (if detected)
    """
    text = user_goal.lower()

    # Extract days like "in 3 days" or "for 10 days"
    days_match = re.search(r'(\d+)\s*day', text)
    days = days_match.group(1) if days_match else None

    # Simple level detection
    level = None
    if "beginner" in text:
        level = "beginner"
    elif "intermediate" in text:
        level = "intermediate"
    elif "advanced" in text:
        level = "advanced"
    elif "basic" in text or "basics" in text:
        level = "basics"

    # Heuristic topic extraction:
    # Try to grab what comes after "learn" and before "in X days"/"for X days"
    topic = None
    learn_idx = text.find("learn")
    if learn_idx != -1:
        after_learn = user_goal[learn_idx + len("learn") :].strip()
        # Cut at "in N days"/"for N days" if present
        cut_match = re.search(r'\b(in|for)\s+\d+\s*day', after_learn.lower())
        if cut_match:
            topic = after_learn[: cut_match.start()].strip(" .,:")
        else:
            topic = after_learn.strip(" .,:")

    return {"topic": topic or None, "days": days, "level": level}

def initialize_model(google_api_key: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=google_api_key
    )

async def setup_agent_with_tools(
    google_api_key: str,
    youtube_pipedream_url: str,
    drive_pipedream_url: Optional[str] = None,
    notion_pipedream_url: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Any:
    """
    Set up the agent with YouTube (mandatory) and optional Drive or Notion tools.
    """
    try:
        if progress_callback:
            progress_callback("Setting up agent with tools... ✅")
        
        # Initialize tools configuration with mandatory YouTube
        tools_config = {
            "youtube": {
                "url": youtube_pipedream_url,
                "transport": "streamable_http"
            }
        }

        # Add Drive if URL provided
        if drive_pipedream_url:
            tools_config["drive"] = {
                "url": drive_pipedream_url,
                "transport": "streamable_http"
            }
            if progress_callback:
                progress_callback("Added Google Drive integration... ✅")

        # Add Notion if URL provided
        if notion_pipedream_url:
            tools_config["notion"] = {
                "url": notion_pipedream_url,
                "transport": "streamable_http"
            }
            if progress_callback:
                progress_callback("Added Notion integration... ✅")

        if progress_callback:
            progress_callback("Initializing MCP client... ✅")
        # Initialize MCP client with configured tools
        mcp_client = MultiServerMCPClient(tools_config)
        
        if progress_callback:
            progress_callback("Getting available tools... ✅")
        # Get all tools
        tools = await mcp_client.get_tools()
        
        if progress_callback:
            progress_callback("Creating AI agent... ✅")
        # Create agent with initialized model
        mcp_orch_model = initialize_model(google_api_key)
        agent = create_react_agent(mcp_orch_model, tools)
        
        if progress_callback:
            progress_callback("Setup complete! Starting to generate learning path... ✅")
        
        return agent
    except Exception as e:
        print(f"Error in setup_agent_with_tools: {str(e)}")
        raise

def run_agent_sync(
    google_api_key: str,
    youtube_pipedream_url: str,
    drive_pipedream_url: Optional[str] = None,
    notion_pipedream_url: Optional[str] = None,
    user_goal: str = "",
    progress_callback: Optional[Callable[[str], None]] = None
) -> dict:
    """
    Synchronous wrapper for running the agent.
    """
    async def _run():
        try:
            agent = await setup_agent_with_tools(
                google_api_key=google_api_key,
                youtube_pipedream_url=youtube_pipedream_url,
                drive_pipedream_url=drive_pipedream_url,
                notion_pipedream_url=notion_pipedream_url,
                progress_callback=progress_callback
            )

            # Parse the user goal into structured fields for tighter control
            parsed = parse_user_goal(user_goal)

            # Build a structured prompt prefix that the agent must follow
            structured_prefix_parts = [
                "User Goal (raw): " + user_goal,
                "",
                "Parsed Goal (structured):",
                f"- Main topic: {parsed.get('topic') or 'Unknown'}",
                f"- Level: {parsed.get('level') or 'Not specified'}",
                f"- Duration in days: {parsed.get('days') or 'Not specified'}",
                "",
            ]

            # If we detected an explicit day count, enforce exact days
            if parsed.get("days"):
                structured_prefix_parts.append(
                    f"STRICT REQUIREMENT: You MUST generate a day-wise learning path "
                    f"using exactly {parsed['days']} days. Do not use a different number of days."
                )
            else:
                structured_prefix_parts.append(
                    "If duration is not specified, choose a reasonable small number of days "
                    "for a foundational learning path and be consistent throughout."
                )

            structured_prefix = "\n".join(structured_prefix_parts) + "\n\n"

            # Combine structured prefix with the main instruction prompt
            learning_path_prompt = structured_prefix + user_goal_prompt
            
            if progress_callback:
                progress_callback("Generating your learning path...")
            
            # Run the agent
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=learning_path_prompt)]},
                config=cfg
            )
            
            if progress_callback:
                progress_callback("Learning path generation complete!")
            
            return result
        except Exception as e:
            print(f"Error in _run: {str(e)}")
            raise

    # Run in new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
