# admin/user_management.py  ───────────────────────────────────────────────
"""
Admin page: view / edit users and their page-level permissions.

• Uses MySQL for storage (via db_handler.DatabaseManager).
• Permission-column list is discovered lazily and cached with Streamlit.
• PIN resetting is optional and validated (4-8 digits).
"""

from __future__ import annotations

import html
import streamlit as st
from auth_utils   import hash_pin
from db_handler   import DatabaseManager

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _discover_perm_cols() -> list[str]:
    """
    Introspect the `users` table and return all columns beginning
    with 'canaccess'.  Falls back to a hard-coded list if the query
    fails (e.g. DB offline or no INFORMATION_SCHEMA privileges).
    """
    db = DatabaseManager()
    q = (
        "SELECT column_name "
        "FROM   information_schema.columns "
        "WHERE  table_name = 'users' "
        "  AND  column_name LIKE 'canaccess%%' "
        "ORDER  BY column_name;"
    )
    try:
        return (
            db.fetch_data(q)["column_name"]
            .str.lower()
            .tolist()
        )
    except Exception:
        return [
            "canaccesshome", "canaccessitems", "canaccessreceive",
            "canaccesspo", "canaccessreports", "canaccesssellingarea",
            "canaccesscashier", "canaccessfinance", "canaccessreturns",
            "canaccessshelfmap", "canaccessissues",
        ]


@st.cache_data(ttl=600, show_spinner=False)
def _get_perm_cols() -> list[str]:
    """Cached wrapper around `_discover_perm_cols()` (10-minute TTL)."""
    return _discover_perm_cols()


def _pretty(col: str) -> str:
    """`canaccesscashier` → `Cashier`."""
    return col.replace("canaccess", "").title()


@st.cache_data(ttl=600, show_spinner=False)
def _load_users(cols: list[str]):
    """Return a DataFrame of all users (cached 10 min)."""
    db = DatabaseManager()
    col_str = ", ".join(cols)
    return db.fetch_data(f"SELECT {col_str} FROM `users` ORDER BY name;")


# ─────────────────────────────────────────────────────────────
# Page entry-point
# ─────────────────────────────────────────────────────────────
def user_management() -> None:
    """Render the User-Management admin view."""
    st.title("👤 User Management")

    # 1) Pull permission columns lazily
    PERM_COLS = _get_perm_cols()

    # 2) Fetch user records
    col_list = ["userid", "name", "email", "role"] + PERM_COLS
    users_df = _load_users(col_list)

    if users_df.empty:
        st.warning("No users found.")
        return

    # 3) Drop-downs & selection helpers
    email_to_uid  = dict(zip(users_df.email, users_df.userid))
    email_to_name = dict(zip(users_df.email, users_df.name))
    email_list    = list(email_to_uid)

    sel_email = st.session_state.get("um_selected_email", email_list[0])
    if sel_email not in email_list:
        sel_email = email_list[0]
    st.session_state["um_selected_email"] = sel_email

    row = users_df[users_df.email == sel_email].iloc[0]
    uid = int(row.userid)

    st.subheader(f"Editing: **{row.name}** ({row.email})")

    # ── Edit-form ────────────────────────────────────────────
    with st.form("um_edit_form"):
        new_role = st.selectbox(
            "Role",
            ["User", "Admin"],
            index=0 if row.role == "User" else 1,
            key="um_role",
        )

        st.subheader("Access permissions")
        new_perms = {
            col: st.checkbox(_pretty(col), bool(row[col]), key=f"perm_{col}")
            for col in PERM_COLS
        }

        st.subheader("Reset PIN (optional)")
        new_pin = st.text_input(
            "Enter a new 4-8 digit PIN (leave blank to keep current)",
            type="password",
            key="um_new_pin",
        ).strip()

        submitted = st.form_submit_button("💾 Review & confirm")

    # ── Queue pending changes & refresh ─────────────────────
    if submitted:
        st.session_state["um_pending"] = {
            "uid":   uid,
            "role":  new_role,
            "perms": new_perms,
            "name":  row.name,
            "email": row.email,
            "new_pin": new_pin,
        }
        st.rerun()                       # show confirmation banner

    # ── Allow quick user switch (no form) ───────────────────
    new_email = st.selectbox(
        "📧 Select user",
        email_list,
        index=email_list.index(sel_email),
        format_func=lambda e: f"{email_to_name[e]} ({e})",
        key="um_user_picker",
    )
    if new_email != sel_email:
        st.session_state["um_selected_email"] = new_email
        st.session_state.pop("um_pending", None)
        st.rerun()

    # ── Confirmation banner ─────────────────────────────────
    if "um_pending" in st.session_state:
        p = st.session_state["um_pending"]

        st.warning("### ⚠️ Confirm updates")
        blue = lambda t: f"<span style='color:#007acc'>{html.escape(t)}</span>"

        st.markdown(
            f"**User:** {html.escape(p['name'])} "
            f"{blue('(' + html.escape(p['email']) + ')')}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**New role:** {blue(p['role'])}", unsafe_allow_html=True)

        page_list = ", ".join(
            [_pretty(c) for c, v in p["perms"].items() if v]
        ) or "None"
        st.markdown(
            f"**Pages with access:** {blue(page_list)}",
            unsafe_allow_html=True,
        )

        if p["new_pin"]:
            st.markdown("**PIN will be reset.**")

        c_yes, c_no = st.columns(2)

        # ── Apply changes ───────────────────────────────────
        if c_yes.button("✅ Apply changes"):
            db = DatabaseManager()

            # role
            db.execute_command(
                "UPDATE `users` SET role = %s WHERE userid = %s",
                (p["role"], p["uid"]),
            )

            # permissions
            for col, val in p["perms"].items():
                db.execute_command(
                    f"UPDATE `users` SET {col} = %s WHERE userid = %s",
                    (val, p["uid"]),
                )

            # optional PIN reset
            if p["new_pin"]:
                if p["new_pin"].isdigit() and 4 <= len(p["new_pin"]) <= 8:
                    db.execute_command(
                        "UPDATE `users` "
                        "SET pin_hash = %s "
                        "WHERE userid  = %s",
                        (hash_pin(p["new_pin"]), p["uid"]),
                    )
                else:
                    st.error("PIN must be 4–8 digits; no changes saved.")
                    st.session_state.pop("um_pending")
                    return

            st.success("Changes saved ✅")
            _load_users.clear()          # clear both caches
            _get_perm_cols.clear()
            st.session_state.pop("um_pending")
            st.rerun()

        # ── Cancel ──────────────────────────────────────────
        if c_no.button("❌ Cancel"):
            st.session_state.pop("um_pending")
            st.rerun()


# Stand-alone debugging hook
if __name__ == "__main__":
    user_management()
