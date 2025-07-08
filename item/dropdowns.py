# item/dropdowns.py   (id-aware, cache-safe)
from __future__ import annotations
from typing import Any, List

import streamlit as st
from item.item_handler import ItemHandler

item_handler = ItemHandler()


# ───────────────────────── helpers ─────────────────────────
def _uniq(values: list[Any]) -> List[str]:
    """deduplicate, strip, sort"""
    return sorted({str(v).strip() for v in values if str(v).strip()})


@st.cache_data(ttl=180, show_spinner=False)
def _cached_dropdown_values(section: str) -> List[str]:
    """3-min cache; caller clears() after mutations"""
    return _uniq(item_handler.get_dropdown_values(section))


# ───────────────────────── main tab ────────────────────────
def manage_dropdowns_tab() -> None:
    st.subheader("🛠️ Manage Dropdown Values")

    sections = [
        "ClassCat", "DepartmentCat", "SectionCat", "FamilyCat",
        "SubFamilyCat", "UnitType", "Packaging", "OriginCountry",
        "Manufacturer", "Brand",
    ]
    section = st.selectbox("Select Dropdown Section", sections, key="section")

    values = _cached_dropdown_values(section)
    st.markdown("**Current Values:**")
    st.write(", ".join(values) if values else "—")
    st.divider()

    # 1️⃣  Add
    st.markdown("### ➕ Bulk Add Values")
    with st.form(f"add_{section}", clear_on_submit=True):
        txt = st.text_area("One value per line")
        if st.form_submit_button("Add Values"):
            new_vals = _uniq(txt.splitlines())
            if not new_vals:
                st.error("❌ Please enter at least one value.")
            else:
                added, skipped = [], []
                with st.spinner("Adding…"):
                    for v in new_vals:
                        if v in values:
                            skipped.append(v)
                        else:
                            new_id = item_handler.add_dropdown_value(section, v)
                            if new_id:
                                added.append(f"{v} (id {new_id})")
                            else:
                                st.error(f"❌ Failed to insert “{v}” (check DB log)")

                if added:
                    st.success("✅ Added: " + ", ".join(added))
                if skipped:
                    st.warning("⚠️ Already existed: " + ", ".join(skipped))

                # invalidate cache → next rerun shows updated list
                _cached_dropdown_values.clear()          # type: ignore[attr-defined]
                st.toast("Updated!", icon="✅")

    st.divider()

    # 2️⃣  Delete
    st.markdown("### 🗑️ Bulk Delete Values")
    with st.form(f"del_{section}", clear_on_submit=True):
        to_del = st.multiselect("Select values to delete", options=values)
        if st.form_submit_button("Delete Selected Values"):
            if not to_del:
                st.error("❌ Choose at least one value.")
            else:
                with st.spinner("Deleting…"):
                    for v in to_del:
                        item_handler.delete_dropdown_value(section, v)

                st.success("✅ Deleted: " + ", ".join(to_del))
                _cached_dropdown_values.clear()          # type: ignore[attr-defined]
                st.toast("Updated!", icon="✅")
