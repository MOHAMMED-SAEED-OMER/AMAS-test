# sidebar.py  ────────────────────────────────────────────────────────────
import streamlit as st
from db_handler import DatabaseManager
from auth_utils import verify_pin, hash_pin

db = DatabaseManager()

# ── CSS ────────────────────────────────────────────────────────────────
def _inject_sidebar_css() -> None:
    """Run once per session to tweak sidebar look & feel."""
    if st.session_state.get("_sidebar_css_done"):
        return

    st.markdown(
        """
        <style>
        /* logo padding */
        section[data-testid="stSidebar"] img {
            margin-bottom: 1rem;
        }
        /* nicer expander spacing */
        section[data-testid="stSidebar"] details {
            margin-top: 1rem;
        }
        /* full-width primary buttons inside sidebar */
        section[data-testid="stSidebar"] .stButton>button {
            width: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_sidebar_css_done"] = True


# ── Change-PIN expander ────────────────────────────────────────────────
def _change_pin_ui() -> None:
    with st.sidebar.expander("🔑 Change PIN"):
        old  = st.text_input("Current",         type="password", key="old_pin")
        new1 = st.text_input("New (4–8 digits)",type="password", key="new_pin1")
        new2 = st.text_input("Confirm new",     type="password", key="new_pin2")

        if st.button("Update PIN", key="btn_update_pin"):
            if not (old and new1 and new2):
                st.warning("Fill all three boxes.")
                return

            row = db.fetch_data(
                "SELECT pin_hash FROM `users` WHERE email = %s",
                (st.session_state["user_email"],),
            )
            stored = row.pin_hash.iloc[0] if not row.empty else None
            if not verify_pin(old, stored):
                st.error("Current PIN is incorrect.")
                return

            if new1 != new2:
                st.error("New PIN entries don’t match.")
                return

            if not (new1.isdigit() and 4 <= len(new1) <= 8):
                st.error("PIN must be 4–8 digits.")
                return

            db.execute_command(
                "UPDATE `users` SET pin_hash = %s WHERE email = %s",
                (hash_pin(new1), st.session_state["user_email"]),
            )
            st.success("✔ PIN updated.")


# ── Public helper for app.py ───────────────────────────────────────────
def extra_sidebar_elements() -> None:
    """
    Called from app.py after the user is authenticated.
    Adds logo, logout, and Change-PIN panel; no page navigation here,
    because Streamlit’s Pages feature already handles that for us.
    """
    _inject_sidebar_css()

    # ─ Logo / brand mark
    st.sidebar.image("assets/logo.png", use_container_width=True)

    # ─ Optional user info (nice touch, not required)
    user_name = st.session_state.get("user_name", "User")
    st.sidebar.markdown(f"**👤 {user_name}**")
    st.sidebar.markdown("---")

    # ─ Change-PIN expander
    _change_pin_ui()

    # ─ Logout button (whatever your logout function is called)
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.logout()


# ── Backward-compat shim ───────────────────────────────────────────────
# If *something* else in your codebase still calls sidebar(), delegate it.
def sidebar() -> str | None:              # type: ignore
    """
    Legacy entry-point kept for backward compatibility.
    Simply renders the extra widgets and returns None.
    """
    extra_sidebar_elements()
    return None
