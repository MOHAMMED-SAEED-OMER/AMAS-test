# home.py  – streamlined single-page dashboard
import base64
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from db_handler import DatabaseManager

# --------------------------------------------------------------------- setup
st.set_page_config(
    page_title="AMAS Inventory",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

db = DatabaseManager()

# ----------------------------------------------------------------- utilities
def _inject_css() -> None:
    """Inject lightweight CSS; runs once per session."""
    if st.session_state.get("_home_css_done"):
        return

    st.markdown(
        """
        <style>
        html, body, [class*="css"], .stApp {
            font-family: 'Roboto', sans-serif;
            background: linear-gradient(to bottom right,#f8f9fb,#e3e6f0);
        }
        .hero {
            background:linear-gradient(90deg,#5c8df6,#a66ef6);
            color:white;
            border-radius:8px;
            padding:2rem 1rem;
            text-align:center;
            margin-bottom:2rem;
        }
        /* subtle card effect for metrics */
        div[data-testid="stMetric"] {
            background: #ffffff20;
            border: 1px solid #ffffff40;
            border-radius: 8px;
            padding: 0.4rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    return (
        f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
        if data
        else None
    )


@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """Fetch inventory and aggregate quantities."""
    q = """
        SELECT i.ItemID, i.ItemNameEnglish, i.ClassCat, i.DepartmentCat,
               i.SectionCat, i.FamilyCat, i.SubFamilyCat, i.ItemPicture,
               inv.Quantity, inv.ExpirationDate, inv.StorageLocation,
               i.Threshold, i.AverageRequired
        FROM Inventory inv
        JOIN Item i ON inv.ItemID = i.ItemID
    """
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


# ----------------------------------------------------------------- sidebar filters
def _sidebar_filters(df: pd.DataFrame) -> dict[str, Iterable[str | None]]:
    """Render sidebar controls and return selections."""
    with st.sidebar:
        st.header("🔍 Filters")
        search = st.text_input("Item name contains …", key="inv_search")

        classes = _multiselect("Class", df["classcat"].unique(), "f_class")
        depts = _multiselect("Department", df["departmentcat"].unique(), "f_dept")
        sections = _multiselect("Section", df["sectioncat"].unique(), "f_sec")

        show_images = st.checkbox("Show images", value=True)

    return {
        "search": search,
        "classes": classes,
        "depts": depts,
        "sections": sections,
        "show_images": show_images,
    }


def _multiselect(label: str, options: Iterable[str], key: str) -> list[str]:
    opts = sorted({o for o in options if pd.notna(o)})
    return st.multiselect(label, options=opts, key=key) if opts else []


def _apply_filters(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    f = df.copy()
    if flt["search"]:
        f = f[
            f["itemnameenglish"].str.contains(flt["search"], case=False, na=False)
        ]
    if flt["classes"]:
        f = f[f["classcat"].isin(flt["classes"])]
    if flt["depts"]:
        f = f[f["departmentcat"].isin(flt["depts"])]
    if flt["sections"]:
        f = f[f["sectioncat"].isin(flt["sections"])]
    return f


# ----------------------------------------------------------------- main page
def home() -> None:
    _inject_css()
    st.title("🏠 Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # ------------- HERO -----------------------------------------------------
    st.markdown(
        """
        <div class='hero'>
            <img src='assets/logo.png' width='180' />
            <h2>Inventory Portal</h2>
            <p>Stay on top of stock levels across your business.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------- KPI row --------------------------------------------------
    items = len(df)
    total_qty = int(df["quantity"].sum())
    low_stock_cnt = int((df["quantity"] < df["threshold"]).sum())

    k1, k2, k3 = st.columns(3)
    k1.metric("🗃️ Items", items)
    k2.metric("📦 Total Stock", total_qty)
    k3.metric("⚠️ Low Stock", low_stock_cnt)

    if low_stock_cnt:
        st.warning(f"⚠️ {low_stock_cnt} items below threshold")

    # ------------- quick insights (tabs) ------------------------------------
    t1, t2 = st.tabs(["Top Classes", "Departments Share"])

    with t1:
        cls_df = (
            df.groupby("classcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
            .head(10)
        )
        if not cls_df.empty:
            st.subheader("Top Classes by Stock")
            st.plotly_chart(
                px.bar(cls_df, x="classcat", y="quantity", color="classcat"),
                use_container_width=True,
            )

    with t2:
        dept_df = (
            df.groupby("departmentcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
        )
        if not dept_df.empty:
            st.subheader("Stock Share by Department")
            st.plotly_chart(
                px.pie(dept_df, values="quantity", names="departmentcat"),
                use_container_width=True,
            )

    # ------------- details expander -----------------------------------------
    filters = _sidebar_filters(df)
    filtered = _apply_filters(df, filters)

    with st.expander("🔧 Details & Actions", expanded=False):
        # ------- low stock table --------------------------------------------
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
        )
        if not low_df.empty:
            low_df["reorderamount"] = (
                low_df["averagerequired"] - low_df["quantity"]
            )
            st.subheader("⚠️ Low Stock Items")
            _show_table(
                low_df,
                [
                    "itempicture",
                    "itemnameenglish",
                    "quantity",
                    "threshold",
                    "reorderamount",
                ],
                filters["show_images"],
            )
        else:
            st.success("All stock levels are sufficient.")

        # ------- full inventory --------------------------------------------
        st.subheader("📦 Full Inventory")
        _show_table(
            filtered,
            [
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
            ],
            filters["show_images"],
        )

        # ------- CSV download ----------------------------------------------
        clicked = st.download_button(
            "Download CSV",
            data=filtered.to_csv(index=False),
            file_name="inventory_data.csv",
            mime="text/csv",
        )
        if clicked:
            st.toast("✅ CSV downloaded")


# ----------------------------------------------------------------- helpers
def _show_table(df: pd.DataFrame, cols: list[str], show_images: bool) -> None:
    """Utility to display a data_editor with optional image column."""
    if not show_images and "itempicture" in cols:
        cols = [c for c in cols if c != "itempicture"]

    column_config = {
        "itemnameenglish": "Item Name",
        "classcat": "Class",
        "departmentcat": "Department",
        "sectioncat": "Section",
        "familycat": "Family",
        "subfamilycat": "Sub-Family",
        "quantity": "Quantity",
        "threshold": "Threshold",
        "averagerequired": "Avg Required",
        "expirationdate": "Expiration",
        "storagelocation": "Storage",
        "reorderamount": "Reorder",
    }
    if show_images and "itempicture" in cols:
        column_config["itempicture"] = st.column_config.ImageColumn("Item Picture")

    st.data_editor(
        df[cols],
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
    )
