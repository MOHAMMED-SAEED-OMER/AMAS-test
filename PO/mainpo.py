import streamlit as st
from PO.autopo import auto_po_tab
from PO.manualpo import manual_po_tab
from PO.trackpo import track_po_tab
from PO.archivedpo import archived_po_tab  # ✅ Import new Archived PO tab

def po_page():
    st.title("🛒 Purchase Order Management")

    tabs = st.tabs(["Auto PO", "Manual PO", "Track PO", "Archived PO"])  # ✅ Added Archived PO tab

    with tabs[0]:
        auto_po_tab()
        
    with tabs[1]:
        manual_po_tab()  # ✅ Handles Manual PO Creation

    with tabs[2]:
        track_po_tab()  # ✅ Handles Tracking of POs

    with tabs[3]:
        archived_po_tab()  # ✅ New Archived PO Tab
