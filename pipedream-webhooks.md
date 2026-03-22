# Pipedream Webhook Contract

To have the app **create real Google Drive documents and YouTube playlists**, your Pipedream workflows must accept HTTP POST with the JSON bodies below and return the expected JSON.

## 1. Turn off demo mode

In `.env`:

- Set **USE_DEMO_MODE=false** (or remove it / leave it unset).
- Set **YOUTUBE_WEBHOOK_URL** = your Pipedream workflow URL for YouTube.
- Set **SECONDARY_WEBHOOK_URL** = your Pipedream workflow URL for Google Drive.
- Set **SECONDARY_WEBHOOK_TYPE=drive**.

The app will then POST to these URLs with the payloads below.

---

## 2. YouTube workflow (YOUTUBE_WEBHOOK_URL)

Your workflow receives a POST body with an **action** field.

### Create playlist

**Request:**

```json
{
  "action": "create_playlist",
  "title": "Python in 5 days - Learning Path",
  "video_urls": [
    "https://www.youtube.com/watch?v=VIDEO_ID_1",
    "https://www.youtube.com/watch?v=VIDEO_ID_2"
  ]
}
```

**Expected response (any of these is fine):**

```json
{ "success": true, "playlist_url": "https://www.youtube.com/playlist?list=..." }
```
or
```json
{ "success": true, "url": "https://www.youtube.com/playlist?list=..." }
```

Your workflow should: create a public playlist with `title`, add the videos from `video_urls`, then return the playlist URL.

### Search (optional)

**Request:**

```json
{
  "action": "search",
  "query": "python basics tutorial"
}
```

**Expected response:**

```json
{
  "success": true,
  "videos": [
    { "title": "Video title", "url": "https://www.youtube.com/watch?v=..." }
  ]
}
```

If you don’t implement **search**, the app will still work: the AI will suggest video URLs from its knowledge and call **create_playlist** only.

---

## 3. Drive workflow (SECONDARY_WEBHOOK_URL)

**Request:**

```json
{
  "action": "create_document",
  "title": "Learning Path: Python in 5 days",
  "content": "# Day 1\nTopic: Intro\nYouTube Link: https://..."
}
```

`content` is markdown or plain text (day-wise learning path with links).

**Expected response:**

```json
{ "success": true, "document_url": "https://docs.google.com/document/d/..." }
```
or
```json
{ "success": true, "url": "https://docs.google.com/document/d/..." }
```

Your workflow should: create a new Google Doc with `title`, write `content` into the body, then return the document’s shareable URL.

---

## 4. Summary

| Webhook           | Action            | Request body                                                                 | Response (include at least one of these)                    |
|-------------------|-------------------|-------------------------------------------------------------------------------|-------------------------------------------------------------|
| YouTube URL       | `create_playlist` | `title`, `video_urls` (array of YouTube URLs)                                 | `playlist_url` or `url`                                     |
| YouTube URL       | `search`          | `query`                                                                       | `videos`: `[{ "title", "url" }]`                            |
| Drive URL         | `create_document` | `title`, `content` (markdown/text)                                            | `document_url` or `url`                                     |

Use Pipedream’s **Google Drive** and **YouTube** actions to create the doc and playlist; your workflow just needs to parse the incoming JSON and return the link in the format above.
