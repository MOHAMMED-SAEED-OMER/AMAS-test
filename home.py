# home.py  – clean dashboard, one big inventory table, no charts
import base64
from typing import Iterable

import pandas as pd
import streamlit as st

from db_handler import DatabaseManager


# ──────────────────────────── CSS / UI helpers ─────────────────────────────
def _inject_css() -> None:
    if st.session_state.get("_home_css_done"):
        return
    st.markdown(
        """
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
              rel="stylesheet">
        <style>
        html,body,[class*="css"],.stApp{
            font-family:'Roboto',sans-serif;
            background:#f8f9fb;
        }
        .hero{
            background:linear-gradient(90deg,#5c8df6,#a66ef6);
            color:#fff;border-radius:8px;text-align:center;
            padding:2rem 1rem;margin-bottom:1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else None


# ──────────────────────── Data retrieval & caching ─────────────────────────
@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """
    Pull inventory joined to item & supplier. Adjust column names if yours differ.
    """
    query = """
        SELECT  i.ItemID,
                i.Barcode,
                i.ItemPicture,
                i.ItemNameEnglish,
                inv.Quantity,
                inv.ReceiveDate,                 -- make sure this column exists
                s.SupplierName,                  -- via JOIN below
                inv.ExpirationDate,
                inv.StorageLocation,
                i.ClassCat, i.DepartmentCat, i.SectionCat,
                i.FamilyCat, i.SubFamilyCat,
                i.Threshold, i.AverageRequired
        FROM        `inventory` AS inv
        JOIN        `item`      AS i  ON inv.ItemID = i.ItemID
        LEFT JOIN   `supplier`  AS s  ON inv.SupplierID = s.SupplierID
    """
    db = DatabaseManager()
    df = db.fetch_data(query)

    if df.empty:
        return df

    df.columns = df.columns.str.lower()
    df["itempicture"] = df["itempicture"].apply(_image_uri)
    df["quantity"]    = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    return df


# ────────────────────────────────  Main page  ──────────────────────────────
def home() -> None:
    _inject_css()
    st.title("🏠 Inventory Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # ── Hero banner ─────────────────────────────────────────────────────────
    st.markdown(
        "<div class='hero'>"
        "<h2>Inventory Portal</h2>"
        "<p>Search and manage all stock in one place.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Inline filters ──────────────────────────────────────────────────────
    col_barcode, col_name = st.columns(2)
    with col_barcode:
        f_barcode = st.text_input("Filter by Barcode").strip()
    with col_name:
        f_name = st.text_input("Filter by Item Name").strip()

    filtered = df.copy()
    if f_barcode:
        filtered = filtered[filtered["barcode"].str.contains(f_barcode, case=False, na=False)]
    if f_name:
        filtered = filtered[filtered["itemnameenglish"].str.contains(f_name, case=False, na=False)]

    # ── Re-order & display table ────────────────────────────────────────────
    col_order = [
        "itemid", "itempicture", "barcode", "itemnameenglish",
        "quantity", "receivedate", "suppliername"
    ]
    # append the rest of the columns in original order
    other_cols = [c for c in filtered.columns if c not in col_order]
    final_df = filtered[col_order + other_cols]

    st.data_editor(
        final_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "itempicture": st.column_config.ImageColumn("Pic", width="small"),
            "itemid":      st.column_config.NumberColumn("ID", width="small"),
            "barcode":     st.column_config.TextColumn("Barcode"),
            "itemnameenglish": st.column_config.TextColumn("English Name", width="medium"),
            "quantity":    st.column_config.NumberColumn("Qty", width="small"),
            "receivedate": st.column_config.DatetimeColumn("Receive Date"),
            "suppliername": st.column_config.TextColumn("Supplier"),
        },
        num_rows="dynamic",
    )

    st.download_button(
        "Download as CSV",
        data=final_df.to_csv(index=False),
        file_name="inventory_full.csv",
        mime="text/csv",
    )
