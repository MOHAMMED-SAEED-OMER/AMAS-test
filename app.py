"""
app.py – Inventory Management System
• st.set_page_config() first (avoids config error)
• Run-reason audit with graceful fallback if st.modal is absent
Last update: 2025-07-09
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import streamlit as st

# ── MUST be the first Streamlit call ─────────────────────────
st.set_page_config(page_title="Inventory Management System", layout="wide")

import psycopg2  # noqa: E402

# ── Page modules ─────────────────────────────────────────────
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

# unified admin tabs
from admin.user_admin_tabs import show_user_admin  # noqa: E402

# ── DB helpers ───────────────────────────────────────────────
def _get_db_conn():
    """Return a psycopg2 connection using DATABASE_URL env var."""
    return psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")


def _init_run_reason_table():
    """Create run_reason_log if it doesn't exist (idempotent)."""
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
    """Insert a run-reason row."""
    _init_run_reason_table()
    with _get_db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO run_reason_log (id, session_id, user_email,
                                        run_reason, logged_at)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                uuid.uuid4(),
                st.session_state["session_id"],
                st.session_state["user_email"],
                reason.strip(),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()


# ── Ask for run reason (modal if available, else form) ──────
def ensure_run_reason_logged() -> None:
    if st.session_state.get("reason_logged"):
        return  # already done

    # 1️⃣ Preferred UX: modal (Streamlit ≥ 1.25)
    if hasattr(st, "modal"):
        with st.modal("📝 Tell us why you’re running the app"):
            reason = st.text_area(
                "Briefly describe this session’s purpose "
                "(e.g., 'daily inventory check', 'adding new POs', 'audit').",
                placeholder="Your reason…",
                height=120,
            )
            submitted = st.button("Submit", disabled=not reason.strip())
            if submitted:
                log_run_reason(reason)
                st.session_state["reason_logged"] = True
                st.success("✅ Reason recorded. Thank you!")
                st.experimental_rerun()  # reload without modal
        st.stop()  # block until modal is closed

    # 2️⃣ Fallback: inline form (works on older versions)
    st.warning("📝 Please tell us why you’re running the app.")
    with st.form("run_reason_form", clear_on_submit=False):
        reason = st.text_area(
            "Purpose of this session:",
            placeholder="Your reason…",
            height=120,
        )
        submitted = st.form_submit_button("Submit")
        if submitted and reason.strip():
            log_run_reason(reason)
            st.session_state["reason_logged"] = True
            st.success("✅ Reason recorded. Thank you!")
            st.experimental_rerun()
        elif submitted:
            st.error("Please enter a reason before submitting.")
    st.stop()  # halt app until reason supplied


# ── Main entry ───────────────────────────────────────────────
def main() -> None:
    # Authentication populates user_email, permissions, user_role
    authenticate()

    # Generate a per-session UUID
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = uuid.uuid4()

    # Run-reason capture (blocks until provided)
    ensure_run_reason_logged()

    # Sidebar navigation
    page  = sidebar()
    perms = st.session_state.get("permissions", {})

    # Routing
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
