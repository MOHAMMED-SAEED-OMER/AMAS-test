import streamlit as st
from reports.sup_performance import sup_performance_tab
from reports.near_expiry import near_expiry_tab  # ✅ Added near expiry tab

def reports_page():
    st.title("📊 Reports & Analytics")

    tabs = st.tabs(["Supplier Performance", "Items Near Expiry"])  # ✅ Added new tab

    with tabs[0]:
        sup_performance_tab()
        
    with tabs[1]:
        near_expiry_tab()  # ✅ Handles near expiry items report
