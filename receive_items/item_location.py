import streamlit as st
import pandas as pd
from receive_items.receive_handler import ReceiveHandler

receive_handler = ReceiveHandler()

def item_location_tab():
    st.header("🏷️ Item Locations")

    # Fetch inventory/location data
    items_df = receive_handler.get_items_with_locations_and_expirations()

    if items_df.empty:
        st.info("No inventory data to show.")
        return

    # Ensure the expected column exists
    if "storagelocation" not in items_df.columns:
        st.error("Column 'storagelocation' is missing – please check the query alias.")
        return

    # Treat blank strings as missing
    items_df["storagelocation"] = items_df["storagelocation"].replace("", pd.NA)

    # ─────────────────── Section 1 : Items WITHOUT a location ───────────────────
    missing_df = items_df[items_df["storagelocation"].isna()]

    st.subheader("❗ Items without a storage location")
    if missing_df.empty:
        st.success("Great! All items have a location.")
    else:
        st.dataframe(missing_df, use_container_width=True)

    # ─────────────────── Section 2 : Manage / update locations ───────────────────
    st.markdown("---")
    st.subheader("✏️ Update Storage Location")

    item_ids = items_df["itemid"].tolist()
    if not item_ids:
        st.info("No items available to update.")
        return

    sel_item = st.selectbox(
        "Select Item ID",
        options=item_ids,
        format_func=lambda x: f"ID {x}"
    )

    new_loc = st.text_input("New Storage Location")
    if st.button("Update Location"):
        receive_handler.update_item_location(sel_item, new_loc)
        st.success("Location updated. Reloading data …")
        st.rerun()

# Run directly for quick manual test
if __name__ == "__main__":
    item_location_tab()
