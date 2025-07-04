# admin/delete_users.py   – delete user UI (MySQL backend)

import streamlit as st
from db_handler import DatabaseManager

db = DatabaseManager()

def delete_users_tab() -> None:
    st.subheader("🗑️ Delete User")

    # Logged-in admin
    user_email = st.session_state.get("user_email")

    # Fetch all users except the current one
    try:
        users_df = db.fetch_data(
            """
            SELECT  UserID AS id, name, email, role
            FROM    `users`
            WHERE   email <> %s
            ORDER BY name
            """,
            (user_email,),
        )
    except Exception as e:
        st.error(f"❌ Failed to load user list: {e}")
        return

    if users_df.empty:
        st.info("No other users found.")
        return

    # Pretty labels for dropdown
    user_options = [
        f"{row['name']} ({row['email']}) [{row['role']}]"
        for _, row in users_df.iterrows()
    ]
    selected = st.selectbox("Select user to delete", user_options)

    if not selected:
        return

    selected_email = selected.split("(")[-1].split(")")[0]
    selected_role  = selected.split("[")[-1].split("]")[0]

    # Prevent deleting admins
    if selected_role.lower() == "admin":
        st.warning("🚫 Cannot delete users with Admin role.")
        return

    if st.button("⚠️ Permanently delete this user"):
        try:
            db.execute_command(
                "DELETE FROM `users` WHERE email = %s",
                (selected_email,),
            )
            st.success(f"✅ User {selected_email} has been deleted.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Deletion failed: {e}")
