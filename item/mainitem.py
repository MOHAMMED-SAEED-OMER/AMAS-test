import streamlit as st
from item.add_item import add_item_tab
from item.bulk_add import bulk_add_tab
from item.edit_item import edit_item_tab
from item.dropdowns import manage_dropdowns_tab  # ✅ Corrected Import
from item.add_pictures import add_pictures_tab  # ✅ New Import

def item_page():
    """Page for managing inventory items."""
    st.title("📦 Item Management")

    # ✅ Define tabs for item management
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "➕ Add Item", "📂 Bulk Add", "✏️ Edit Item", "📸 Add Pictures", "📋 Manage Dropdowns"
    ])

    with tab1:
        add_item_tab()  # ✅ Handles adding new items

    with tab2:
        bulk_add_tab()  # ✅ Handles bulk item upload via Excel

    with tab3:
        edit_item_tab()  # ✅ Handles editing existing items

    with tab4:
        add_pictures_tab()  # ✅ New Add Pictures tab

    with tab5:
        manage_dropdowns_tab()  # ✅ Handles dropdown management
