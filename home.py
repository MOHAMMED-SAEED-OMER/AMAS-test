# home.py  ── AMAS Inventory Dashboard
import base64
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from db_handler import DatabaseManager

# ---------------------------------------------------------------------------
# ── Streamlit setup ---------------------------------------------------------
st.set_page_config(
    page_title="AMAS Inventory",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# ── Helper functions --------------------------------------------------------
def _inject_css() -> None:
    """Minimal custom CSS for dark mode polish."""
    if st.session_state.get("_home_css_done"):
        return

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

        html, body, [class*="css"], .stApp {
            font-family: 'Roboto', sans-serif;
            background: var(--background-color);
        }
        .hero {
            background: #1ABC9C;
            color: #ffffff;
            border-radius: 8px;
            padding: 2rem 1rem;
            text-align: center;
            margin-bottom: 2rem;
        }
        .stDataFrame tbody tr:nth-child(even) {
            background: rgba(255,255,255,0.03);  /* zebra rows */
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    """Convert raw bytes to base64 data-URI for ImageColumn."""
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else None


@st.cache_resource(show_spinner=False)
def _get_db() -> DatabaseManager:
    """Keep a single DB connection for the whole session."""
    return DatabaseManager()


@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """Pull inventory and aggregate quantities across duplicate item–exp date–location rows."""
    q = """
        SELECT i.ItemID, i.ItemNameEnglish, i.ClassCat, i.DepartmentCat,
               i.SectionCat, i.FamilyCat, i.SubFamilyCat, i.ItemPicture,
               inv.Quantity, inv.ExpirationDate, inv.StorageLocation,
               i.Threshold, i.AverageRequired
        FROM Inventory inv
        JOIN Item i ON inv.ItemID = i.ItemID
    """
    db = _get_db()
    df = db.fetch_data(q)

    if df.empty:
        return df

    df.columns = df.columns.str.lower()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    df["itempicture"] = df["itempicture"].apply(_image_uri)

    return (
        df.groupby(["itemid", "expirationdate", "storagelocation"], as_index=False)
        .agg(
            {
                "itemnameenglish": "first",
                "classcat": "first",
                "departmentcat": "first",
                "sectioncat": "first",
                "familycat": "first",
                "subfamilycat": "first",
                "threshold": "first",
                "averagerequired": "first",
                "itempicture": "first",
                "quantity": "sum",
            }
        )
    )


def _filter_multiselect(label: str, options: Iterable[str], key: str) -> list[str]:
    opts = sorted({o for o in options if pd.notna(o)})
    return st.sidebar.multiselect(label, options=opts, key=key) if opts else []


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("🔎 Filters")
    search = st.sidebar.text_input("Search Item Name", key="inv_search")

    classes = _filter_multiselect("Class", df["classcat"].unique(), "f_class")
    depts = _filter_multiselect("Department", df["departmentcat"].unique(), "f_dept")
    sections = _filter_multiselect("Section", df["sectioncat"].unique(), "f_sec")

    f = df.copy()
    if search:
        f = f[f["itemnameenglish"].str.contains(search, case=False, na=False)]
    if classes:
        f = f[f["classcat"].isin(classes)]
    if depts:
        f = f[f["departmentcat"].isin(depts)]
    if sections:
        f = f[f["sectioncat"].isin(sections)]

    return f


# ---------------------------------------------------------------------------
# ── Main page ---------------------------------------------------------------
def home() -> None:
    _inject_css()
    st.title("📦 Inventory Dashboard")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # ── Hero -----------------------------------------------------------------
    st.markdown(
        "<div class='hero'>"
        "<img src='assets/logo.png' width='160'/>"
        "<h2>AMAS Inventory Portal</h2>"
        "<p>Stay on top of stock levels across your business.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── KPIs -----------------------------------------------------------------
    items = len(df)
    total_qty = int(df["quantity"].sum())
    low_stock_cnt = (df["quantity"] < df["threshold"]).sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("🗃️ Items", items)
    k2.metric("📦 Total Stock", total_qty)
    k3.metric("⚠️ Low Stock", low_stock_cnt)

    if low_stock_cnt:
        st.warning(f"⚠️  {low_stock_cnt} items are below their threshold!")

    # ── Quick insights -------------------------------------------------------
    tab_classes, tab_departments = st.tabs(["Top Classes", "Departments Share"])

    with tab_classes:
        top_classes = (
            df.groupby("classcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
            .head(10)
        )
        if not top_classes.empty:
            st.subheader("Top Classes by Stock")
            st.plotly_chart(
                px.bar(
                    top_classes,
                    x="classcat",
                    y="quantity",
                    color="classcat",
                ).update_layout(showlegend=False),
                use_container_width=True,
            )

    with tab_departments:
        dept_data = (
            df.groupby("departmentcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
        )
        if not dept_data.empty:
            st.subheader("Stock Distribution by Department")
            st.plotly_chart(
                px.pie(dept_data, values="quantity", names="departmentcat"),
                use_container_width=True,
            )

    # ── Details & actions ----------------------------------------------------
    with st.expander("🔧 Details & Actions", expanded=False):
        show_images = st.checkbox("Show Images", value=True)
        filtered = _apply_filters(df)

        # Low-stock table ------------------------------------------------------
        low_df = (
            filtered.groupby("itemid", as_index=False)
            .agg(
                {
                    "itemnameenglish": "first",
                    "quantity": "sum",
                    "threshold": "first",
                    "averagerequired": "first",
                    "itempicture": "first",
                }
            )
            .query("quantity < threshold")
            .assign(reorderamount=lambda d: d["averagerequired"] - d["quantity"])
        )

        if not low_df.empty:
            st.subheader("⚠️ Low Stock Items")
            cols = [
                "itempicture",
                "itemnameenglish",
                "quantity",
                "threshold",
                "reorderamount",
            ]
            if not show_images:
                cols.remove("itempicture")

            st.data_editor(
                low_df[cols],
                column_config=(
                    {"itempicture": st.column_config.ImageColumn("Item Picture")}
                    if show_images
                    else None
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("All stock levels are sufficient.")

        # Full inventory grid --------------------------------------------------
        st.subheader("📋 Full Inventory")
        grid_cols = [
            "itempicture",
            "itemnameenglish",
            "classcat",
            "departmentcat",
            "sectioncat",
            "familycat",
            "subfamilycat",
            "quantity",
            "threshold",
            "averagerequired",
            "expirationdate",
            "storagelocation",
        ]
        if not show_images:
            grid_cols.remove("itempicture")

        st.data_editor(
            filtered[grid_cols],
            column_config=(
                {"itempicture": st.column_config.ImageColumn("Item Picture")}
                if show_images
                else None
            ),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
        )

        # CSV download ---------------------------------------------------------
        if st.download_button(
            "⬇️  Download CSV",
            data=filtered.to_csv(index=False),
            file_name="inventory_data.csv",
            mime="text/csv",
        ):
            st.toast("✅ CSV downloaded", icon="📄")


# ---------------------------------------------------------------------------
# ── Run as standalone script ------------------------------------------------
if __name__ == "__main__":
    home()
