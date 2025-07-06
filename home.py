# home.py – consolidated table, KPI totals, no charts, no hero banner
import base64
import pandas as pd
import streamlit as st
from db_handler import DatabaseManager


# ───────────────────────── CSS & UI helpers ─────────────────────────
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
        /* KPI cards */
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


# ─────────────────────────── data loader ───────────────────────────
@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
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


# ──────────────────────────── main page ────────────────────────────
def home() -> None:
    _inject_css()
    st.title("🏠 Inventory Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # ── KPI totals ──────────────────────────────────────────────────
    total_items   = df["itemid"].nunique()
    total_qty     = int(df["quantity"].sum())
    today         = pd.Timestamp.today().normalize()
    exp_dates     = pd.to_datetime(df["expirationdate"], errors="coerce")

    near_exp_cnt  = ((exp_dates >= today) &
                     (exp_dates <= today + pd.Timedelta(days=30))).sum()
    expired_cnt   = (exp_dates < today).sum()
    low_stock_cnt = (df["quantity"] < df["threshold"]).sum()

    _kpi_cards(
        [
            ("Items",       total_items,  "🗃️"),
            ("Total Stock", total_qty,    "📦"),
            ("Near-Expiry", near_exp_cnt, "⏳"),
            ("Expired",     expired_cnt,  "❌"),
            ("Low Stock",   low_stock_cnt,"⚠️"),
        ]
    )

    # ── inline filters ─────────────────────────────────────────────
    c_bc, c_nm = st.columns(2)
    with c_bc:
        f_bc = st.text_input("Filter by Barcode").strip()
    with c_nm:
        f_nm = st.text_input("Filter by Item Name").strip()

    fdf = df.copy()
    if f_bc:
        fdf = fdf[fdf["barcode"].str.contains(f_bc, case=False, na=False)]
    if f_nm:
        fdf = fdf[fdf["itemnameenglish"].str.contains(f_nm, case=False, na=False)]

    # ── table ──────────────────────────────────────────────────────
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
