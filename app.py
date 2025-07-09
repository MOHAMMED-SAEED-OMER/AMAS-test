"""
app.py – Inventory Management System
Re-ordered so st.set_page_config() is the first Streamlit call.
Added “run-reason” audit logging.  (Last update 2025-07-09)
"""

import os
import uuid
from datetime import datetime, timezone

import streamlit as st

# ── page-wide config – must be FIRST Streamlit command ───────
st.set_page_config(page_title="Inventory Management System", layout="wide")

import psycopg2  # noqa: E402  (import after page_config is fine)

# ── Page modules (these may contain Streamlit calls) ──────────
import home  # noqa: E402
from item                       import mainitem  # noqa: E402
import PO.mainpo                as mainpo        # noqa: E402
from receive_items.main_receive import main_receive_page  # noqa: E402
import reports.main_reports      as main_reports         # noqa: E402
from selling_area.main_shelf     import main_shelf_page  # noqa: E402
from cashier.main_cashier        import main_cashier_page  # noqa: E402
from finance.main_finance        import main_finance_page  # noqa: E402
from returns.main_return         import main_return_page  # noqa: E402
from issues.main_issue           import issues_page       # noqa: E402
from shelf_map.main_map          import main as shelf_map_page  # noqa: E402

# helpers
from sidebar    import sidebar       # noqa: E402
from inv_signin import authenticate  # noqa: E402

# NEW: unified user management tabs
from admin.user_admin_tabs import show_user_admin  # noqa: E402

# ── DB helpers ────────────────────────────────────────────────
def _get_db_conn():
    """Return a psycopg2 connection using DATABASE_URL env var."""
    return psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")


def _init_run_reason_table():
    """Create run_reason_log table if it doesn't exist (idempotent)."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS run_reason_log (
        id            UUID PRIMARY KEY,
        session_id    UUID,
        user_email    TEXT NOT NULL,
        run_reason    TEXT NOT NULL,
        logged_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    with _get_db_conn() as conn, conn.cursor() as cur:
        cur.execute(create_sql)
        conn.commit()


def log_run_reason(reason: str) -> None:
    """Persist the reason the user gave for running the app."""
    _init_run_reason_table()  # safe to call each time
    with _get_db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO run_reason_log (id, session_id, user_email, run_reason, logged_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(),                          # id
                st.session_state["session_id"],        # session identifier
                st.session_state["user_email"],        # from authenticate()
                reason.strip(),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()


# ── Main entry – includes run-reason capture ─────────────────
def main() -> None:
    # ── Auth (sets user_email, permissions, user_role) ────────
    authenticate()

    # Generate a per-session UUID once
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = uuid.uuid4()

    # ── Ask “Why are you running the app?” (once per session) ─
    if "reason_logged" not in st.session_state:
        with st.modal("📝 Tell us why you’re running the app"):
            reason = st.text_area(
                "Please briefly describe the purpose of this session "
                "(e.g., 'daily inventory check', 'adding new POs', 'audit').",
                placeholder="Your reason…",
                height=120,
            )
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Submit", type="primary", disabled=not reason.strip()):
                    log_run_reason(reason)
                    st.session_state["reason_logged"] = True
                    st.success("✅ Reason recorded. Thank you!")
            with col2:
                st.markdown("*We record this just once per session for audit and analytics.*")
            st.stop()  # halt until the reason is provided

    # ── Sidebar navigation & routing ──────────────────────────
    page  = sidebar()
    perms = st.session_state.get("permissions", {})

    if   page == "Home"            and perms.get("CanAccessHome"):           home.home()
    elif page == "Item"            and perms.get("CanAccessItems"):          mainitem.item_page()
    elif page == "Receive Items"   and perms.get("CanAccessReceive"):        main_receive_page()
    elif page == "Purchase Order"  and perms.get("CanAccessPO"):            mainpo.po_page()
    elif page == "Selling Area"    and perms.get("CanAccessSellingArea"):    main_shelf_page()
    elif page == "Cashier"         and perms.get("CanAccessCashier"):       main_cashier_page()
    elif page == "Finance"         and perms.get("CanAccessFinance"):       main_finance_page()
    elif page == "Returns"         and perms.get("CanAccessReturns"):       main_return_page()
    elif page == "Issues"          and perms.get("CanAccessIssues"):        issues_page()
    elif page == "Shelf Map"       and perms.get("CanAccessShelfMap"):      shelf_map_page()
    elif page == "Reports"         and perms.get("CanAccessReports"):       main_reports.reports_page()
    elif page == "User Management" and st.session_state.get("user_role") == "Admin":
        show_user_admin()
    else:
        st.error("❌ You do not have permission to access this page.")


# ── Bootstrap ────────────────────────────────────────────────
if __name__ == "__main__":
    main()
