# item/dropdowns.py
"""
Manage Dropdown Values tab (Streamlit ≥ 1.28, cache-optimised).

• No manual st.rerun() – avoids double-rerun loops.
• Fetch list of values via @st.cache_data (3-min TTL) for snappy UI.
"""

from __future__ import annotations

from typing import Any, List

import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _uniq(values: list[Any]) -> List[str]:
    """Normalise → strip → deduplicate → sorted list."""
    return sorted({str(v).strip() for v in values if str(v).strip()})


@st.cache_data(ttl=180, show_spinner=False)   # 3-minute cache per section
def _cached_dropdown_values(section: str) -> List[str]:
    return _uniq(item_handler.get_dropdown_values(section))


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
    # Current values (cached)
    # ---------------------------------------------------------------------
    current_values = _cached_dropdown_values(selected_section)
    st.markdown("**Current Values:**")
    st.write(", ".join(current_values) if current_values else "—")

    st.divider()

    # ---------------------------------------------------------------------
    # 1️⃣  Bulk ADD
    # ---------------------------------------------------------------------
    st.markdown("### ➕ Bulk Add Values")
    with st.form(f"add_form_{selected_section}", clear_on_submit=True):
        new_values_str = st.text_area("Enter one value per line")
        submitted_add = st.form_submit_button("Add Values")

        if submitted_add:
            new_values = _uniq(new_values_str.splitlines())

            if not new_values:
                st.error("❌ Please enter at least one value.")
            else:
                added, skipped = [], []
                with st.spinner("Adding…"):
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

                # Clear the cache for this section so next rerun shows fresh list
                _cached_dropdown_values.clear()         # type: ignore[attr-defined]

    st.divider()

    # ---------------------------------------------------------------------
    # 2️⃣  Bulk DELETE
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
                with st.spinner("Deleting…"):
                    for val in values_to_delete:
                        item_handler.delete_dropdown_value(selected_section, val)
                st.success(f"✅ Deleted: {', '.join(values_to_delete)}")

                # Invalidate cache so updated list is fetched automatically
                _cached_dropdown_values.clear()         # type: ignore[attr-defined]
