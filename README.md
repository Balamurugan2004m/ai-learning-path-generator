# Learning Path Generator with Model Context Protocol (MCP)

This project is a Streamlit-based web application that generates personalized learning paths using the Model Context Protocol (MCP). It integrates with various services including YouTube, Google Drive, and Notion to create comprehensive learning experiences.

## Features

- 🎯 Generate personalized learning paths based on your goals
- 🎥 Integration with YouTube for video content
- 📁 Google Drive integration for document storage
- 📝 Notion integration for note-taking and organization
- 🚀 Real-time progress tracking
- 🎨 User-friendly Streamlit interface

## Prerequisites

- Python 3.10+
- Google ai Studio API Key
- Pipedream URLs for integrations (YouTube and either Drive or Notion)

## Installation

1. Clone the repository:

2. Create and activate a virtual environment:

3. Install the required packages:
```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set **GOOGLE_API_KEY** (your Google AI Studio / Gemini key).

### Try it without Pipedream (Demo mode)

To **stop the endless loading** and see a result right away:

1. In `.env`, set **USE_DEMO_MODE=true** and leave **YOUTUBE_WEBHOOK_URL** empty (or remove it).
2. Run the app. It will use **Gemini only** and show a **text-only** learning path (no real YouTube playlist or Drive/Notion doc).

No Pipedream setup is required for demo mode.

### Full mode: Drive + YouTube via Pipedream webhooks

To **create real Google Drive documents and YouTube playlists**:

1. In `.env`, set **USE_DEMO_MODE=false** (or remove it).
2. Set **YOUTUBE_WEBHOOK_URL** and **SECONDARY_WEBHOOK_URL** to your Pipedream workflow trigger URLs.
3. Set **SECONDARY_WEBHOOK_TYPE=drive** for Google Drive.
4. Your Pipedream workflows must accept the **request format** and return the **response format** described in **[PIPEDREAM_WEBHOOKS.md](PIPEDREAM_WEBHOOKS.md)**.

The app will POST JSON to your workflows (e.g. `create_document`, `create_playlist`). Each workflow should call the Google Drive / YouTube APIs and return the document or playlist URL. No MCP or JSON-RPC is required.

## Running the Application

To start the application, run:
```bash
streamlit run app.py
```

The application will be available at `http://localhost:8501` by default.

## Usage

1. Run the app and sign in (any email/password for the mock login).
2. Enter your learning goal (e.g., "I want to learn python basics in 3 days").
3. Click "Generate Learning Path" to create your personalized learning plan.

## Project Structure

- `app.py` - Main Streamlit application
- `utils.py` - Utility functions and helper methods
- `prompt.py` - Prompt template
- `requirements.txt` - Project dependencies
