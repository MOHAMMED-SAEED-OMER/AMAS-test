# admin/delete_users.py

import streamlit as st
from db_handler import DatabaseManager

db = DatabaseManager()

def delete_users_tab():
    st.subheader("🗑️ Delete User")

    # Fetch all users except self or optionally admins
    user_email = st.session_state.get("user_email")
    users_df = db.fetch_data(
        "SELECT id, name, email, role FROM users WHERE email != %s ORDER BY name", 
        (user_email,)
    )

    if users_df.empty:
        st.info("No other users found.")
        return

    user_options = [
        f"{row['name']} ({row['email']}) [{row['role']}]" 
        for _, row in users_df.iterrows()
    ]

    selected = st.selectbox("Select user to delete", user_options)

    if selected:
        selected_email = selected.split("(")[-1].split(")")[0]
        selected_role = selected.split("[")[-1].split("]")[0]

        if selected_role.lower() == "admin":
            st.warning("🚫 Cannot delete users with Admin role.")
            return

        if st.button("⚠️ Permanently delete this user"):
            db.execute_command("DELETE FROM users WHERE email = %s", (selected_email,))
            st.success(f"✅ User {selected_email} has been deleted.")
            st.rerun()
