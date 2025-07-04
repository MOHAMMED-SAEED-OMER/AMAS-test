# PO/autopo.py  – Auto-generate POs from low-stock inventory (MySQL backend)

import datetime
from io import BytesIO
from typing import Dict, List

import pandas as pd
import streamlit as st

from PO.po_handler import POHandler

po_handler = POHandler()


# ─────────────────────────────────────────────────────────────
# Main tab
# ─────────────────────────────────────────────────────────────
def auto_po_tab() -> None:
    """Automatically generates purchase orders based on low-stock inventory."""
    st.subheader("📦 Automatic Purchase Order by Supplier")

    low_stock_df = _get_low_stock_items()
    if low_stock_df.empty:
        st.success("✅ All stock levels are sufficient. No purchase orders needed.")
        return

    st.write("Below are items grouped by supplier. Generate POs as needed.")
    grouped = low_stock_df.groupby("supplierid")

    for supplier_id, group in grouped:
        supplier_name = group.iloc[0]["suppliername"]
        with st.expander(f"📦 Supplier: {supplier_name}"):
            st.write("**Items needing reorder from this supplier:**")
            st.dataframe(
                group[
                    ["itemnameenglish", "currentquantity", "threshold", "neededquantity"]
                ],
                use_container_width=True,
            )

            # delivery date/time picker
            st.write(f"### 📅 Expected Delivery Date & Time for {supplier_name}")
            col_date, col_time = st.columns(2)
            delivery_date = col_date.date_input(
                "Select Date", key=f"date_{supplier_id}", min_value=datetime.date.today()
            )
            delivery_time = col_time.time_input(
                "Select Time", key=f"time_{supplier_id}", value=datetime.time(9, 0)
            )

            exp_datetime = datetime.datetime.combine(delivery_date, delivery_time)

            if st.button(
                f"Accept & Send Order to {supplier_name}", key=f"send_{supplier_id}"
            ):
                items_for_supplier: List[Dict[str, int]] = [
                    {
                        "item_id": int(row["itemid"]),
                        "quantity": int(row["neededquantity"]),
                        "estimated_price": None,
                    }
                    for _, row in group.iterrows()
                ]
                created_by = st.session_state.get("user_email", "Unknown")
                po_handler.create_manual_po(
                    supplier_id, exp_datetime, items_for_supplier, created_by
                )
                st.success(
                    f"✅ Purchase Order created for {supplier_name} successfully by {created_by}!"
                )
                st.stop()


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _get_low_stock_items() -> pd.DataFrame:
    """
    Return a DataFrame of items where currentquantity < threshold,
    enriched with supplierid / suppliername and neededquantity.
    """
    # MySQL-safe quoting (back-ticks) + lower-case table names
    query = """
        SELECT  i.ItemID            AS itemid,
                i.ItemNameEnglish   AS itemnameenglish,
                i.Threshold         AS threshold,
                i.AverageRequired   AS averagerequired,
                COALESCE(SUM(inv.Quantity), 0) AS currentquantity
        FROM    `item`       AS i
        LEFT JOIN `inventory` AS inv ON i.ItemID = inv.ItemID
        GROUP BY i.ItemID, i.ItemNameEnglish, i.Threshold, i.AverageRequired
    """
    df = po_handler.fetch_data(query)
    if df.empty:
        return pd.DataFrame()

    # low-stock filter
    df = df[df["currentquantity"] < df["threshold"]].copy()
    if df.empty:
        return df

    df["neededquantity"] = df["averagerequired"] - df["currentquantity"]
    df = df[df["neededquantity"] > 0].copy()
    if df.empty:
        return df

    # map each item → first supplier
    supplier_map = _get_first_supplier_for_items()
    df["supplierid"] = df["itemid"].map(supplier_map)
    df.dropna(subset=["supplierid"], inplace=True)
    df["supplierid"] = df["supplierid"].astype(int)

    # supplier name lookup
    sup_df = po_handler.get_suppliers()
    sup_lookup = dict(zip(sup_df["supplierid"], sup_df["suppliername"]))
    df["suppliername"] = df["supplierid"].map(sup_lookup).fillna("No Supplier")

    return df


def _get_first_supplier_for_items() -> Dict[int, int]:
    """
    Return {item_id: supplier_id} mapping (first supplier found per item).
    """
    mapping_df = po_handler.get_item_supplier_mapping()
    first_map: Dict[int, int] = {}
    if not mapping_df.empty:
        for row in mapping_df.itertuples():
            item_id = getattr(row, "itemid")
            sup_id = getattr(row, "supplierid")
            if item_id not in first_map:
                first_map[item_id] = sup_id
    return first_map
