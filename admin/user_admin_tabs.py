# admin/admin_user_tabs.py

import streamlit as st
from admin.user_management import user_management
from admin.add_users import add_user_tab
from admin.delete_users import delete_users_tab

def show_user_admin():
    tab1, tab2, tab3 = st.tabs(["🔧 Edit Users", "➕ Add User", "🗑️ Delete User"])

    with tab1:
        user_management()

    with tab2:
        add_user_tab()

    with tab3:
        delete_users_tab()
