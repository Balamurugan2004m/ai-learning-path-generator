import os
from typing import List, Dict, Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import json
import time
import urllib.parse
import httpx

# Load environment variables
load_dotenv()

app = FastAPI(title="AI Learning Path Generator API")

# Allow CORS for local Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google API key (from env; placeholder if missing)
DEFAULT_GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY") or "YOUR_GOOGLE_API_KEY_HERE").strip()

# High-quality fallback video pool – used only if YouTube Data API is unavailable
FALLBACK_VIDEO_POOL = [
    "kqtD5dpn9C8",  # Python full course – freeCodeCamp
    "rfscVS0vtbw",  # Python for Beginners
    "HGOBQqn636M",  # JavaScript full course
    "8nM6p-CqNn0",  # React full course
    "l9AZmHafAlM",  # Machine Learning crash course
    "ua-CiDNNj30",  # SQL full course
    "pTB0EiLXUC8",  # Data Science
    "aircAruvnKk",  # Neural Networks
    "Qqca-p3oSCg",  # HTML/CSS crash course
    "SWYqp7iY_Tc",  # Docker tutorial
]

YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"


class MCPRequest(BaseModel):
    action: str
    input: Dict[str, Any]


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "3.0.0"}


@app.post("/mcp/execute")
async def execute_mcp(req: MCPRequest):
    """Main entry point for learning path generation."""
    print(f"DEBUG: Executing action '{req.action}'")
    if req.action == "generate_learning_path":
        try:
            return await generate_learning_path(req.input)
        except HTTPException:
            raise
        except Exception as e:
            print(f"ERROR in generate_learning_path: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")


