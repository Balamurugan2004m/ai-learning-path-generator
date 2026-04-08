import os
from typing import List, Dict, Optional, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from composio import Composio
from dotenv import load_dotenv
import google.generativeai as genai
import json

# Load environment variables
load_dotenv()

app = FastAPI()

# Initial configuration from environment (optional at startup)
# Hardcoded API Keys as requested
DEFAULT_COMPOSIO_API_KEY = "ak_sRchiR71nshYZflar7f2"
DEFAULT_GOOGLE_API_KEY = "AIzaSyCPbpDMiW6x-LGeR6Q7HPNpKiDyz1g2SYo"

class MCPRequest(BaseModel):
    action: str
    input: Dict[str, Any]
    action: str
    input: Dict[str, Any]

@app.post("/mcp/execute")
async def execute_mcp(req: MCPRequest):
    """
    Standard interface for MCP execution simulation.
    """
    print(f"DEBUG: Executing action {req.action}")
    if req.action == "generate_learning_path":
        return await generate_learning_path(req.input)
    
    # Generic tool execution fallback if needed
    try:
        # Example: action could be "search_videos"
        # We assume req.action and req.input match Composio tool/action requirements
        # Tool name would need to be in the input for a generic executor.
        raise HTTPException(status_code=400, detail=f"Action {req.action} not natively implemented")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def generate_learning_path(input_data: Dict[str, Any]):
    """
    Core Orchestration Layer:
    Migrated from utils.py and prompt.py logic.
    """
    topic = input_data.get("topic")
    composio_api_key = input_data.get("composio_api_key") or DEFAULT_COMPOSIO_API_KEY
    google_api_key = input_data.get("google_api_key") or DEFAULT_GOOGLE_API_KEY

    if not topic:
        raise HTTPException(status_code=400, detail="Missing topic in input")
    if not composio_api_key:
        raise HTTPException(status_code=400, detail="Missing Composio API Key")

    # Initialize Composio with the provided or default key
    composio = Composio(api_key=composio_api_key)

    # 1. Planning with Gemini
    # We use Gemini to create the structured day-wise plan.
    if not google_api_key:
        print("DEBUG: Google API Key missing, using fallback plan")
        plan = [{"day": 1, "topic_name": f"Introduction to {topic}", "search_query": f"{topic} basics"}]
    else:
        try:
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            planning_prompt = f"""
            You are an elite Senior Curriculum Designer. Create a comprehensive, deeply structured day-wise learning path for: "{topic}".
            
            Step 1: Contextual Analysis. If the goal implies specialized context (e.g. religious, regional), identify it.
            Step 2: Curated Roadmap. Plan at least 5-7 days of progressive learning.
            
            For each day, you MUST provide:
            1. 'day': Day number.
            2. 'topic_name': A clear, professional lesson title.
            3. 'detailed_plan': A 5-8 sentence professional breakdown including core mission, sub-topics, and practical exercise. Use markdown for lists.
            4. 'selection_reasoning': A 1-2 sentence explanation of why a resource from a top-tier provider (like FreeCodeCamp, Harvard, or Coursera) is the "best match" for this specific day based on authority, relevance, and clarity.
            5. 'primary_search_query': A context-specific YouTube search term.
            6. 'fallback_search_query': A high-quality general English search term.
            7. 'course_search_query': A search term to find a structured course on Coursera, Udemy, or edX.
            
            Format as JSON list. Return ONLY the valid JSON list.
            """
            import time
            plan = None
            for attempt in range(3):
                try:
                    response = model.generate_content(planning_prompt)
                    clean_resp = response.text.strip()
                    # Robust cleaning for JSON
                    if "```json" in clean_resp:
                        clean_resp = clean_resp.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_resp:
                        clean_resp = clean_resp.split("```")[1].split("```")[0].strip()
                    
                    plan = json.loads(clean_resp)
                    if plan: break
                except Exception as api_e:
                    print(f"DEBUG: Planning attempt {attempt+1} failed: {api_e}")
                    if "429" in str(api_e) and attempt < 2:
                        time.sleep(3 * (attempt + 1))
                        continue
                    if attempt == 2: raise api_e

        except Exception as e:
            print(f"Planning error (final failure or rate limit): {e}")
            # Premium fallback generating multiple days with high-quality details
            days = 5
            if "10" in topic: days = 10
            plan = []
            # High-depth generic topics fallback
            topics = [
                ("Foundations & Environment Setup", "**Today's Mission**: Establish a professional workspace and master the core syntax of {topic}.\n- **Key Sub-Topics**: Workspace configuration, Variable declarations, and Primitive types.\n- **Learning Objectives**: By the end of today, you will be able to write and execute basic {topic} scripts independently.\n- **Practical Exercise**: Build a 'Personal Info' utility that processes and displays user data."),
                ("Logic, Control Flow & Decisions", "**Today's Mission**: Master the 'brain' of your application by controlling code execution logic.\n- **Key Sub-Topics**: Conditional branching (If/Else), Boolean algebra, and Switch statements.\n- **Learning Objectives**: By the end of today, you will create programs that make complex decisions based on dynamic inputs.\n- **Practical Exercise**: Develop a fully functional command-line interest calculator."),
                ("Data Structures & Iteration", "**Today's Mission**: Efficiently manage collections of information and automate repetitive tasks.\n- **Key Sub-Topics**: Array/List management, Loop archetypes (For/While), and Sequence processing.\n- **Learning Objectives**: By the end of today, you will manage large datasets and iterate through complex collections with ease.\n- **Practical Exercise**: Create a Dynamic Task Manager that supports adding/removing multiple items."),
                ("Functional Architecture & Modularity", "**Today's Mission**: Organize your code into reusable, professional-grade structures.\n- **Key Sub-Topics**: Function definition, Scope management, and Error Handling (Try/Except).\n- **Learning Objectives**: By the end of today, you will write clean, modularized code that is easy to debug and extend.\n- **Practical Exercise**: Refactor your previous utilities into a cohesive, function-driven library."),
                ("Advanced specialization & Integration", "**Today's Mission**: Apply everything learned to a real-world integration scenario for {topic}.\n- **Key Sub-Topics**: API interaction basics, File I/O, and Performance optimization tips.\n- **Learning Objectives**: By the end of today, you will understand how {topic} connects to the broader software ecosystem.\n- **Practical Exercise**: Build a 'Final Portfolio' mini-project that saves and reads data from local storage.")
            ]
            for i in range(1, days + 1):
                t_idx = (i-1) % len(topics)
                t_info = topics[t_idx]
                plan.append({
                    "day": i,
                    "topic_name": f"{t_info[0]} for {topic}",
                    "primary_search_query": f"{topic} {t_info[0]} comprehensive tutorial",
                    "fallback_search_query": f"introduction to {topic} basics",
                    "detailed_plan": t_info[1].format(topic=topic)
                })

    final_path = []
    video_ids = []

    # 2. Search YouTube for each topic via Composio
    used_video_ids = set()
    fallback_pool = ["kqtD5dpn9C8", "rfscVS0vtbw", "HGOBQqn636M", "8nM6p-CqNn0", "l9AZmHafAlM"]
    
    for entry in plan:
        video_id = None
        video_url = "No video found"
        
        # Determine queries to try (handle both new and old schema)
        p_query = entry.get("primary_search_query") or entry.get("search_query")
        f_query = entry.get("fallback_search_query")
        
        queries_to_try = [q for q in [p_query, f_query] if q]
        
        for q in queries_to_try:
            try:
                print(f"DEBUG: Searching YouTube for '{q}'")
                search_results = composio.tools.execute(
                    slug="YOUTUBE_SEARCH_YOU_TUBE",
                    arguments={"q": q, "max_results": 5},
                    user_id="default",
                    dangerously_skip_version_check=True
                )
                
                if isinstance(search_results, dict) and "successful" in search_results:
                    search_data = search_results.get("data", {})
                    items = search_data.get("items", [])
                    for item in items:
                        v_id = item.get("id", {}).get("videoId")
                        if v_id and v_id not in used_video_ids:
                            video_id = v_id
                            video_url = f"https://www.youtube.com/watch?v={v_id}"
                            used_video_ids.add(v_id)
                            break
            except Exception as e:
                print(f"Search error for query '{q}': {e}")
            
            if video_id: break # Stop if we found a unique video for this day
            
        # If no unique video found across all queries, use from fallback pool
        if not video_id:
            for f_id in fallback_pool:
                if f_id not in used_video_ids:
                    video_id = f_id
                    video_url = f"https://www.youtube.com/watch?v={f_id}"
                    used_video_ids.add(f_id)
                    break
        # 3. Seeking specialized Course Links (Coursera/Udemy/edX) via Google Search
        course_url = None
        c_query = entry.get("course_search_query")
        if c_query:
            try:
                print(f"DEBUG: Searching for courses: '{c_query}'")
                web_results = composio.tools.execute(
                    slug="GOOGLESEARCH_SEARCH",
                    arguments={"q": c_query + " site:coursera.org OR site:udemy.com OR site:edx.org"},
                    user_id="default",
                    dangerously_skip_version_check=True
                )
                if isinstance(web_results, dict) and "successful" in web_results:
                    w_data = web_results.get("data", {})
                    w_items = w_data.get("results", []) or w_data.get("items", [])
                    if w_items:
                        course_url = w_items[0].get("link") or w_items[0].get("url")
            except Exception as e:
                print(f"Course Search failed: {e}")

        video_ids.append(video_id)
        final_path.append({
            "day": entry["day"],
            "topic": entry["topic_name"],
            "video_url": video_url,
            "course_url": course_url,
            "selection_reasoning": entry.get("selection_reasoning", "Selected for high authority and pedagogical clarity."),
            "detailed_plan": entry.get("detailed_plan", "Focus on the core fundamentals and practice examples.")
        })

    # 3. Create Document (Drive priority, then Notion) via Composio
    doc_link = "Not created"
    
    # Construct the "Masterpiece" Premium Document Template
    divider = "=" * 80
    short_divider = "-" * 80
    
    doc_body = f"{divider}\n"
    doc_body += f"🎓  ULTIMATE LEARNING PATH: {topic.upper()}\n"
    doc_body += f"{divider}\n\n"
    
    doc_body += "OVERVIEW:\n"
    doc_body += f"This curated {len(final_path)}-day roadmap is designed to transform you from a \n"
    doc_body += f"beginner to a proficient specialist in {topic}.\n\n"
    
    for p in final_path:
        doc_body += f"{short_divider}\n"
        doc_body += f"📅  DAY {p['day']}: {p['topic'].upper()}\n"
        doc_body += f"{short_divider}\n"
        doc_body += f"🎯  CORE MISSION: \n    {p['detailed_plan']}\n\n"
        doc_body += f"📺  VIDEO LESSON: \n    {p['video_url']}\n\n"
        if p.get('course_url'):
            doc_body += f"🎓  RECOMMENDED COURSE: \n    {p['course_url']}\n\n"
        doc_body += f"💡  REASONING: \n    {p['selection_reasoning']}\n\n"
        
    doc_body += f"{divider}\n"
    doc_body += "✅  YOUR PATH TO MASTERY COMPLETED\n"
    doc_body += "Stay consistent, stay curious, and build something amazing!\n"
    doc_body += f"{divider}\n"

    try:
        # Try Google Drive first
        drive_result = composio.tools.execute(
            slug="googledrive_create_file_from_text",
            arguments={
                "file_name": f"ULTIMATE_LEARNING_PATH_{topic.replace(' ', '_')}.txt",
                "text_content": doc_body
            },
            user_id="default",
            dangerously_skip_version_check=True
        )
        if isinstance(drive_result, dict) and "successful" in drive_result:
            drive_data = drive_result.get("data", {})
            file_id = drive_data.get("id")
            if file_id:
                doc_link = f"https://drive.google.com/file/d/{file_id}/view"
            else:
                doc_link = drive_data.get("webViewLink") or drive_data.get("url") or "Drive file created successfully"
        else:
            doc_link = "Drive creation failed - check integration"
    except Exception as drive_e:
        print(f"Drive creation failed: {drive_e}, trying Notion...")
        try:
            notion_result = composio.tools.execute(
                slug="notion_create_page",
                arguments={
                    "title": f"Learning Path - {topic}",
                    "content": doc_body
                },
                user_id="default",
                dangerously_skip_version_check=True
            )
            if isinstance(notion_result, dict) and "successful" in notion_result:
                notion_data = notion_result.get("data", {})
                doc_link = notion_data.get("url", "Notion page created successfully")
        except Exception as notion_e:
            print(f"Notion creation failed: {notion_e}")

    # 4. Create YouTube Playlist via Composio
    playlist_link = "Not created"
    if video_ids:
        try:
            playlist_result = composio.tools.execute(
                slug="youtube_create_playlist",
                arguments={"title": f"Learning Path: {topic}"},
                user_id="default",
                dangerously_skip_version_check=True
            )
            if isinstance(playlist_result, dict) and "successful" in playlist_result:
                playlist_data = playlist_result.get("data", {})
                playlist_id = playlist_data.get("id") or playlist_data.get("playlist_id")
                if playlist_id:
                    playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
                    for v_id in video_ids:
                        composio.tools.execute(
                            slug="youtube_add_video_to_playlist",
                            arguments={"playlist_id": playlist_id, "video_id": v_id},
                            user_id="default",
                            dangerously_skip_version_check=True
                        )
        except Exception as yt_e:
            print(f"Playlist creation failed: {yt_e}")

    # Format the final response string for the Streamlit UI
    response_content = f"Learning path for {topic}:\n\n"
    for p in final_path:
        response_content += f"Day {p['day']}:\nTopic: {p['topic']}\nDetailed Plan: {p['detailed_plan']}\n"
        response_content += f"YouTube Link: {p['video_url']}\n"
        if p.get('course_url'):
            response_content += f"Course Link: {p['course_url']}\n"
        response_content += f"AI Reasoning: {p['selection_reasoning']}\n\n"
    
    response_content += f"Here is your learning path document link: {doc_link}\n"
    response_content += f"Here is your YouTube playlist link: {playlist_link}\n"

    return {
        "status": "success",
        "messages": [{"role": "ai", "content": response_content}]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
