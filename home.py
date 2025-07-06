# home.py – one big inventory table, inline filters, no charts
import base64
import pandas as pd
import streamlit as st
from db_handler import DatabaseManager

# ───────────────────────── CSS helper ──────────────────────────
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


def _img_uri(blob: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(blob).decode()}" if blob else None


# ───────────────────── data loader (cached) ────────────────────
@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """
    Pull inventory and item data.
    Uses inv.DateReceived (rename here if your column differs).
    """
    query = """
        SELECT  i.ItemID,
                i.Barcode,
                i.ItemPicture,
                i.ItemNameEnglish,
                inv.Quantity,
                inv.DateReceived  AS ReceiveDate,
                inv.ExpirationDate,
                inv.StorageLocation,
                i.ClassCat, i.DepartmentCat, i.SectionCat,
                i.FamilyCat, i.SubFamilyCat,
                i.Threshold, i.AverageRequired
        FROM  `inventory` AS inv
        JOIN  `item`      AS i  ON inv.ItemID = i.ItemID
    """
    db = DatabaseManager()
    df = db.fetch_data(query)
    if df.empty:
        return df

    df.columns = df.columns.str.lower()
    df["itempicture"] = df["itempicture"].apply(_img_uri)
    df["quantity"]    = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    return df


# ─────────────────────────── main page ─────────────────────────
def home() -> None:
    _inject_css()
    st.title("🏠 Inventory Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    st.markdown(
        "<div class='hero'><h2>Inventory Portal</h2>"
        "<p>Search and manage all stock in one place.</p></div>",
        unsafe_allow_html=True,
    )

    # inline filters
    col_bc, col_nm = st.columns(2)
    with col_bc:
        f_bc = st.text_input("Filter by Barcode").strip()
    with col_nm:
        f_nm = st.text_input("Filter by Item Name").strip()

    fdf = df.copy()
    if f_bc:
        fdf = fdf[fdf["barcode"].str.contains(f_bc, case=False, na=False)]
    if f_nm:
        fdf = fdf[fdf["itemnameenglish"].str.contains(f_nm, case=False, na=False)]

    # ordered table (Supplier column removed for now)
    col_order = [
        "itemid", "itempicture", "barcode", "itemnameenglish",
        "quantity", "receivedate"
    ] + [c for c in fdf.columns if c not in (
        "itemid","itempicture","barcode","itemnameenglish",
        "quantity","receivedate")]

    st.data_editor(
        fdf[col_order],
        hide_index=True,
        use_container_width=True,
        column_config={
            "itempicture":    st.column_config.ImageColumn("Pic", width="small"),
            "itemid":         st.column_config.NumberColumn("ID", width="small"),
            "barcode":        st.column_config.TextColumn("Barcode"),
            "itemnameenglish":st.column_config.TextColumn("English Name", width="medium"),
            "quantity":       st.column_config.NumberColumn("Qty", width="small"),
            "receivedate":    st.column_config.DatetimeColumn("Receive Date"),
        },
        num_rows="dynamic",
    )

    st.download_button(
        "Download CSV",
        fdf[col_order].to_csv(index=False).encode(),
        "inventory_full.csv",
        "text/csv",
    )
