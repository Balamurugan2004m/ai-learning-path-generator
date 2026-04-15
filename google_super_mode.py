"""
Google Super Mode orchestration.

Implements a deterministic, Gemini-free architecture for:
- Smart task generation
- Time intelligence scheduling
- Feedback and missed-task recovery hooks
- Resource binding
- Progress intelligence
- Execution via Composio MCP meta tools (Google Calendar/Tasks/Drive, optional Gmail)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import re
from typing import Any, Callable, Optional

import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient

DEFAULT_GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY_HERE"


@dataclass
class LearningTask:
    day: int
    title: str
    duration_min: int
    difficulty: str
    kind: str
    resource_query: str
    outcome: str
    start_iso: str = ""
    end_iso: str = ""


class SmartTaskGenerator:
    """Goal -> atomic tasks."""

    def generate(self, goal: str, days: int, sprint_mode: bool) -> list[LearningTask]:
        topic = goal.strip() or "Learning Goal"
        tasks: list[LearningTask] = []
        for day in range(1, days + 1):
            base = 35 if sprint_mode else 30
            tasks.extend(
                [
                    LearningTask(
                        day=day,
                        title=f"Deep concept study ({topic})",
                        duration_min=base + 20,
                        difficulty="hard",
                        kind="study",
                        resource_query=f"{topic} advanced concepts tutorial",
                        outcome="Understand the core concept and write summary notes.",
                    ),
                    LearningTask(
                        day=day,
                        title=f"Build practical mini-task ({topic})",
                        duration_min=base + 25,
                        difficulty="hard",
                        kind="build",
                        resource_query=f"{topic} project walkthrough",
                        outcome="Build one practical artifact and save output.",
                    ),
                    LearningTask(
                        day=day,
                        title=f"Revision and reflection ({topic})",
                        duration_min=base,
                        difficulty="medium",
                        kind="revision",
                        resource_query=f"{topic} recap summary",
                        outcome="Capture lessons, blockers, and next action.",
                    ),
                ]
            )
        return tasks


class TimeIntelligenceEngine:
    """Morning hard tasks; evening revision tasks."""

    def schedule(self, tasks: list[LearningTask], start_date: Optional[datetime] = None) -> list[LearningTask]:
        anchor = (start_date or datetime.now()).replace(hour=8, minute=30, second=0, microsecond=0)
        for t in tasks:
            day_date = anchor + timedelta(days=t.day - 1)
            if t.kind == "revision":
                start = day_date.replace(hour=19, minute=0)
            elif t.kind == "build":
                start = day_date.replace(hour=11, minute=0)
            else:
                start = day_date.replace(hour=9, minute=0)
            end = start + timedelta(minutes=t.duration_min)
            t.start_iso = start.isoformat()
            t.end_iso = end.isoformat()
        return tasks


class FeedbackLoopEngine:
    """Basic adaptation hooks."""

    def adapt(self, tasks: list[LearningTask], skipped_count: int = 0) -> list[LearningTask]:
        # If user is skipping often, reduce duration slightly to lower overload.
        if skipped_count <= 1:
            return tasks
        for t in tasks:
            t.duration_min = max(20, int(t.duration_min * 0.85))
        return tasks


class MissedTaskRecoverySystem:
    """Compress missed tasks into summary-focused recovery."""

    def recover(self, tasks: list[LearningTask], missed_task_ids: Optional[set[str]] = None) -> list[LearningTask]:
        # Placeholder for future persistent tracking. Keeps architecture in place.
        _ = missed_task_ids
        return tasks


class ResourceBindingLayer:
    def bind(self, tasks: list[LearningTask]) -> list[LearningTask]:
        # Queries/outcomes are already attached by generator.
        return tasks


class ProgressIntelligence:
    def summarize(self, tasks: list[LearningTask]) -> dict[str, Any]:
        total_minutes = sum(t.duration_min for t in tasks)
        hard_count = sum(1 for t in tasks if t.difficulty == "hard")
        return {
            "consistency_score": 100,  # deterministic bootstrap value
            "focus_hours": round(total_minutes / 60.0, 1),
            "hard_task_ratio": round(hard_count / max(1, len(tasks)), 2),
            "insight": "You are scheduled for hardest tasks in the morning and revision in the evening.",
        }


class GoogleSuperExecutor:
    """Execution layer using Composio meta tools."""

    def __init__(
        self,
        api_key: str,
        user_id: str,
        progress: Optional[Callable[[str], None]] = None,
        google_api_key: Optional[str] = None,
    ):
        self.api_key = api_key
        self.user_id = user_id
        self.progress = progress
        self.google_api_key = (google_api_key or os.getenv("GOOGLE_API_KEY") or DEFAULT_GOOGLE_API_KEY).strip()
        self.session_id = ""
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: dict[str, Any] = {}

    def _build_fallback_plan_text(self, goal: str, tasks: list[LearningTask], days: int) -> tuple[str, str]:
        lines = [f"## Detailed Plan: {goal}", ""]
        for day in range(1, days + 1):
            lines.append(f"### Day {day}")
            lines.append("- Objective:")
            lines.append(f"  - Complete structured learning tasks for Day {day}.")
            lines.append("- Tasks:")
            for t in [x for x in tasks if x.day == day]:
                lines.append(f"  - **{t.title}** ({t.duration_min} min)")
                lines.append(f"    - Outcome: {t.outcome}")
                lines.append(f"    - Resource search: `{t.resource_query}`")
            lines.append("- Checkpoint:")
            lines.append("  - Summarize what you learned in 3-5 bullet points.")
            lines.append("")
        detailed = "\n".join(lines).strip()
        summary = (
            f"Goal: {goal}\n"
            f"Duration: {days} days\n"
            "Structure: Morning deep study, midday practical build, evening revision.\n"
            f"Total tasks: {len(tasks)}\n"
            f"Estimated effort: {round(sum(t.duration_min for t in tasks)/60.0, 1)} hours."
        )
        return detailed, summary

    def _generate_plan_with_gemini(self, goal: str, tasks: list[LearningTask], days: int) -> tuple[str, str]:
        """
        Returns (detailed_plan_text, summary_for_drive_doc).
        Falls back deterministically if Gemini is unavailable.
        """
        fallback_detailed, fallback_summary = self._build_fallback_plan_text(goal, tasks, days)
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.google_api_key)
            task_rows = "\n".join(
                f"- Day {t.day} | {t.title} | {t.duration_min} min | {t.start_iso} -> {t.end_iso} | {t.outcome}"
                for t in tasks
            )
            prompt = f"""
