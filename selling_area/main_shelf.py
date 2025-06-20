import streamlit as st
from selling_area.shelf import shelf_tab
from selling_area.transfer import transfer_tab
from selling_area.alerts import alerts_tab
from selling_area.shelf_manage import shelf_manage_tab

def main_shelf_page():
    tabs = st.tabs(["Shelf", "Transfer", "Alerts", "Manage Settings"])
    
    with tabs[0]:
        shelf_tab()

    with tabs[1]:
        transfer_tab()

    with tabs[2]:
        alerts_tab()

    with tabs[3]:
        shelf_manage_tab()  # The new tab for Shelf Threshold & Average
