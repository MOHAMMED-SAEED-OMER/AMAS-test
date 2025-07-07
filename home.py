# home.py – consolidated view, raw table, two Excel downloads
import base64
from io import BytesIO

import pandas as pd
import streamlit as st
from db_handler import DatabaseManager


# ───────────────────── CSS & UI helpers ──────────────────────
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
        .kpi-card{
            background:#fff;border-radius:10px;
            box-shadow:0 3px 8px rgba(0,0,0,0.06);
            padding:1rem;display:flex;align-items:center;gap:0.75rem;
        }
        .kpi-icon{font-size:1.8rem;line-height:1}
        .kpi-value{font-size:1.4rem;font-weight:700;margin:0}
        .kpi-label{font-size:0.85rem;color:#666;margin:0}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _img_uri(blob: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(blob).decode()}" if blob else None


def _kpi_cards(kpis: list[tuple[str, int | float, str]]) -> None:
    cols = st.columns(len(kpis))
    for col, (label, val, icon) in zip(cols, kpis):
        col.markdown(
            f"""
            <div class="kpi-card">
              <div class="kpi-icon">{icon}</div>
              <div>
                <p class="kpi-value">{val:,}</p>
                <p class="kpi-label">{label}</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ─────────────────────── data loaders ────────────────────────
@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory_view() -> pd.DataFrame:
    """Joined view for the main table."""
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
    df = DatabaseManager().fetch_data(query)
    if df.empty:
        return df

    df.columns = df.columns.str.lower()
    df["itempicture"] = df["itempicture"].apply(_img_uri)
    df["quantity"]    = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    return df


@st.cache_data(show_spinner=False)
def _load_inventory_raw() -> pd.DataFrame:
    """Exact columns from inventory table."""
    return DatabaseManager().fetch_data("SELECT * FROM `inventory`")


# ────────────────────────── helpers ──────────────────────────
def _excel_from_df(df: pd.DataFrame, sheet: str) -> BytesIO:
    """Return BytesIO of Excel file (drops image columns, casts ids to str)."""
    cleaned = df.copy()
    # drop any image / picture columns
    pic_cols = [c for c in cleaned.columns if "picture" in c or "image" in c]
    cleaned = cleaned.drop(columns=pic_cols)
    # cast id / barcode to str if present
    for col in ("itemid", "barcode"):
        if col in cleaned.columns:
            cleaned[col] = cleaned[col].astype(str)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wrt:
        cleaned.to_excel(wrt, index=False, sheet_name=sheet)
    buf.seek(0)
    return buf


# ─────────────────────────── main page ───────────────────────
def home() -> None:
    _inject_css()
    st.title("🏠 Inventory Home")

    view_df = _load_inventory_view()
    if view_df.empty:
        st.info("No inventory data available.")
        return

    # KPIs
    total_items = view_df["itemid"].nunique()
    total_qty   = int(view_df["quantity"].sum())
    today       = pd.Timestamp.today().normalize()
    exp_dates   = pd.to_datetime(view_df["expirationdate"], errors="coerce")

    near_exp   = ((exp_dates >= today) &
                  (exp_dates <= today + pd.Timedelta(days=30))).sum()
    expired    = (exp_dates < today).sum()
    low_stock  = (view_df["quantity"] < view_df["threshold"]).sum()

    _kpi_cards(
        [
            ("Items",       total_items, "🗃️"),
            ("Total Stock", total_qty,   "📦"),
            ("Near-Expiry", near_exp,    "⏳"),
            ("Expired",     expired,     "❌"),
            ("Low Stock",   low_stock,   "⚠️"),
        ]
    )

    # Filters
    c_bc, c_nm = st.columns(2)
    with c_bc:
        f_bc = st.text_input("Filter by Barcode").strip()
    with c_nm:
        f_nm = st.text_input("Filter by Item Name").strip()

    fdf = view_df.copy()
    if f_bc:
        fdf = fdf[fdf["barcode"].str.contains(f_bc, case=False, na=False)]
    if f_nm:
        fdf = fdf[fdf["itemnameenglish"].str.contains(f_nm, case=False, na=False)]

    # Main table
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
    )

    # Download main view
    st.download_button(
        "Download Inventory View (Excel)",
        data=_excel_from_df(fdf, "Inventory_View"),
        file_name="inventory_view.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # Raw inventory table
    st.subheader("🗄️ Raw `inventory` Table")
    raw_df = _load_inventory_raw()
    if raw_df.empty:
        st.info("Inventory table is empty.")
        return

    st.data_editor(
        raw_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
    )

    st.download_button(
        "Download Raw Inventory (Excel)",
        data=_excel_from_df(raw_df, "Inventory_Raw"),
        file_name="inventory_raw.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