You are an expert learning coach.
Goal: {goal}
Duration: {days} days
Schedule:
{task_rows}

Return ONLY valid JSON with keys:
- detailed_plan: markdown, rich day-wise plan (descriptive and actionable)
- summary_for_document: concise summary (max 220 words)

For `detailed_plan`, use EXACT structure:
1) Start with: `## Detailed Plan: <goal>`
2) For each day, add heading: `### Day N`
3) Under each day include these bullet sections:
   - Objective
   - Topics to Cover (3-5 bullets)
   - Hands-on Tasks (3-5 bullets)
   - Deliverable
   - Quick Self-Assessment (3 checklist bullets using `- [ ]`)
4) Keep each bullet concrete and beginner-friendly.
5) Do not include code fences.
"""
            models = [
                os.getenv("GOOGLE_MODEL", "").strip() or "gemini-1.5-flash",
                "gemini-1.5-flash-latest",
                "gemini-2.0-flash",
            ]
            tried: set[str] = set()
            for model_name in models:
                if not model_name or model_name in tried:
                    continue
                tried.add(model_name)
                try:
                    model = genai.GenerativeModel(model_name)
                    resp = model.generate_content(prompt)
                    text = (resp.text or "").strip()
                    if "```json" in text:
                        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
                    elif "```" in text:
                        text = text.split("```", 1)[1].split("```", 1)[0].strip()
                    obj = json.loads(text)
                    detailed = (obj.get("detailed_plan") or "").strip()
                    summary = (obj.get("summary_for_document") or "").strip()
                    if detailed and summary:
                        return detailed, summary
                except Exception:
                    continue
        except Exception:
            pass
        return fallback_detailed, fallback_summary

    async def _create_tool_router_session(self, toolkits: list[str]) -> dict:
        url = "https://backend.composio.dev/api/v3.1/tool_router/session"
        payload = {
            "user_id": self.user_id,
            "toolkits": {"enable": toolkits},
            "manage_connections": {"enable": True, "enable_wait_for_connections": False},
            "workbench": {"enable": False, "enable_proxy_execution": False},
        }
        async with httpx.AsyncClient(timeout=30.0) as c:
            for header_name in ("x-api-key", "x-user-api-key"):
                r = await c.post(url, json=payload, headers={header_name: self.api_key})
                if r.status_code == 401:
                    continue
                r.raise_for_status()
                return r.json()
        raise ValueError("Composio authorization failed for Tool Router session creation.")

    async def initialize(self) -> None:
        if self.progress:
            self.progress("Initializing Google Super toolkit session...")
        s = await self._create_tool_router_session(
            ["googlecalendar", "googletasks", "googledrive", "gmail", "youtube"]
        )
        mcp_url = (s.get("mcp") or {}).get("url")
        if not mcp_url:
            raise ValueError("Composio session did not return mcp.url")
        self.session_id = s.get("session_id", "")
        self.client = MultiServerMCPClient(
            {"composio": {"transport": "streamable_http", "url": mcp_url, "headers": {"x-api-key": self.api_key}}}
        )
        fetched = await self.client.get_tools()
        self.tools = {t.name: t for t in fetched}

    async def _search_slugs(self, query: str) -> tuple[list[str], list[dict]]:
        raw = await self.tools["COMPOSIO_SEARCH_TOOLS"].ainvoke({"query": query})
        obj = json.loads(raw) if isinstance(raw, str) else (raw or {})
        data = obj.get("data") or {}
        if not self.session_id:
            self.session_id = data.get("session_id") or data.get("sessionId") or self.session_id
        results = data.get("results") or []
        slugs: list[str] = []
        for r in results:
            slugs.extend(r.get("primary_tool_slugs") or [])
            slugs.extend(r.get("related_tool_slugs") or [])
        # preserve order / uniq
        uniq: list[str] = []
        for s in slugs:
            if s not in uniq:
                uniq.append(s)
        return uniq, data.get("toolkit_connection_statuses") or []

    async def _ensure_connections(self, statuses: list[dict], required: set[str]) -> Optional[str]:
        missing = sorted(
            {
                s.get("toolkit")
                for s in statuses
                if s.get("toolkit") in required and s.get("has_active_connection") is False
            }
        )
        if not missing:
            return None
        mraw = await self.tools["COMPOSIO_MANAGE_CONNECTIONS"].ainvoke({"toolkits": missing})
        mobj = json.loads(mraw) if isinstance(mraw, str) else (mraw or {})
        results = ((mobj.get("data") or {}).get("results")) or {}
        links = []
        for tk in missing:
            lk = ((results.get(tk) or {}).get("redirect_url")) or ""
            if lk:
                links.append(f"- Connect {tk}: {lk}")
        return "Google Super mode needs connections:\n" + "\n".join(links)

    async def _exec_one(self, tool_slug: str, arguments: dict, step: str) -> dict:
        payload = {
            "session_id": self.session_id,
            "current_step": step,
            "current_step_metric": "0/1",
            "tools": [{"tool_slug": tool_slug, "arguments": arguments}],
            "sync_response_to_workbench": False,
            "memory": {},
            "thought": f"Execute {tool_slug}",
        }
        raw = await self.tools["COMPOSIO_MULTI_EXECUTE_TOOL"].ainvoke(payload)
        obj = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return obj

    @staticmethod
    def _first_response_data(obj: dict) -> dict:
        data = obj.get("data") or {}
        results = data.get("results") or []
        if not results:
            return {}
        resp = (results[0] or {}).get("response") or {}
        if resp.get("successful") is True:
            return resp.get("data") or {}
        return {}

    async def execute(self, goal: str, tasks: list[LearningTask], progress_summary: dict[str, Any]) -> str:
        if self.progress:
            self.progress("Discovering Google toolkit actions...")
        task_slugs, task_status = await self._search_slugs("google tasks create task with due date")
        cal_slugs, cal_status = await self._search_slugs("google calendar create event")
        drive_slugs, drive_status = await self._search_slugs("google drive create file from text")
        maybe_msg = await self._ensure_connections(
            task_status + cal_status + drive_status, {"googletasks", "googlecalendar", "googledrive"}
        )
        if maybe_msg:
            return maybe_msg

        task_slug = next((s for s in task_slugs if "INSERT_TASK" in s), "") or next(
            (s for s in task_slugs if "CREATE" in s and "TASK" in s), ""
        )
        list_tasklists_slug = next((s for s in task_slugs if "LIST_TASK_LISTS" in s), "")
        create_tasklist_slug = next((s for s in task_slugs if "CREATE_TASK_LIST" in s), "")
        cal_slug = next((s for s in cal_slugs if "CREATE" in s and "EVENT" in s), "")
        drive_slug = next((s for s in drive_slugs if "CREATE" in s and "FILE" in s), "")

        if not task_slug or not cal_slug or not drive_slug:
            return "Could not discover required Google toolkit actions (Tasks/Calendar/Drive)."

        # Resolve a task list id (required by GOOGLETASKS_INSERT_TASK).
        tasklist_id = ""
        if list_tasklists_slug:
            lres = await self._exec_one(list_tasklists_slug, {}, "GOOGLETASKS_LIST")
            ldata = self._first_response_data(lres)
            items = ldata.get("items") or []
            if items and isinstance(items[0], dict):
                tasklist_id = items[0].get("id") or ""
        if not tasklist_id and create_tasklist_slug:
            cres = await self._exec_one(
                create_tasklist_slug, {"tasklist_title": "AI Learning Path Tasks"}, "GOOGLETASKS_CREATE_LIST"
            )
            cdata = self._first_response_data(cres)
            tasklist_id = cdata.get("id") or ""
        if not tasklist_id:
            return "Google Tasks is connected but no task list could be resolved. Please create one manually and retry."

        if self.progress:
            self.progress("Pushing actionable tasks to Google Tasks and Calendar...")

        lines = [f"Goal: {goal}", "", "Today's Learning Schedule", ""]
        task_count = 0
        event_count = 0
        first_task_link = ""
        first_event_link = ""
        for t in tasks:
            # Create Google Task
            t_args = {
                "title": t.title[:200],
                "notes": f"{t.outcome}\nResource query: {t.resource_query}",
                "due": t.end_iso,
                "tasklist_id": tasklist_id,
            }
            tres = await self._exec_one(task_slug, t_args, "GOOGLETASKS_CREATE")
            if ((tres.get("data") or {}).get("success_count") or 0) > 0:
                task_count += 1
            if not first_task_link:
                t_data = self._first_response_data(tres)
                first_task_link = (
                    t_data.get("webViewLink")
                    or t_data.get("selfLink")
                    or t_data.get("link")
                    or ""
                )

            # Create Calendar event
            c_args = {
                "summary": t.title[:200],
                "description": f"{t.outcome}\nResource query: {t.resource_query}",
                "start_datetime": t.start_iso,
                "end_datetime": t.end_iso,
            }
            cres = await self._exec_one(cal_slug, c_args, "GOOGLECALENDAR_CREATE")
            if ((cres.get("data") or {}).get("success_count") or 0) > 0:
                event_count += 1
            if not first_event_link:
                c_data = self._first_response_data(cres)
                first_event_link = (
                    c_data.get("htmlLink")
                    or c_data.get("link")
                    or ""
                )

            lines.append(
                f"- Day {t.day}: {t.title} ({t.duration_min} min)"
            )
            lines.append(f"  Time: {t.start_iso} -> {t.end_iso}")
            lines.append(f"  Outcome: {t.outcome}")
            lines.append(f"  Resource: {t.resource_query}")
            lines.append("")

        total = len(tasks)
        lines.append("Sync Status")
        lines.append(f"- Planned tasks: {total}")
        lines.append(f"- Synced to Google Tasks: {task_count}/{total}")
        lines.append(f"- Synced to Google Calendar: {event_count}/{total}")
        lines.append("")
        lines.append("Quick Access")
        lines.append(f"- Google Tasks: {first_task_link or 'https://mail.google.com/tasks/canvas'}")
        lines.append(f"- Google Calendar: {first_event_link or 'https://calendar.google.com/calendar/u/0/r'}")
        lines.append("")
        lines.append("Progress Intelligence")
        lines.append(f"- Consistency score: {progress_summary.get('consistency_score')}")
        lines.append(f"- Focus hours: {progress_summary.get('focus_hours')}")
        lines.append(f"- Skill progression insight: {progress_summary.get('insight')}")
        lines.append("")

        if self.progress:
            self.progress("Generating detailed AI plan...")
        days = max((t.day for t in tasks), default=1)
        detailed_plan, summary_for_doc = self._generate_plan_with_gemini(
            goal=goal,
            tasks=tasks,
            days=days,
        )

        if self.progress:
            self.progress("Creating summary document in Google Drive...")
        dres = await self._exec_one(
            drive_slug,
            {
                "file_name": f"Learning Plan Summary - {goal}"[:180],
                "text_content": summary_for_doc,
                "mime_type": "application/vnd.google-apps.document",
            },
            "GOOGLEDRIVE_CREATE_SUMMARY_DOC",
        )
        ddata = self._first_response_data(dres)
        doc_url = ddata.get("display_url") or (
            f"https://docs.google.com/document/d/{ddata.get('id')}/edit" if ddata.get("id") else ""
        )

        lines.append("Summary Document")
        lines.append(f"- Google Drive summary doc: {doc_url or 'not created'}")
        lines.append("")
        lines.append("Detailed AI Plan")
        lines.append(detailed_plan.strip())

        return "\n".join(lines)


async def run_google_super_mode(
    goal: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    api_key = (os.getenv("COMPOSIO_API_KEY") or "").strip()
    user_id = (os.getenv("COMPOSIO_USER_ID") or "").strip()
    if not api_key or not user_id:
        raise ValueError("Google Super mode requires COMPOSIO_API_KEY and COMPOSIO_USER_ID.")

    # Runtime knobs (no Gemini needed)
    sprint_mode = (os.getenv("GOOGLE_SUPER_SPRINT_MODE", "false").strip().lower() in ("1", "true", "yes"))
    days_match = re.search(r"\b(\d{1,2})\s*(?:day|days)\b", (goal or "").lower())
    days = int(days_match.group(1)) if days_match else int(os.getenv("GOOGLE_SUPER_DEFAULT_DAYS", "7"))
    days = max(1, min(days, 30))

    generator = SmartTaskGenerator()
    scheduler = TimeIntelligenceEngine()
    feedback = FeedbackLoopEngine()
    recovery = MissedTaskRecoverySystem()
    binder = ResourceBindingLayer()
    progress = ProgressIntelligence()

    tasks = generator.generate(goal, days=days, sprint_mode=sprint_mode)
    tasks = feedback.adapt(tasks, skipped_count=0)
    tasks = recovery.recover(tasks, missed_task_ids=None)
    tasks = binder.bind(tasks)
    tasks = scheduler.schedule(tasks)
    summary = progress.summarize(tasks)

    google_api_key = (os.getenv("GOOGLE_API_KEY") or DEFAULT_GOOGLE_API_KEY).strip()
    executor = GoogleSuperExecutor(
        api_key=api_key,
        user_id=user_id,
        progress=progress_callback,
        google_api_key=google_api_key,
    )
    await executor.initialize()
    content = await executor.execute(goal=goal, tasks=tasks, progress_summary=summary)
    if progress_callback:
        progress_callback("Google Super flow complete.")
    return {"status": "success", "messages": [{"role": "ai", "content": content}], "metadata": {"days": days, "sprint_mode": sprint_mode}}
