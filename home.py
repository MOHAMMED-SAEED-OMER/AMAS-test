# home.py  – one big inventory table, inline filters, no charts
import base64
import pandas as pd
import streamlit as st
from db_handler import DatabaseManager

# ───────────────────────────  CSS / helper funcs ────────────────────────────
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


def _image_uri(blob: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(blob).decode()}" if blob else None


# ─────────────────────────────  Data loader  ────────────────────────────────
@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """
    Pull inventory, item, PO, and supplier data.
    • Uses inv.datereceived  (your DESCRIBE shows this column).
    • Joins to purchase orders (po) → supplier for a readable name.
      Change table/column names if yours differ.
    """
    query = """
        SELECT  i.ItemID,
                i.Barcode,
                i.ItemPicture,
                i.ItemNameEnglish,
                inv.Quantity,
                inv.DateReceived        AS ReceiveDate,
                s.SupplierName,
                inv.ExpirationDate,
                inv.StorageLocation,
                i.ClassCat, i.DepartmentCat, i.SectionCat,
                i.FamilyCat, i.SubFamilyCat,
                i.Threshold, i.AverageRequired
        FROM        `inventory`      AS inv
        JOIN        `item`           AS i   ON inv.ItemID = i.ItemID
        LEFT JOIN   `purchaseorder`  AS po  ON inv.POID   = po.POID          -- ↙ adjust if your PO table is named differently
        LEFT JOIN   `supplier`       AS s   ON po.SupplierID = s.SupplierID
    """
    db = DatabaseManager()
    df = db.fetch_data(query)

    if df.empty:
        return df

    # normalise column names
    df.columns = df.columns.str.lower()

    # convert / format
    df["itempicture"] = df["itempicture"].apply(_image_uri)
    df["quantity"]    = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")

    return df


# ─────────────────────────────-  Main page  ────────────────────────────────
def home() -> None:
    _inject_css()
    st.title("🏠 Inventory Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    st.markdown(
        "<div class='hero'>"
        "<h2>Inventory Portal</h2>"
        "<p>Search and manage all stock in one place.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── inline filters ──────────────────────────────────────────────────────
    col_barcode, col_name = st.columns(2)
    with col_barcode:
        f_barcode = st.text_input("Filter by Barcode").strip()
    with col_name:
        f_name = st.text_input("Filter by Item Name").strip()

    fdf = df.copy()
    if f_barcode:
        fdf = fdf[fdf["barcode"].str.contains(f_barcode, case=False, na=False)]
    if f_name:
        fdf = fdf[fdf["itemnameenglish"].str.contains(f_name, case=False, na=False)]

    # ── column order & table ───────────────────────────────────────────────
    col_order = [
        "itemid",
        "itempicture",
        "barcode",
        "itemnameenglish",
        "quantity",
        "receivedate",
        "suppliername",
    ]
    col_order += [c for c in fdf.columns if c not in col_order]  # append the rest

    st.data_editor(
        fdf[col_order],
        hide_index=True,
        use_container_width=True,
        column_config={
            "itempicture":   st.column_config.ImageColumn("Pic", width="small"),
            "itemid":        st.column_config.NumberColumn("ID", width="small"),
            "barcode":       st.column_config.TextColumn("Barcode"),
            "itemnameenglish": st.column_config.TextColumn("English Name", width="medium"),
            "quantity":      st.column_config.NumberColumn("Qty", width="small"),
            "receivedate":   st.column_config.DatetimeColumn("Receive Date"),
            "suppliername":  st.column_config.TextColumn("Supplier"),
        },
        num_rows="dynamic",
    )

    st.download_button(
        "Download CSV",
        fdf[col_order].to_csv(index=False).encode(),
        "inventory_full.csv",
        "text/csv",
    )
