"""
AI Learning Path Generator - Production-style user application.
Uses environment variables for secrets; mock login and dashboard UI.
"""
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from utils import run_agent_sync, _use_demo_mode, _use_webhook_mode

# Page config - no sidebar, wide layout
st.set_page_config(
    page_title="Build Your Learning Path",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS – gamified, clean UI
st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebar"] + div { margin-left: 0 !important; }
    
    .main-block { max-width: 640px; margin: 0 auto; padding: 2rem 1rem; }
    
    .login-card {
        background: linear-gradient(160deg, #f0f9ff 0%, #e0f2fe 50%, #bae6fd 100%);
        border-radius: 20px;
        padding: 2.5rem;
        box-shadow: 0 8px 32px rgba(14, 165, 233, 0.15);
        margin: 2rem auto;
        border: 1px solid rgba(14, 165, 233, 0.2);
    }
    .dashboard-header { margin-bottom: 1.5rem; padding-bottom: 0.75rem; }
    
    .hero-text {
        font-size: 1.1rem;
        color: #0c4a6e;
        margin-bottom: 1.5rem;
    }
    .goal-input-wrap {
        background: #fff;
        border-radius: 16px;
        padding: 0.5rem 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border: 2px solid #e0f2fe;
    }
    .result-box {
        background: linear-gradient(180deg, #f0fdf4 0%, #dcfce7 100%);
        border-radius: 16px;
        padding: 1.5rem 1.75rem;
        margin-top: 1rem;
        border: 2px solid #86efac;
        box-shadow: 0 4px 12px rgba(34, 197, 94, 0.1);
    }
    .level-badge {
        display: inline-block;
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .mission-complete {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
        color: white;
        padding: 0.75rem 1.25rem;
        border-radius: 12px;
        font-weight: 600;
        text-align: center;
        margin: 0.5rem 0;
    }
    h1, h2, h3 { color: #0c4a6e; }
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
    st.markdown("<div class='main-block'>", unsafe_allow_html=True)
    container = st.container()
    with container:
        st.markdown("<div class='login-card'>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🎯 Your Learning Journey Starts Here")
            st.markdown("<p class='hero-text'>Sign in to build a custom path and get a Drive doc + YouTube playlist.</p>", unsafe_allow_html=True)
            st.markdown("---")
            email = st.text_input("Email", placeholder="you@example.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password")
            st.markdown("")
            if st.button("Start journey →", type="primary", use_container_width=True):
                if not email or not password:
                    st.warning("Enter your email and password to continue.")
                elif mock_authenticate(email, password):
                    st.session_state.logged_in = True
                    st.session_state.user_email = email.strip()
                    st.rerun()
                else:
                    st.warning("Use any email and password to try the app.")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


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

    with progress_container:
        if progress_pct >= 1.0:
            st.markdown("<div class='mission-complete'>🎉 Mission complete! Your path is ready.</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='level-badge'>Level {int(progress_pct * 5) + 1}</span> {level_label}", unsafe_allow_html=True)


def render_dashboard():
    """Render main dashboard: goal input, generate button, and results."""
    init_session_state()

    # Header with logout
    header = st.container()
    with header:
        col_title, col_spacer, col_logout = st.columns([2, 2, 1])
        with col_title:
            st.markdown("### 🎯 Build Your Learning Path")
        with col_logout:
            if st.button("Sign out", key="logout_btn"):
                logout()
                st.rerun()
        st.markdown("<div class='dashboard-header'></div>", unsafe_allow_html=True)

    main = st.container()
    with main:
        if _use_webhook_mode():
            st.caption("We’ll create a Google Doc and a YouTube playlist for you.")
        st.markdown("**What do you want to learn?**")
        user_goal = st.text_input(
            "Learning goal",
            placeholder="e.g. Python basics in 5 days, Data science in a week",
            label_visibility="collapsed",
            key="user_goal_input",
        )
        st.markdown("")

        progress_bar_placeholder = st.empty()
        progress_container = st.container()

        col_btn, _ = st.columns([1, 3])
        with col_btn:
            generate_clicked = st.button(
                "Generate my path →",
                type="primary",
                disabled=st.session_state.is_generating,
                use_container_width=True,
                key="generate_btn",
            )

        if generate_clicked:
            if not (user_goal and user_goal.strip()):
                st.warning("Tell us what you want to learn so we can build your path.")
            else:
                try:
                    st.session_state.is_generating = True
                    st.session_state.current_step = ""
                    st.session_state.progress = 0
                    st.session_state.last_section = ""
                    st.session_state.last_result = None

                    with st.spinner("Building your path…"):
                        result = run_agent_sync(
                            user_goal=user_goal.strip(),
                            progress_callback=lambda msg: update_progress(
                                progress_bar_placeholder, progress_container, msg
                            ),
                        )
                    st.session_state.last_result = result
                    st.session_state.is_generating = False
                    st.success("Your learning path is ready.")
                except Exception as e:
                    st.session_state.is_generating = False
                    err_text = str(e).strip()
                    st.error("Something went wrong. Please try again.")
                    st.caption("If it keeps failing, check your app configuration.")

        if st.session_state.get("last_result"):
            st.markdown("---")
            st.markdown("#### 🏆 Your Learning Path")
            st.markdown("<div class='result-box'>", unsafe_allow_html=True)
            result = st.session_state.last_result
            if result and "messages" in result:
                for msg in result["messages"]:
                    st.markdown(f"📚 {msg.content}")
            else:
                st.info("Nothing generated yet. Try a different goal or run again.")
            st.markdown("</div>", unsafe_allow_html=True)


def main():
    init_session_state()
    if not st.session_state.logged_in:
        render_login()
        return
    render_dashboard()


if __name__ == "__main__":
    main()
