# admin/user_management.py
import streamlit as st
from db_handler import DatabaseManager
from auth_utils import hash_pin          # ✅  hashing helper

# ────────────────────────── discover permission columns ──────────────────────────
@st.cache_data(ttl=600)
def _discover_perm_cols() -> list[str]:
    db = DatabaseManager()
    q = """
        SELECT column_name
        FROM   information_schema.columns
        WHERE  table_name = 'users' AND column_name ILIKE 'canaccess%'
        ORDER  BY column_name;
    """
    try:
        return db.fetch_data(q)["column_name"].tolist()
    except Exception:
        return [
            "canaccesshome", "canaccessitems", "canaccessreceive",
            "canaccesspo", "canaccessreports", "canaccesssellingarea",
            "canaccesscashier", "canaccessfinance", "canaccessreturns",
            "canaccessshelfmap", "canaccessissues"
        ]


PERM_COLS = _discover_perm_cols()
_pretty   = lambda c: c.replace("canaccess", "").title()

# ────────────────────────── cached user list ──────────────────────────
@st.cache_data(ttl=600)
def load_users(col_str: str):
    db = DatabaseManager()
    return db.fetch_data(f"SELECT {col_str} FROM users ORDER BY name;")

# ────────────────────────── main page ──────────────────────────
def user_management() -> None:
    st.title("👤 User Management")

    # ---- fetch users -------------------------------------------------
    col_list = ["userid", "name", "email", "role"] + PERM_COLS
    users_df = load_users(", ".join(col_list))
    if users_df.empty:
        st.warning("No users found."); return

    email_map = dict(zip(users_df.email, users_df.userid))
    name_map  = dict(zip(users_df.email, users_df.name))
    emails    = list(email_map.keys())

    sel_email = st.session_state.get("um_selected_email", emails[0])
    if sel_email not in emails: sel_email = emails[0]
    st.session_state["um_selected_email"] = sel_email

    row = users_df[users_df.email == sel_email].iloc[0]
    uid = int(row.userid)

    st.subheader(f"Editing: **{row['name']}** ({row['email']})")

    # ---- edit form ---------------------------------------------------
    with st.form("edit_permissions_form"):
        new_role = st.selectbox(
            "Role", ["User", "Admin"],
            index=0 if row.role == "User" else 1,
            key="um_role",
        )

        st.subheader("Access Permissions")
        new_perms = {
            col: st.checkbox(_pretty(col), bool(row[col]), key=f"perm_{col}")
            for col in PERM_COLS
        }

        # >>> NEW – optional PIN reset <<<
        st.subheader("Reset PIN (optional)")
        new_pin = st.text_input(
            "Enter a new 4-8 digit PIN (leave blank to keep current)",
            type="password", key="um_new_pin"
        )

        submitted = st.form_submit_button("💾 Review & Confirm")

    # ---- stash pending changes --------------------------------------
    if submitted:
        st.session_state["um_pending"] = {
            "uid":   uid,
            "role":  new_role,
            "perms": new_perms,
            "name":  row["name"],
            "email": row["email"],
            "new_pin": new_pin.strip(),
        }
        st.rerun()

    # ---- select another user ----------------------------------------
    new_email = st.selectbox(
        "📧 Select User", emails,
        index=emails.index(sel_email),
        format_func=lambda e: f"{name_map[e]} ({e})",
        key="um_user_picker",
    )
    if new_email != sel_email:
        st.session_state["um_selected_email"] = new_email
        st.session_state.pop("um_pending", None)
        st.rerun()

    # ---- confirmation banner ----------------------------------------
    if "um_pending" in st.session_state:
        p = st.session_state["um_pending"]

        st.warning("### ⚠️ Confirm updates")
        blue = lambda t: f"<span style='color:#007acc'>{t}</span>"

        st.markdown(f"**User:** {p['name']} {blue('(' + p['email'] + ')')}", unsafe_allow_html=True)
        st.markdown(f"**New role:** {blue(p['role'])}", unsafe_allow_html=True)

        pages = ", ".join([_pretty(c) for c,v in p["perms"].items() if v]) or "None"
        st.markdown(f"**Pages with access:** {blue(pages)}", unsafe_allow_html=True)

        if p["new_pin"]:
            st.markdown("**PIN will be reset.**")

        c_yes, c_no = st.columns(2)
        if c_yes.button("✅ Apply changes"):
            db = DatabaseManager()

            # role update
            db.execute_command(
                "UPDATE users SET role = %s WHERE userid = %s",
                (p["role"], p["uid"])
            )

            # permissions update
            for col,val in p["perms"].items():
                db.execute_command(
                    f"UPDATE users SET {col} = %s WHERE userid = %s",
                    (val, p["uid"])
                )

            # optional PIN reset
            if p["new_pin"]:
                if p["new_pin"].isdigit() and 4 <= len(p["new_pin"]) <= 8:
                    db.execute_command(
                        "UPDATE users SET pin_hash = %s WHERE userid = %s",
                        (hash_pin(p["new_pin"]), p["uid"])
                    )
                else:
                    st.error("PIN must be 4-8 digits; no changes saved.")
                    st.session_state.pop("um_pending"); return

            st.success("Changes saved ✅")
            load_users.clear()          # clear cache
            st.session_state.pop("um_pending")
            st.rerun()

        if c_no.button("❌ Cancel"):
            st.session_state.pop("um_pending")
            st.rerun()

# run standalone
if __name__ == "__main__":
    user_management()
