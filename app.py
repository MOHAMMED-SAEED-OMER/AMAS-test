# app.py ──────────────────────────────────────────────────────────────────
import streamlit as st

# ── GLOBAL CONFIG ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventory Management System",
    layout="wide",
)

# ── AUTHENTICATION ───────────────────────────────────────────────────────
from inv_signin import authenticate     # ← sets st.session_state["user"], ["permissions"], …

# ── OPTIONAL SIDEBAR EXTRAS ──────────────────────────────────────────────
def _inject_sidebar_extras() -> None:
    """
    Draw company logo, dark-mode toggle, etc. if helper(s) exist.

    • Preferred helper name:  extra_sidebar_elements()
    • Fallback  helper name:  sidebar()           (legacy)
    • If neither is found, do nothing.
    """
    try:
        from sidebar import extra_sidebar_elements as _extras     # type: ignore
        _extras()
    except ImportError:
        try:
            # legacy helper that used to return a page choice; we just ignore the return value
            from sidebar import sidebar as _legacy_extras         # type: ignore
            _legacy_extras()
        except ImportError:
            pass  # no sidebar embellishments available


# ── MAIN ─────────────────────────────────────────────────────────────────
def main() -> None:
    authenticate()            # 1️⃣  guard the whole app
    _inject_sidebar_extras()  # 2️⃣  draw optional global widgets

    # 3️⃣  landing view for root ("/")
    st.markdown(
        """
        ## Inventory Management System

        Use the menu on the left to navigate.  
        Only the pages you have permission to access are shown.
        """
    )


if __name__ == "__main__":
    main()
