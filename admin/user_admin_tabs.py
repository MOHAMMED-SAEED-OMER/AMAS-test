# admin/admin_user_tabs.py

import streamlit as st
from admin.add_users import add_user_tab
from admin.edit_permissions import edit_permissions_tab
from admin.delete_users import delete_users_tab  # ← NEW

tab1, tab2, tab3 = st.tabs(["🔧 Edit Users", "➕ Add User", "🗑️ Delete User"])

with tab1:
    edit_permissions_tab()

with tab2:
    add_user_tab()

with tab3:
    delete_users_tab()
