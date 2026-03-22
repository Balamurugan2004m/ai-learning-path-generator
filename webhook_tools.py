"""
Custom LangChain tools that call Pipedream webhooks to create Drive documents and YouTube playlists.
Your Pipedream workflows must accept the payload format below and return the expected JSON.
"""
import json
from typing import Optional

import httpx
from langchain_core.tools import tool


def _post_webhook(url: str, payload: dict, timeout: float = 60.0) -> dict:
    """POST JSON to webhook URL; return parsed JSON or raise."""
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            data = {"success": False, "error": r.text}
        return data


def _get_drive_webhook_url() -> Optional[str]:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("SECONDARY_WEBHOOK_URL")
    if not url or not url.strip():
        return None
    if (os.getenv("SECONDARY_WEBHOOK_TYPE") or "drive").strip().lower() != "drive":
        return None
    return url.strip()


def _get_youtube_webhook_url() -> Optional[str]:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("YOUTUBE_WEBHOOK_URL")
    if not url or not url.strip():
        return None
    return url.strip()


@tool
def create_drive_document(title: str, content: str) -> str:
    """
    Create a new Google Drive document with the given title and content (markdown or plain text).
    Use this to save the day-wise learning path document. Returns the document URL or an error message.
    """
    url = _get_drive_webhook_url()
    if not url:
        return "Error: Drive webhook not configured. Set SECONDARY_WEBHOOK_URL and SECONDARY_WEBHOOK_TYPE=drive in .env"
    try:
        payload = {"action": "create_document", "title": title, "content": content}
        data = _post_webhook(url, payload)
        # Accept both "url" and "document_url" in response
        link = data.get("document_url") or data.get("url") or data.get("link")
        if link:
            return f"Document created: {link}"
        if data.get("success") is True:
            return "Document created successfully (no URL returned by workflow)."
        return f"Unexpected response: {json.dumps(data)[:200]}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def create_youtube_playlist(title: str, video_urls: list[str]) -> str:
    """
    Create a new public YouTube playlist with the given title and add the given video URLs to it.
    video_urls should be a list of full YouTube URLs (e.g. https://www.youtube.com/watch?v=VIDEO_ID).
    Returns the playlist URL or an error message.
    """
    webhook_url = _get_youtube_webhook_url()
    if not webhook_url:
        return "Error: YouTube webhook not configured. Set YOUTUBE_WEBHOOK_URL in .env"
    try:
        payload = {"action": "create_playlist", "title": title, "video_urls": video_urls}
        data = _post_webhook(webhook_url, payload)
        link = data.get("playlist_url") or data.get("url") or data.get("link")
        if link:
            return f"Playlist created: {link}"
        if data.get("success") is True:
            return "Playlist created successfully (no URL returned by workflow)."
        return f"Unexpected response: {json.dumps(data)[:200]}"
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def search_youtube(query: str) -> str:
    """
    Search YouTube for videos matching the query. Returns a list of video titles and URLs
    so you can choose the best video for each day of the learning path.
    """
    webhook_url = _get_youtube_webhook_url()
    if not webhook_url:
        return "Error: YouTube webhook not configured. Set YOUTUBE_WEBHOOK_URL in .env"
    try:
        payload = {"action": "search", "query": query}
        data = _post_webhook(webhook_url, payload)
        if data.get("success") is False:
            return f"Search failed: {data.get('error', json.dumps(data)[:200])}"
        # Return a string the agent can use: list of videos
        videos = data.get("videos") or data.get("results") or []
        if not videos:
            return "No videos found. You may suggest well-known video URLs from your knowledge."
        lines = []
        for i, v in enumerate(videos[:15], 1):
            url = v.get("url") or v.get("video_url") or v.get("id", "")
            title = v.get("title", "Unknown")
            lines.append(f"{i}. {title} | {url}")
        return "\n".join(lines) if lines else json.dumps(data)[:500]
    except httpx.HTTPStatusError as e:
        # If workflow doesn't support "search", return a hint
        if e.response.status_code == 400 or e.response.status_code == 422:
            return "Search not supported by this workflow. Use your knowledge to suggest YouTube video URLs for each topic."
        return f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_webhook_tools(drive: bool = True, youtube: bool = True):
    """Return list of LangChain tools for Drive and YouTube webhooks."""
    tools = []
    if youtube:
        tools.extend([search_youtube, create_youtube_playlist])
    if drive and _get_drive_webhook_url():
        tools.append(create_drive_document)
    return tools