# ─────────────────────────────────────────────────────────────────────────────
# YouTube Data API v3 helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _search_youtube_video(query: str, api_key: str) -> Optional[str]:
    """
    Search YouTube Data API v3 for a single video matching the query.
    Returns the video ID or None on failure.
    """
    try:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 5,
            "safeSearch": "moderate",
            "relevanceLanguage": "en",
            "key": api_key,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(YOUTUBE_SEARCH_API, params=params)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    video_id = items[0].get("id", {}).get("videoId")
                    print(f"DEBUG: YouTube search '{query}' → {video_id}")
                    return video_id
            else:
                print(f"DEBUG: YouTube API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"DEBUG: YouTube search failed for '{query}': {e}")
    return None


def _build_youtube_playlist_url(video_ids: List[str]) -> Optional[str]:
    """
    Build a YouTube watch_videos URL that acts as a temporary playlist
    from a list of video IDs. Returns None if no IDs are available.
    Works without authentication — creates a session-based playlist.
    """
    valid_ids = [vid for vid in video_ids if vid]
    if not valid_ids:
        return None
    ids_param = ",".join(valid_ids)
    return f"https://www.youtube.com/watch_videos?video_ids={ids_param}"


def _build_youtube_search_url(query: str) -> str:
    """Fallback: build a YouTube search URL."""
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"


# ─────────────────────────────────────────────────────────────────────────────
# HTML document builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_html_document(topic: str, final_path: List[Dict], playlist_url: Optional[str]) -> str:
    """Generate a rich, print-ready HTML study plan document."""

    days_html = ""
    for p in final_path:
        plan_text = p["detailed_plan"].replace("\n", "<br>")
        video_html = (
            f'<a href="{p["video_url"]}" target="_blank">▶ Watch Video — Day {p["day"]}</a>'
            if "youtube.com/watch?v=" in p["video_url"]
            else f'<a href="{p["video_url"]}" target="_blank">🔍 Search YouTube for this topic</a>'
        )
        days_html += f"""
        <div class="day-card">
            <div class="day-header">
                <span class="day-badge">Day {p['day']}</span>
                <h2>{p['topic']}</h2>
            </div>
            <div class="day-body">
                <div class="section">
                    <h3>📋 Study Plan</h3>
                    <p>{plan_text}</p>
                </div>
                <div class="section links-row">
                    <div class="link-card youtube">
                        <span class="link-icon">📺</span>
                        <div>
                            <div class="link-label">Video Resource</div>
                            {video_html}
                        </div>
                    </div>
                    <div class="link-card course">
                        <span class="link-icon">🎓</span>
                        <div>
                            <div class="link-label">Structured Course</div>
                            <a href="{p['course_url']}" target="_blank">Browse matching courses</a>
                        </div>
                    </div>
                </div>
                <div class="reasoning">
                    <strong>💡 Why this?</strong> {p['selection_reasoning']}
                </div>
            </div>
        </div>
        """

    playlist_section = ""
    if playlist_url:
        playlist_section = f"""
        <div class="playlist-banner">
            <span>🎵</span>
            <div>
                <strong>Your YouTube Playlist is Ready!</strong><br>
                <a href="{playlist_url}" target="_blank">{playlist_url}</a>
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Learning Path: {topic}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', system-ui, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    padding: 2rem 1rem;
  }}
  .container {{ max-width: 860px; margin: 0 auto; }}

  .hero {{
    background: linear-gradient(135deg, #1e3a5f 0%, #1e4080 50%, #2d1b69 100%);
    border-radius: 20px;
    padding: 3rem 2.5rem;
    text-align: center;
    margin-bottom: 2.5rem;
    border: 1px solid rgba(96, 165, 250, 0.25);
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  }}
  .hero .emoji {{ font-size: 3rem; display: block; margin-bottom: 1rem; }}
  .hero h1 {{ font-size: 2rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; }}
  .hero .subtitle {{
    font-size: 1rem; color: #94a3b8; margin-bottom: 1.5rem;
  }}
  .hero .meta-badges {{ display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }}
  .badge {{
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 0.35rem 0.9rem;
    font-size: 0.8rem;
    color: #cbd5e1;
    font-weight: 500;
  }}

  .playlist-banner {{
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
    border-radius: 14px;
    padding: 1.25rem 1.75rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    margin-bottom: 2rem;
    font-size: 1.5rem;
    box-shadow: 0 8px 24px rgba(220, 38, 38, 0.35);
  }}
  .playlist-banner strong {{ color: #fff; }}
  .playlist-banner a {{ color: #fca5a5; word-break: break-all; font-size: 0.85rem; }}

  .day-card {{
    background: #1e293b;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    overflow: hidden;
    border: 1px solid #334155;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    transition: transform 0.2s;
  }}
  .day-card:hover {{ transform: translateY(-2px); }}
  .day-header {{
    background: linear-gradient(90deg, #1d4ed8 0%, #4f46e5 100%);
    padding: 1.25rem 1.75rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }}
  .day-badge {{
    background: rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 0.3rem 0.9rem;
    font-size: 0.78rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .day-header h2 {{ font-size: 1.05rem; font-weight: 700; color: #fff; }}

  .day-body {{ padding: 1.5rem 1.75rem; }}
  .section {{ margin-bottom: 1.25rem; }}
  .section h3 {{ font-size: 0.85rem; font-weight: 600; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.06em; }}
  .section p {{ color: #cbd5e1; line-height: 1.7; font-size: 0.92rem; }}

  .links-row {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .link-card {{
    flex: 1;
    min-width: 200px;
    background: #0f172a;
    border-radius: 10px;
    padding: 1rem;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    border: 1px solid #334155;
  }}
  .link-card.youtube {{ border-color: #dc262650; }}
  .link-card.course {{ border-color: #16a34a50; }}
  .link-icon {{ font-size: 1.5rem; flex-shrink: 0; }}
  .link-label {{ font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.3rem; }}
  .link-card a {{ color: #60a5fa; font-size: 0.88rem; font-weight: 500; text-decoration: none; }}
  .link-card a:hover {{ text-decoration: underline; }}

  .reasoning {{
    background: #0f172a;
    border-left: 3px solid #f59e0b;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #94a3b8;
    line-height: 1.6;
  }}
  .reasoning strong {{ color: #fbbf24; }}

  .footer {{
    text-align: center;
    padding: 2.5rem 1rem;
    color: #475569;
    font-size: 0.82rem;
  }}
  .footer .cta {{
    font-size: 1.1rem;
    color: #60a5fa;
    font-weight: 700;
    display: block;
    margin-bottom: 0.5rem;
  }}

  @media print {{
    body {{ background: #fff; color: #000; }}
    .day-card {{ break-inside: avoid; box-shadow: none; border-color: #ccc; }}
    .hero {{ background: #1e3a8a; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <span class="emoji">🎯</span>
    <h1>Ultimate Learning Path</h1>
    <p class="subtitle">{topic}</p>
    <div class="meta-badges">
      <span class="badge">📅 {len(final_path)} Days</span>
      <span class="badge">🚀 Beginner → Intermediate</span>
      <span class="badge">🤖 AI-Generated Curriculum</span>
    </div>
  </div>

  {playlist_section}

  {days_html}

  <div class="footer">
    <span class="cta">✅ Your Path to Mastery is Complete!</span>
    Stay consistent, practice daily, and build something amazing.
    <br>Generated by AI Learning Path Generator
  </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Core learning path orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def generate_learning_path(input_data: Dict[str, Any]):
    """
    Orchestrates:
      1. Gemini curriculum planning
      2. YouTube Data API v3 video search → real video IDs
      3. YouTube watch_videos playlist URL
      4. Beautiful HTML study plan document
    """
    topic = input_data.get("topic", "").strip()
    google_api_key = input_data.get("google_api_key") or DEFAULT_GOOGLE_API_KEY

    if not topic:
        raise HTTPException(status_code=400, detail="Missing 'topic' in input")

    # ── Step 1: Gemini curriculum planning ───────────────────────────────────
    plan = None
    if google_api_key:
        try:
            genai.configure(api_key=google_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            planning_prompt = f"""
You are an elite Senior Curriculum Designer. Create a comprehensive, deeply structured day-wise learning path for: "{topic}".

Plan exactly 7 days of progressive learning from beginner to intermediate.

For each day, provide a JSON object with these EXACT keys:
1. "day": integer day number (1-7)
2. "topic_name": A clear, professional lesson title (max 60 chars)
3. "detailed_plan": A 4-6 sentence professional breakdown covering: core mission, key sub-topics, learning objectives, and a practical exercise. Use bullet points with \\n for structure.
4. "selection_reasoning": 1-2 sentences on why this day's resources are the best match.
5. "primary_search_query": A specific YouTube search query (max 60 chars, English).
6. "fallback_search_query": A broad YouTube search query (max 50 chars, English).
7. "course_search_query": A search term for Coursera, Udemy, or edX.

Return ONLY a valid JSON array. No markdown, no explanation. Just the JSON array.
"""
            for attempt in range(3):
                try:
                    response = model.generate_content(planning_prompt)
                    raw = response.text.strip()
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0].strip()

                    parsed = json.loads(raw)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        plan = parsed
                        print(f"DEBUG: Gemini produced {len(plan)}-day plan.")
                        break
                except json.JSONDecodeError as je:
                    print(f"DEBUG: JSON parse failed attempt {attempt+1}: {je}")
                    if attempt == 2:
                        raise
                except Exception as api_e:
                    print(f"DEBUG: Gemini attempt {attempt+1} failed: {api_e}")
                    if "429" in str(api_e) and attempt < 2:
                        time.sleep(4 * (attempt + 1))
                        continue
                    if attempt == 2:
                        raise api_e
        except Exception as e:
            print(f"ERROR: Gemini planning failed: {e}. Falling back to built-in plan.")

    if not plan:
        plan = _build_fallback_plan(topic)
        print("DEBUG: Using built-in fallback plan.")

    # ── Step 2: YouTube Data API v3 – search for real video IDs ─────────────
    final_path: List[Dict] = []
    video_ids: List[str] = []
    used_video_ids: set = set()

    for i, entry in enumerate(plan):
        day_num = entry.get("day", i + 1)
        topic_name = entry.get("topic_name", f"Day {day_num} – {topic}")
        p_query = entry.get("primary_search_query") or entry.get("search_query", "")
        f_query = entry.get("fallback_search_query", "")
        c_query = entry.get("course_search_query", "")

        # Try primary query first, then fallback
        video_id = None
        for query in [q for q in [p_query, f_query] if q]:
            vid = await _search_youtube_video(query, google_api_key)
            if vid and vid not in used_video_ids:
                video_id = vid
                used_video_ids.add(vid)
                break

        # Pool fallback if YouTube API didn't return usable ID
        if not video_id:
            fallback_vid = FALLBACK_VIDEO_POOL[i % len(FALLBACK_VIDEO_POOL)]
            if fallback_vid not in used_video_ids:
                video_id = fallback_vid
                used_video_ids.add(video_id)
            else:
                # Last resort: search URL
                video_id = None

        if video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            video_ids.append(video_id)
        else:
            video_url = _build_youtube_search_url(p_query or f_query or topic_name)

        # Build Coursera search URL
        course_url = (
            f"https://www.coursera.org/search?query={urllib.parse.quote_plus(c_query)}"
            if c_query
            else f"https://www.udemy.com/courses/search/?q={urllib.parse.quote_plus(topic_name)}"
        )

        final_path.append({
            "day": day_num,
            "topic": topic_name,
            "video_url": video_url,
            "course_url": course_url,
            "selection_reasoning": entry.get(
                "selection_reasoning",
                "Selected for high authority, pedagogical clarity, and topic relevance.",
            ),
            "detailed_plan": entry.get(
                "detailed_plan",
                f"Focus on the core fundamentals of {topic_name} and practice examples.",
            ),
        })

    # ── Step 3: Build YouTube playlist URL ───────────────────────────────────
    playlist_url = _build_youtube_playlist_url(video_ids)
    print(f"DEBUG: Playlist URL → {playlist_url}")

    # ── Step 4: Build HTML study plan document ───────────────────────────────
    html_doc = _build_html_document(topic, final_path, playlist_url)

    # ── Step 5: Format Streamlit-friendly Markdown response ──────────────────
    days_str = len(final_path)
    response_content = f"## 🎯 Your {days_str}-Day Learning Path: **{topic}**\n\n"

    for p in final_path:
        response_content += "---\n"
        response_content += f"### 📅 Day {p['day']}: {p['topic']}\n\n"
        response_content += f"**📋 Study Plan:**\n{p['detailed_plan']}\n\n"
        if "youtube.com/watch?v=" in p["video_url"]:
            response_content += f"**📺 Video:** [Watch on YouTube]({p['video_url']})\n\n"
        else:
            response_content += f"**📺 Video:** [Search YouTube for this topic]({p['video_url']})\n\n"
        response_content += f"**🎓 Course:** [Browse matching courses]({p['course_url']})\n\n"
        response_content += f"**💡 Why this?** {p['selection_reasoning']}\n\n"

    response_content += "---\n"
    response_content += f"### ✅ Your {days_str}-Day Path to Master **{topic}** is Ready!\n"
    response_content += "_Stay consistent, practice daily, and you'll reach your goal!_\n"

    return {
        "status": "success",
        "messages": [{"role": "ai", "content": response_content}],
        "metadata": {
            "topic": topic,
            "days": days_str,
            "playlist_url": playlist_url,
            "html_doc": html_doc,
            "video_ids": video_ids,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback curriculum plan
# ─────────────────────────────────────────────────────────────────────────────

def _build_fallback_plan(topic: str) -> list:
    """High-quality generic 7-day plan used when Gemini is unavailable."""
    template = [
        (
            "Foundations & Environment Setup",
            f"**Today's Mission**: Establish a solid workspace and understand the fundamentals of {topic}.\n"
            f"- **Key Sub-Topics**: Installation, workspace setup, core syntax, basic concepts.\n"
            f"- **Learning Objectives**: Write and execute your first {topic} programs confidently.\n"
            f"- **Practical Exercise**: Build a 'Hello World' project that demonstrates the basic workflow.",
            f"{topic} beginner tutorial for absolute beginners",
            f"{topic} introduction basics",
            f"Introduction to {topic} beginner course",
        ),
        (
            "Core Concepts & Fundamentals",
            f"**Today's Mission**: Master the building blocks that power every {topic} application.\n"
            f"- **Key Sub-Topics**: Data types, variables, operators, and expressions.\n"
            f"- **Learning Objectives**: Correctly use core data structures and operations.\n"
            f"- **Practical Exercise**: Create a small utility program that processes user input.",
            f"{topic} core concepts explained tutorial",
            f"{topic} fundamentals guide",
            f"{topic} fundamentals online course",
        ),
        (
            "Control Flow & Logic",
            f"**Today's Mission**: Control the execution path of your {topic} programs.\n"
            f"- **Key Sub-Topics**: Conditionals (if/else), loops (for/while), boolean logic.\n"
            f"- **Learning Objectives**: Write programs that make smart decisions based on dynamic inputs.\n"
            f"- **Practical Exercise**: Build a command-line quiz or calculator app.",
            f"{topic} control flow conditionals loops tutorial",
            f"{topic} if else loops",
            f"{topic} control flow course",
        ),
        (
            "Functions & Modular Design",
            f"**Today's Mission**: Organize your code into clean, reusable functions and modules.\n"
            f"- **Key Sub-Topics**: Function definition, parameters, return values, scope, error handling.\n"
            f"- **Learning Objectives**: Write modular, professional-grade code that is testable.\n"
            f"- **Practical Exercise**: Refactor previous exercises into a function-driven library.",
            f"{topic} functions modules tutorial",
            f"{topic} functions reusable code",
            f"{topic} functions and modules course",
        ),
        (
            "Data Structures & Collections",
            f"**Today's Mission**: Master how to store, retrieve, and manipulate collections of data.\n"
            f"- **Key Sub-Topics**: Arrays/Lists, Dictionaries/Maps, Sets, and iteration patterns.\n"
            f"- **Learning Objectives**: Efficiently manage, filter, and transform datasets.\n"
            f"- **Practical Exercise**: Build a dynamic task manager or inventory tracker.",
            f"{topic} data structures arrays lists dictionaries",
            f"{topic} collections data structures",
            f"{topic} data structures course",
        ),
        (
            "Real-World Integration & APIs",
            f"**Today's Mission**: Connect your {topic} skills to the outside world via APIs and files.\n"
            f"- **Key Sub-Topics**: File I/O, HTTP requests, JSON parsing, third-party libraries.\n"
            f"- **Learning Objectives**: Build {topic} apps that communicate with external services.\n"
            f"- **Practical Exercise**: Create a weather app or data fetcher using a public API.",
            f"{topic} API integration tutorial project",
            f"{topic} working with APIs",
            f"{topic} APIs and integration course",
        ),
        (
            "Capstone Project & Best Practices",
            f"**Today's Mission**: Apply everything learned to build a complete, portfolio-worthy project.\n"
            f"- **Key Sub-Topics**: Project architecture, code review, testing, documentation.\n"
            f"- **Learning Objectives**: Deliver a fully functional, well-documented {topic} project.\n"
            f"- **Practical Exercise**: Build a final project that demonstrates end-to-end {topic} skills.",
            f"{topic} capstone project tutorial build",
            f"{topic} final project complete",
            f"{topic} project-based course",
        ),
    ]

    return [
        {
            "day": i + 1,
            "topic_name": t[0],
            "detailed_plan": t[1],
            "primary_search_query": t[2],
            "fallback_search_query": t[3],
            "course_search_query": t[4],
            "selection_reasoning": (
                f"This resource provides structured, authority-grade content for {t[0].lower()}, "
                f"making it the ideal match for Day {i+1} of your {topic} journey."
            ),
        }
        for i, t in enumerate(template)
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
