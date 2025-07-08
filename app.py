# app.py ──────────────────────────────────────────────────────────────────
import streamlit as st

# ── GLOBAL CONFIG ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventory Management System",
    layout="wide",
)

# ── AUTHENTICATION ───────────────────────────────────────────────────────
from inv_signin import authenticate      # populates st.session_state["user"], ["permissions"], …

# ── OPTIONAL GLOBAL SIDEBAR WIDGETS ──────────────────────────────────────
def _inject_sidebar_extras() -> None:
    """
    If the repo contains `sidebar.extra_sidebar_elements()`, call it to
    draw company-wide sidebar widgets (logo, theme switch, etc.).
    Otherwise do nothing.
    """
    try:
        from sidebar import extra_sidebar_elements  # type: ignore
        extra_sidebar_elements()
    except ImportError:
        pass


# ── MAIN ────────────────────────────────────────────────────────────────
def main() -> None:
    authenticate()            # 1️⃣  protect the app
    _inject_sidebar_extras()  # 2️⃣  add global widgets (optional)

    # 3️⃣  landing content for the root URL ("/")
    st.markdown(
        """
        ## Inventory Management System

        Use the menu on the left to navigate.  
        Pages are listed automatically based on the files in the `pages/`
        directory; you’ll only see the sections you have permission to access.
        """
    )


if __name__ == "__main__":
    main()
