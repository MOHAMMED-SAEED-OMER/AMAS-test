# admin/user_admin_tabs.py
import streamlit as st
from admin.user_management import user_management
from admin.add_users import add_user_tab

def show_user_admin():
    st.title("🔐 Admin: User Access Control")

    tab1, tab2 = st.tabs(["🧑‍💼 Manage Users", "➕ Add New User"])
    
    with tab1:
        user_management()

    with tab2:
        add_user_tab()
