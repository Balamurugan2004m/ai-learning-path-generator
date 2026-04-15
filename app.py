"""
AI Learning Path Generator - Production-style user application.
Uses environment variables for secrets; mock login and dashboard UI.
"""
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from utils import (
    run_agent_sync,
    _use_demo_mode,
    _use_webhook_mode,
    _use_composio_mcp,
    _use_google_super_mode,
)

# Page config - no sidebar, wide layout
st.set_page_config(
    page_title="AI Learning Path Generator",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Premium Dark Glassmorphism UI ────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Google Font ── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

  /* ── Global Reset ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  [data-testid="stSidebar"]       { display: none !important; }
  [data-testid="stHeader"]        { background: transparent !important; }
  [data-testid="stToolbar"]       { display: none !important; }
  [data-testid="stDecoration"]    { display: none !important; }
  footer                          { display: none !important; }
  #MainMenu                       { display: none !important; }

  /* ── App Background ── */
  .stApp, [data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 20% 50%, hsla(260,80%,10%,1) 0%, hsla(220,70%,5%,1) 50%, hsla(200,60%,4%,1) 100%) !important;
    font-family: 'Inter', sans-serif !important;
    min-height: 100vh;
  }

  /* ── Animated grid bg ── */
  .stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(99,102,241,0.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(99,102,241,0.04) 1px, transparent 1px);
    background-size: 48px 48px;
    pointer-events: none;
    z-index: 0;
  }

  /* ── Floating orbs ── */
  .stApp::after {
    content: '';
    position: fixed;
    width: 600px; height: 600px;
    background: radial-gradient(circle, hsla(270,80%,60%,0.12) 0%, transparent 70%);
    top: -150px; right: -150px;
    border-radius: 50%;
    pointer-events: none;
    z-index: 0;
    animation: float 8s ease-in-out infinite;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    50%       { transform: translateY(30px) rotate(5deg); }
  }

  /* ── Block container ── */
  .block-container {
    max-width: 900px !important;
    padding: 2rem 2.5rem !important;
    position: relative; z-index: 1;
  }

  /* ── All text white by default ── */
  .stMarkdown, .stMarkdown p, .stMarkdown li, label,
  [data-testid="stMarkdownContainer"] p { color: rgba(255,255,255,0.85) !important; }

  /* ── Headings ── */
  h1, h2, h3, h4 {
    font-family: 'Inter', sans-serif !important;
    color: #fff !important;
    letter-spacing: -0.02em;
  }

  /* ─────────────── LOGIN CARD ─────────────── */
  .login-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 88vh;
  }

  .login-card {
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 24px;
    padding: 3rem 3.5rem;
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
    box-shadow:
      0 0 0 1px rgba(99,102,241,0.2),
      0 32px 64px -16px rgba(0,0,0,0.6),
      inset 0 1px 0 rgba(255,255,255,0.08);
    animation: slideUp 0.6s cubic-bezier(.16,1,.3,1) both;
  }

  @keyframes slideUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .login-logo {
    width: 56px; height: 56px;
    background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
    border-radius: 16px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.6rem;
    margin: 0 auto 1.5rem;
    box-shadow: 0 8px 24px rgba(99,102,241,0.4);
    text-align: center;
    line-height: 56px;
  }

  .login-title {
    font-size: 1.65rem;
    font-weight: 800;
    text-align: center;
    color: #fff !important;
    margin-bottom: 0.4rem;
    line-height: 1.2;
  }

  .login-subtitle {
    font-size: 0.9rem;
    text-align: center;
    color: rgba(255,255,255,0.5) !important;
    margin-bottom: 2rem;
    line-height: 1.6;
  }

  .divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    margin: 1.5rem 0;
  }

  /* ─────────── INPUTS ─────────── */
  .stTextInput > div > div > input,
  .stTextArea > div > div > textarea {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 12px !important;
    color: #fff !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
    padding: 0.75rem 1rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
  }

  .stTextInput > div > div > input:focus,
  .stTextArea > div > div > textarea:focus {
    border-color: rgba(99,102,241,0.7) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.15) !important;
    outline: none !important;
  }

  .stTextInput > div > div > input::placeholder,
  .stTextArea > div > div > textarea::placeholder {
    color: rgba(255,255,255,0.3) !important;
  }

  /* label of input */
  .stTextInput label, .stTextArea label {
    color: rgba(255,255,255,0.65) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase;
    margin-bottom: 0.4rem !important;
  }

  /* ─────────── BUTTONS ─────────── */
  .stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border: none !important;
    border-radius: 12px !important;
    color: #fff !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
    cursor: pointer !important;
    transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s !important;
    box-shadow: 0 4px 16px rgba(99,102,241,0.35) !important;
    letter-spacing: 0.01em;
  }

  .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(99,102,241,0.5) !important;
    opacity: 0.95;
  }

  .stButton > button:active {
    transform: translateY(0px) !important;
  }

  /* Secondary / logout button */
  .stButton > button[kind="secondary"],
  div[data-testid="column"]:last-child .stButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    box-shadow: none !important;
    white-space: nowrap !important;
    word-break: keep-all !important;
  }

  .stButton > button[kind="secondary"]:hover,
  div[data-testid="column"]:last-child .stButton > button:hover {
    background: rgba(255,255,255,0.12) !important;
    transform: none !important;
    box-shadow: none !important;
  }

  /* ─────────── DASHBOARD HEADER ─────────── */
  .dash-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem 2rem;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
    margin-bottom: 2rem;
    backdrop-filter: blur(12px);
  }

  .dash-logo {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, #6366f1, #a855f7);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.3rem;
    flex-shrink: 0;
    text-align: center;
    line-height: 44px;
    box-shadow: 0 4px 12px rgba(99,102,241,0.35);
  }

  .dash-header-text h2 {
    font-size: 1.2rem !important;
    font-weight: 700 !important;
    color: #fff !important;
    margin: 0 !important;
  }

  .dash-header-text p {
    font-size: 0.8rem !important;
    color: rgba(255,255,255,0.45) !important;
    margin: 0 !important;
  }

  /* ─────────── GOAL SECTION ─────────── */
  .goal-section {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 2rem;
    margin-bottom: 1.5rem;
  }

  .goal-section-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.4rem;
  }

  .goal-section-sub {
    font-size: 0.875rem;
    color: rgba(255,255,255,0.45);
    margin-bottom: 1.5rem;
    line-height: 1.6;
  }

  /* ─────────── BADGE / TAG ─────────── */
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: rgba(99,102,241,0.15);
    border: 1px solid rgba(99,102,241,0.3);
    color: #a5b4fc !important;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }

  /* ─────────── PROGRESS ─────────── */
  .stProgress > div > div > div {
    background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899) !important;
    border-radius: 999px !important;
    transition: width 0.4s ease !important;
  }

  .stProgress > div > div {
    background: rgba(255,255,255,0.07) !important;
    border-radius: 999px !important;
    height: 6px !important;
  }

  /* ─────────── LEVEL BADGE ─────────── */
  .level-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(168,85,247,0.2));
    border: 1px solid rgba(99,102,241,0.35);
    color: #c4b5fd !important;
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-right: 0.5rem;
  }

  /* ─────────── MISSION COMPLETE ─────────── */
  .mission-complete {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.1));
    border: 1px solid rgba(34,197,94,0.3);
    color: #6ee7b7 !important;
    padding: 1rem 1.5rem;
    border-radius: 14px;
    font-weight: 600;
    font-size: 0.95rem;
    margin-top: 0.5rem;
    margin-bottom: 1rem;
    animation: pulseGreen 1.5s ease-in-out 1;
  }

  .progress-live {
    margin-top: 0.45rem;
    margin-bottom: 1rem;
    min-height: 2.1rem;
    display: flex;
    align-items: center;
    gap: 0.55rem;
  }

  @keyframes pulseGreen {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.3); }
    50%  { box-shadow: 0 0 0 12px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
  }

  /* ─────────── RESULT BOX ─────────── */
  .result-box {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 2rem;
    margin-top: 1.5rem;
    position: relative;
    overflow: hidden;
  }

  .result-box::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899);
  }

  .result-heading {
    font-size: 1.1rem;
    font-weight: 700;
    color: #fff !important;
    margin-bottom: 1.2rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  /* Result message content */
  .result-message {
    color: rgba(255,255,255,0.8) !important;
    line-height: 1.75 !important;
    font-size: 0.92rem !important;
  }

  .result-message a {
    color: #818cf8 !important;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  /* ─────────── ALERTS / info / warning ─────────── */
  .stAlert {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    color: rgba(255,255,255,0.8) !important;
  }

  [data-testid="stAlertContainer"][data-baseweb="notification"] {
    background: rgba(99,102,241,0.1) !important;
    border-color: rgba(99,102,241,0.3) !important;
    border-radius: 12px !important;
    color: #c4b5fd !important;
  }

  div[data-testid="stAlertContainer"] p,
  div[data-testid="stAlertContainer"] {
    color: rgba(255,255,255,0.8) !important;
  }

  /* ─────────── SPINNER ─────────── */
  .stSpinner > div { border-top-color: #6366f1 !important; }

  /* ─────────── CAPTION / SMALL TEXT ─────────── */
  .stCaption, .stCaption p {
    color: rgba(255,255,255,0.4) !important;
    font-size: 0.8rem !important;
  }

  /* ─────────── DIVIDER ─────────── */
  hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent) !important;
    margin: 1.5rem 0 !important;
  }

  /* ─────────── FEATURE PILLS row ─────────── */
  .features-row {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 1.75rem;
  }

  .feature-pill {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 999px;
    padding: 0.35rem 0.85rem;
    font-size: 0.78rem;
    color: rgba(255,255,255,0.6) !important;
    font-weight: 500;
  }

  /* ─────────── STAT CARDS row ─────────── */
  .stat-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    flex: 1;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 1.1rem 1.25rem;
    text-align: center;
  }

  .stat-card .stat-val {
    font-size: 1.5rem;
    font-weight: 800;
    background: linear-gradient(135deg, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: block;
  }

  .stat-card .stat-label {
    font-size: 0.75rem;
    color: rgba(255,255,255,0.4) !important;
    font-weight: 500;
    margin-top: 0.25rem;
    display: block;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* ─────────── GLOW PULSE on generate btn ─────────── */
  div[data-testid="column"]:first-child .stButton > button[kind="primary"] {
    position: relative;
    overflow: hidden;
  }

  div[data-testid="column"]:first-child .stButton > button[kind="primary"]::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, transparent 0%, rgba(255,255,255,0.1) 50%, transparent 100%);
    transform: translateX(-100%);
    transition: transform 0.4s ease;
  }

  div[data-testid="column"]:first-child .stButton > button[kind="primary"]:hover::after {
    transform: translateX(100%);
  }

  /* ─────────── SCROLLBAR ─────────── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); }
  ::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.4); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(99,102,241,0.6); }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize all session state keys."""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_email" not in st.session_state:
        st.session_state.user_email = ""
    if "current_step" not in st.session_state:
        st.session_state.current_step = ""
    if "progress" not in st.session_state:
        st.session_state.progress = 0
    if "last_section" not in st.session_state:
        st.session_state.last_section = ""
    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False
    if "last_result" not in st.session_state:
        st.session_state.last_result = None


def mock_authenticate(email: str, password: str) -> bool:
    """Mock auth: accept any non-empty email and password (e.g. demo@example.com / demo)."""
    return bool(email and password and email.strip() and password.strip())


def logout():
    """Clear login state."""
    st.session_state.logged_in = False
    st.session_state.user_email = ""


def render_login():
    """Render login page."""
    init_session_state()

    # Center column
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        # Top decorative part of the card (logo + title + subtitle)
        st.markdown("""
<div style="
  background:rgba(255,255,255,0.04);
  backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
  border:1px solid rgba(255,255,255,0.1);
  border-bottom:none;
  border-radius:24px 24px 0 0;
  padding:2.8rem 3rem 1.5rem;
  text-align:center;
  box-shadow:0 0 0 1px rgba(99,102,241,0.2),0 32px 64px -16px rgba(0,0,0,0.6),inset 0 1px 0 rgba(255,255,255,0.08);
  animation:slideUp 0.6s cubic-bezier(.16,1,.3,1) both;
">
  <div style="
    width:56px;height:56px;
    background:linear-gradient(135deg,#6366f1 0%,#a855f7 50%,#ec4899 100%);
    border-radius:16px;
    margin:0 auto 1.25rem;
    display:flex;align-items:center;justify-content:center;
    font-size:1.6rem;line-height:56px;text-align:center;
    box-shadow:0 8px 24px rgba(99,102,241,0.4);
  ">🚀</div>
  <div style="font-size:1.55rem;font-weight:800;color:#fff;letter-spacing:-0.02em;line-height:1.25;margin-bottom:0.5rem;">
    AI Learning Path Generator
  </div>
  <div style="font-size:0.88rem;color:rgba(255,255,255,0.45);line-height:1.65;">
    Build a personalised curriculum with YouTube playlists<br>
    and a Google Drive study guide — powered by AI.
  </div>
  <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.1),transparent);margin:1.5rem 0 0;"></div>
</div>
""", unsafe_allow_html=True)

        # The form sits inside a matching glass-bottom panel
        st.markdown("""
<div style="
  background:rgba(255,255,255,0.04);
  backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);
  border:1px solid rgba(255,255,255,0.1);
  border-top:none;
  border-radius:0 0 24px 24px;
  padding:0 3rem 2.2rem;
  box-shadow:0 32px 64px -16px rgba(0,0,0,0.6);
  animation:slideUp 0.6s cubic-bezier(.16,1,.3,1) both;
">
""", unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email address", placeholder="you@example.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password")
            st.markdown("")
            submitted = st.form_submit_button("Sign in  →", type="primary", use_container_width=True)

            if submitted:
                if not email or not password:
                    st.warning("Please enter your email and password to continue.")
                elif mock_authenticate(email, password):
                    st.session_state.logged_in = True
                    st.session_state.user_email = email.strip()
                    st.rerun()
                else:
                    st.warning("Use any email and password to try the app.")

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("""
<p style="text-align:center;font-size:0.78rem;color:rgba(255,255,255,0.28);margin-top:1.25rem;">
  Demo mode — any credentials work &nbsp;·&nbsp; No data stored
</p>
""", unsafe_allow_html=True)


def _message_to_level(message: str) -> tuple[float, str]:
    """Map backend messages to gamified level and label."""
    if "Setting up" in message or "Initializing" in message or "Creating AI" in message:
        return 0.15, "Preparing your mission"
    if "Drive" in message or "Notion" in message or "integration" in message.lower():
        return 0.25, "Connecting your tools"
    if "Getting available" in message or "Setup complete" in message:
        return 0.35, "Ready to build"
    if "Generating your learning path" in message:
        return 0.5, "Building your path"
    if "Learning path generation complete" in message or "complete!" in message:
        return 1.0, "Mission complete"
    return 0.4, "Working on it…"


def update_progress(progress_bar_placeholder, progress_container, message: str):
    """Update progress with gamified level labels."""
    st.session_state.current_step = message
    progress_pct, level_label = _message_to_level(message)
    st.session_state.progress = progress_pct
    if "complete" in message.lower():
        st.session_state.is_generating = False
    progress_bar_placeholder.progress(st.session_state.progress)

    if progress_pct >= 1.0:
        progress_container.markdown(
            "<div class='mission-complete'>🎉&nbsp; Mission complete — your learning path is ready!</div>",
            unsafe_allow_html=True,
        )
    else:
        progress_container.markdown(
            "<div class='progress-live'>"
            f"<span class='level-badge'>⚡ {level_label}</span>"
            f"<span style='color:rgba(255,255,255,0.55);font-size:0.85rem;'>{message}</span>"
            "</div>",
            unsafe_allow_html=True,
        )


def render_dashboard():
    """Render main dashboard: goal input, generate button, and results."""
    init_session_state()

    # ── Top header bar ──────────────────────────────────────────────────────
    col_logo, col_title, col_spacer, col_user, col_logout = st.columns([0.05, 0.37, 0.27, 0.15, 0.16])
    with col_logo:
        st.markdown("<div style='font-size:1.8rem;padding-top:0.25rem'>🚀</div>", unsafe_allow_html=True)
    with col_title:
        st.markdown(
            "<div style='padding-top:0.42rem'>"
            "<span style='font-size:0.98rem;font-weight:700;color:#fff;letter-spacing:-0.01em;'>"
            "AI Learning Path Generator</span></div>",
            unsafe_allow_html=True,
        )
    with col_user:
        email_short = st.session_state.user_email.split("@")[0] if st.session_state.user_email else "User"
        st.markdown(
            f"<div style='padding-top:0.55rem;text-align:right;"
            f"font-size:0.8rem;color:rgba(255,255,255,0.45);'>"
            f"👤 {email_short}</div>",
            unsafe_allow_html=True,
        )
    with col_logout:
        if st.button("Sign out", key="logout_btn"):
            logout()
            st.rerun()

    # Gradient divider under header
    st.markdown(
        "<div style='height:3px;background:linear-gradient(90deg,#6366f1,#a855f7,#ec4899);"
        "border-radius:999px;margin-bottom:2rem;opacity:0.85;'></div>",
        unsafe_allow_html=True,
    )

    # ── Mode badge ──────────────────────────────────────────────────────────
    if _use_google_super_mode():
        mode_badge = "GOOGLE SUPER MODE"
        mode_color = "#f59e0b"
        mode_bg    = "rgba(245,158,11,0.12)"
        mode_bdr   = "rgba(245,158,11,0.3)"
    elif _use_composio_mcp():
        mode_badge = "🔗 MCP Link Mode"
        mode_color = "#34d399"
        mode_bg    = "rgba(52,211,153,0.12)"
        mode_bdr   = "rgba(52,211,153,0.3)"
    elif _use_webhook_mode():
        mode_badge = "🔌 Webhook Mode"
        mode_color = "#60a5fa"
        mode_bg    = "rgba(96,165,250,0.12)"
        mode_bdr   = "rgba(96,165,250,0.3)"
    else:
        mode_badge = "✨ Demo Mode"
        mode_color = "#c084fc"
        mode_bg    = "rgba(192,132,252,0.12)"
        mode_bdr   = "rgba(192,132,252,0.3)"

    st.markdown(
        f"<div style='display:inline-flex;align-items:center;gap:0.5rem;"
        f"background:{mode_bg};border:1px solid {mode_bdr};"
        f"border-radius:999px;padding:0.3rem 0.9rem;margin-bottom:1.5rem;'>"
        f"<span style='color:{mode_color};font-size:0.78rem;font-weight:600;letter-spacing:0.04em;'>"
        f"{mode_badge}</span></div>",
        unsafe_allow_html=True,
    )

    # ── Stat cards ──────────────────────────────────────────────────────────
    st.markdown("""
<div class="stat-row">
  <div class="stat-card">
    <span class="stat-val">7–30</span>
    <span class="stat-label">Day Plans</span>
  </div>
  <div class="stat-card">
    <span class="stat-val">AI</span>
    <span class="stat-label">Powered</span>
  </div>
  <div class="stat-card">
    <span class="stat-val">YT</span>
    <span class="stat-label">Playlists</span>
  </div>
  <div class="stat-card">
    <span class="stat-val">Doc</span>
    <span class="stat-label">Drive Export</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Goal input card ──────────────────────────────────────────────────────
    st.markdown("""
<div class="goal-section-title">What do you want to learn?</div>
<div class="goal-section-sub">
  Describe your learning goal — include a topic, timeframe, and skill level for the best results.
</div>
<div class="features-row">
  <div class="feature-pill">📺 YouTube curated videos</div>
  <div class="feature-pill">📄 Google Drive doc</div>
  <div class="feature-pill">📅 Day-by-day plan</div>
</div>
""", unsafe_allow_html=True)

    user_goal = st.text_input(
        "Learning goal",
        placeholder="e.g.  Python basics in 7 days · Machine learning for beginners · React in 2 weeks",
        label_visibility="collapsed",
        key="user_goal_input",
    )

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    progress_bar_placeholder = st.empty()
    progress_container       = st.empty()

    col_btn, col_hint = st.columns([0.32, 0.68])
    with col_btn:
        generate_clicked = st.button(
            "✦ Generate My Path",
            type="primary",
            disabled=st.session_state.is_generating,
            use_container_width=True,
            key="generate_btn",
        )
    with col_hint:
        if st.session_state.is_generating:
            st.markdown(
                "<p style='padding-top:0.65rem;font-size:0.82rem;color:rgba(255,255,255,0.35);'>"
                "⏳ Generating — this may take 30–60 seconds…</p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<p style='padding-top:0.65rem;font-size:0.82rem;color:rgba(255,255,255,0.3);'>"
                "Takes ~30–60 s &nbsp;·&nbsp; Results include playlist + Drive doc</p>",
                unsafe_allow_html=True,
            )

    if generate_clicked:
        if not (user_goal and user_goal.strip()):
            st.warning("⚠️  Tell us what you want to learn so we can build your path.")
        else:
            try:
                st.session_state.is_generating = True
                st.session_state.current_step  = ""
                st.session_state.progress      = 0
                st.session_state.last_section  = ""
                st.session_state.last_result   = None

                with st.spinner("Building your personalised learning path…"):
                    result = run_agent_sync(
                        user_goal=user_goal.strip(),
                        progress_callback=lambda msg: update_progress(
                            progress_bar_placeholder, progress_container, msg
                        ),
                    )
                st.session_state.last_result    = result
                st.session_state.is_generating  = False
                st.success("✅  Your learning path is ready — scroll down to view it.")
            except Exception as e:
                st.session_state.is_generating = False
                err_text = str(e).strip()
                st.error(f"⚠️  Something went wrong: {err_text}")
                st.caption("If it keeps failing, check your app configuration or API keys.")

    # ── Results ──────────────────────────────────────────────────────────────
    if st.session_state.get("last_result"):
        st.markdown(
            "<div style='height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.08),transparent);margin:1.75rem 0;'></div>",
            unsafe_allow_html=True,
        )

        st.markdown("""
<div class="result-box">
<div class="result-heading">🏆&nbsp; Your Personalised Learning Path</div>
""", unsafe_allow_html=True)

        result = st.session_state.last_result
        if result and "messages" in result:
            for msg in result["messages"]:
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                # Render content as markdown (links become clickable)
                st.markdown(content)
        else:
            st.info("Nothing generated yet. Try a different goal or run again.")

        st.markdown("</div>", unsafe_allow_html=True)

        # Quick action pills after results
        st.markdown("""
<div style="margin-top:1.25rem;display:flex;gap:0.75rem;flex-wrap:wrap;">
  <div class="feature-pill">💡 Tip: click any YouTube link to start watching</div>
  <div class="feature-pill">📌 Bookmark your Drive doc for daily reference</div>
</div>
""", unsafe_allow_html=True)


def main():
    init_session_state()
    if not st.session_state.logged_in:
        render_login()
        return
    render_dashboard()


if __name__ == "__main__":
    main()
