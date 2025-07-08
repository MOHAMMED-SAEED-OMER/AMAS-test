# selling_area/shelf.py  – fast & crash-safe shelf view
from __future__ import annotations

import pandas as pd
import streamlit as st

from selling_area.shelf_handler import ShelfHandler

handler = ShelfHandler()

# ────────────────────────────────────────────────────────────────
# cached loader: refresh every 30 s, cast away extension dtypes
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _load_shelf_df() -> pd.DataFrame:
    df = handler.get_shelf_items()
    # Arrow + nullable Int64 can trigger allocator bugs → cast to plain dtypes
    return df.convert_dtypes().infer_objects()


# ────────────────────────────────────────────────────────────────
# main tab
# ────────────────────────────────────────────────────────────────
def shelf_tab() -> None:
    st.subheader("📚 Current Shelf Items")

    shelf_df = _load_shelf_df()

    if shelf_df.empty:
        st.info("ℹ️ No items currently in the selling area.")
    else:
        st.dataframe(shelf_df, use_container_width=True, hide_index=True)


# manual run
if __name__ == "__main__":
    shelf_tab()
