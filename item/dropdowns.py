# item/manage_dropdowns.py
"""
Tab for bulk adding / deleting the drop-down values used in the *Item* module.

Fixes:
    • After deleting values we now clear the associated widget state, so
      Streamlit doesn’t crash with “value not in options”.
    • Clears the add-textarea after successful insert.
    • Converts all data to `str` to avoid set-membership surprises.
"""

from __future__ import annotations

from typing import List

import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _normalise(values) -> List[str]:
    """Return a deduplicated, sorted `list[str]`."""
    return sorted({str(v).strip() for v in values if str(v).strip()})


# ─────────────────────────────────────────────────────────────────────────────
# Main tab
# ─────────────────────────────────────────────────────────────────────────────
def manage_dropdowns_tab() -> None:
    st.subheader("🛠️ Manage Dropdown Values")

    sections = [
        "ClassCat",
        "DepartmentCat",
        "SectionCat",
        "FamilyCat",
        "SubFamilyCat",
        "UnitType",
        "Packaging",
        "OriginCountry",
        "Manufacturer",
        "Brand",
    ]

    selected_section = st.selectbox("Select Dropdown Section", sections, key="section")

    # --- current values ---------------------------------------------------
    current_values = _normalise(item_handler.get_dropdown_values(selected_section))
    st.markdown("**Current Values:**")
    st.write(", ".join(current_values) if current_values else "—")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────
    # 1️⃣  Bulk ADD
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("### ➕ Bulk Add Values")

    add_key = f"bulk_add_{selected_section}"
    new_values_str = st.text_area("Enter one value per line", key=add_key)

    if st.button("Add Values", key=f"add_btn_{selected_section}"):
        new_values = _normalise(new_values_str.splitlines())

        if not new_values:
            st.error("❌ Please enter at least one value.")
        else:
            added, skipped = [], []
            for val in new_values:
                if val in current_values:
                    skipped.append(val)
                else:
                    item_handler.add_dropdown_value(selected_section, val)
                    added.append(val)

            if added:
                st.success(f"✅ Added: {', '.join(added)}")
            if skipped:
                st.warning(f"⚠️ Already existed (skipped): {', '.join(skipped)}")

            # clear textarea → avoid accidental duplicate inserts on rerun
            st.session_state[add_key] = ""
            st.rerun()

    st.divider()

    # ─────────────────────────────────────────────────────────────────────
    # 2️⃣  Bulk DELETE
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("### 🗑️ Bulk Delete Values")

    del_key = f"bulk_delete_{selected_section}"
    values_to_delete = st.multiselect(
        "Select values to delete", options=current_values, key=del_key
    )

    if st.button("Delete Selected Values", key=f"del_btn_{selected_section}"):
        if not values_to_delete:
            st.error("❌ Please select at least one value to delete.")
        else:
            for val in values_to_delete:
                item_handler.delete_dropdown_value(selected_section, val)
            st.success(f"✅ Deleted: {', '.join(values_to_delete)}")

            # 💡 Clear the widget state *before* rerunning so Streamlit
            # doesn’t try to keep a now-invalid selection.
            st.session_state[del_key] = []
            st.rerun()
