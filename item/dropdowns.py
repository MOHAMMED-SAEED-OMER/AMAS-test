# item/dropdowns.py
"""
Manage Dropdown Values tab.

Fixes:
    • Eliminates StreamlitAPIException caused by writing to st.session_state
      keys that belong to widgets after they were instantiated.
    • Uses “clear-on-next-run” flags so text-area / multiselect can be reset
      without breaking Streamlit’s rules.
"""

from __future__ import annotations

from typing import List, Any

import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _uniq(values: list[str] | list[Any]) -> List[str]:
    """Normalise → strip → deduplicate → sort."""
    return sorted({str(v).strip() for v in values if str(v).strip()})


def _maybe_clear_widget(key: str, flag_key: str) -> None:
    """
    If *flag_key* exists in session_state, remove *key* (the widget’s value)
    BEFORE the widget is created, then drop the flag.
    """
    if st.session_state.get(flag_key):
        st.session_state.pop(key, None)
        st.session_state.pop(flag_key, None)


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

    # Build widget keys (+ matching “please clear” flag names)
    add_key = f"bulk_add_{selected_section}"
    del_key = f"bulk_delete_{selected_section}"
    add_flag = f"clear___{add_key}"
    del_flag = f"clear___{del_key}"

    # Clear widget state *before* widgets are drawn if flagged
    _maybe_clear_widget(add_key, add_flag)
    _maybe_clear_widget(del_key, del_flag)

    # ---------------------------------------------------------------------
    # Current values
    # ---------------------------------------------------------------------
    current_values = _uniq(item_handler.get_dropdown_values(selected_section))
    st.markdown("**Current Values:**")
    st.write(", ".join(current_values) if current_values else "—")

    st.divider()

    # ---------------------------------------------------------------------
    # 1️⃣  Bulk ADD
    # ---------------------------------------------------------------------
    st.markdown("### ➕ Bulk Add Values")

    new_values_str = st.text_area("Enter one value per line", key=add_key)

    if st.button("Add Values", key=f"btn_add_{selected_section}"):
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

            # Ask next run to clear the textarea, then rerun
            st.session_state[add_flag] = True
            st.experimental_rerun()

    st.divider()

    # ---------------------------------------------------------------------
    # 2️⃣  Bulk DELETE
    # ---------------------------------------------------------------------
    st.markdown("### 🗑️ Bulk Delete Values")

    values_to_delete = st.multiselect(
        "Select values to delete", options=current_values, key=del_key
    )

    if st.button("Delete Selected Values", key=f"btn_del_{selected_section}"):
        if not values_to_delete:
            st.error("❌ Please select at least one value to delete.")
        else:
            for val in values_to_delete:
                item_handler.delete_dropdown_value(selected_section, val)
            st.success(f"✅ Deleted: {', '.join(values_to_delete)}")

            # Ask next run to clear the multiselect selection, then rerun
            st.session_state[del_flag] = True
            st.experimental_rerun()
