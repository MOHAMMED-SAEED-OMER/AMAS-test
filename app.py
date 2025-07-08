# app.py  ────────────────────────────────────────────────────────────────
import streamlit as st

# ── GLOBAL CONFIG ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventory Management System",
    layout="wide",
)

# ── SHARED HELPERS (run once per session, no matter which page opens) ─
from inv_signin import authenticate            # login / SSO
from sidebar    import extra_sidebar_elements  # any global widgets you still want

# ── MAIN ───────────────────────────────────────────────────────────────
def main() -> None:
    """
    This file’s only job is to run authentication and provide
    global UI/context.  Actual feature pages now live under /pages.
    """
    # 1️⃣  Guard the whole app
    authenticate()              # sets st.session_state["user"], ["permissions"], …

    # 2️⃣  (Optional) put anything you want to show on *every* page here
    extra_sidebar_elements()    # e.g. company logo, dark-mode toggle, etc.

    # 3️⃣  Landing view for the root page ("/")
    st.markdown(
        """
        ## Inventory Management System

        Use the menu on the left to navigate through the application.
        Your view is automatically filtered to show only the sections
        you have permission to access.
        """
    )

if __name__ == "__main__":
    main()
