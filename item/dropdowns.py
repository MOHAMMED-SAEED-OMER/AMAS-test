# item/dropdowns.py
"""
Manage Dropdown Values tab (stable form-based version).

Why this won’t crash:
    • No code writes to `st.session_state[widget_key]` after the widget exists.
    • We wrap add & delete actions in `st.form(..., clear_on_submit=True)`,
      which clears text-areas / multiselects automatically once the form is
      successfully submitted.
    • No need for manual flags, reruns are still used to refresh the list.
"""

from __future__ import annotations

from typing import List, Any

import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _uniq(values: list[Any]) -> List[str]:
    """Normalise → strip → deduplicate → sorted list."""
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

    # ---------------------------------------------------------------------
    # Current values
    # ---------------------------------------------------------------------
    current_values = _uniq(item_handler.get_dropdown_values(selected_section))
    st.markdown("**Current Values:**")
    st.write(", ".join(current_values) if current_values else "—")

    st.divider()

    # ---------------------------------------------------------------------
    # 1️⃣  Bulk ADD (form clears textarea automatically)
    # ---------------------------------------------------------------------
    st.markdown("### ➕ Bulk Add Values")

    with st.form(f"add_form_{selected_section}", clear_on_submit=True):
        new_values_str = st.text_area("Enter one value per line")
        submitted_add  = st.form_submit_button("Add Values")

        if submitted_add:
            new_values = _uniq(new_values_str.splitlines())

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

                st.experimental_rerun()   # refresh list

    st.divider()

    # ---------------------------------------------------------------------
    # 2️⃣  Bulk DELETE (form clears selection automatically)
    # ---------------------------------------------------------------------
    st.markdown("### 🗑️ Bulk Delete Values")

    with st.form(f"del_form_{selected_section}", clear_on_submit=True):
        values_to_delete = st.multiselect(
            "Select values to delete", options=current_values
        )
        submitted_del = st.form_submit_button("Delete Selected Values")

        if submitted_del:
            if not values_to_delete:
                st.error("❌ Please select at least one value to delete.")
            else:
                for val in values_to_delete:
                    item_handler.delete_dropdown_value(selected_section, val)
                st.success(f"✅ Deleted: {', '.join(values_to_delete)}")
                st.experimental_rerun()   # refresh list
