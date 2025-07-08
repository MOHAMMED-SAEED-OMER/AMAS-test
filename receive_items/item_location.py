# item/item_location.py
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from receive_items.receive_handler import ReceiveHandler

receive_handler = ReceiveHandler()


# ────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────
def _rerun() -> None:
    """Streamlit rerun (works on both new and old versions)."""
    if hasattr(st, "rerun"):          # Streamlit ≥ 1.28
        st.rerun()
    else:
        st.experimental_rerun()       # pragma: no cover


@st.cache_data(ttl=60, show_spinner=False)
def load_items() -> pd.DataFrame:
    """Cache inventory + locations for 60 s."""
    df = receive_handler.get_items_with_locations_and_expirations()
    if "storagelocation" in df.columns:
        df["storagelocation"] = df["storagelocation"].replace("", pd.NA)
    return df


def update_location(item_id: int, new_loc: str) -> None:
    """DB update + cache invalidation."""
    receive_handler.update_item_location(item_id, new_loc)
    load_items.clear()         # type: ignore[attr-defined]


# ────────────────────────────────────────────────────────────────
# main tab
# ────────────────────────────────────────────────────────────────
def item_location_tab() -> None:
    st.header("🏷️ Item Locations")

    items_df = load_items()

    if items_df.empty:
        st.info("No inventory data to show.")
        return

    if "storagelocation" not in items_df.columns:
        st.error("Column 'storagelocation' is missing – please check the query alias.")
        return

    # ── Section 1 : items WITHOUT a location ──────────────────────
    missing_df = items_df[items_df["storagelocation"].isna()]

    st.subheader("❗ Items without a storage location")
    if missing_df.empty:
        st.success("Great! All items have a location.")
    else:
        st.dataframe(missing_df, use_container_width=True)

    # ── Section 2 : Manage / update locations ─────────────────────
    st.markdown("---")
    st.subheader("✏️ Update Storage Location")

    if items_df.empty:
        st.info("No items available to update.")
        return

    # Use a form so the rerun is automatic and the widgets reset safely
    with st.form("update_location_form", clear_on_submit=True):
        item_ids = items_df["itemid"].tolist()
        sel_item = st.selectbox(
            "Select Item ID",
            options=item_ids,
            format_func=lambda x: f"ID {x}",
        )
        new_loc = st.text_input("New Storage Location")

        submitted = st.form_submit_button("Update Location")

    if not submitted:
        return

    update_location(sel_item, new_loc)
    st.success("Location updated.")
    _rerun()


# ── quick manual test ───────────────────────────────────────────
if __name__ == "__main__":
    item_location_tab()
