# home.py  – streamlined single-page dashboard (no global st.set_page_config)

import base64
from typing import Iterable

import pandas as pd
import plotly.express as px
import streamlit as st

from db_handler import DatabaseManager

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
def _inject_css() -> None:
    """Add once-per-session CSS."""
    if st.session_state.get("_home_css_done"):
        return
    st.markdown(
        """
        <style>
        html,body,[class*="css"],.stApp{
            font-family:'Roboto',sans-serif;
            background:linear-gradient(to bottom right,#f8f9fb,#e3e6f0);
        }
        .hero{
            background:linear-gradient(90deg,#5c8df6,#a66ef6);
            color:#fff;border-radius:8px;padding:2rem 1rem;
            text-align:center;margin-bottom:2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else None


@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
    """Fetch and aggregate inventory records from PostgreSQL."""
    query = """
        SELECT i.ItemID, i.ItemNameEnglish, i.ClassCat, i.DepartmentCat,
               i.SectionCat, i.FamilyCat, i.SubFamilyCat, i.ItemPicture,
               inv.Quantity, inv.ExpirationDate, inv.StorageLocation,
               i.Threshold, i.AverageRequired
        FROM Inventory inv
        JOIN Item i ON inv.ItemID = i.ItemID
    """
    db = DatabaseManager()
    df = db.fetch_data(query)
    if df.empty:
        return df

    df.columns = df.columns.str.lower()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    df["itempicture"] = df["itempicture"].apply(_image_uri)

    return (
        df.groupby(["itemid", "expirationdate", "storagelocation"], as_index=False)
        .agg({
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
        })
    )


def _filter_multiselect(label: str, options: Iterable[str], key: str) -> list[str]:
    opts = sorted({o for o in options if pd.notna(o)})
    return st.sidebar.multiselect(label, options=opts, key=key) if opts else []


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Sidebar search + category filters."""
    st.sidebar.header("🔎 Filters")
    search = st.sidebar.text_input("Search Item Name", key="inv_search")
    classes = _filter_multiselect("Class", df["classcat"].unique(), "f_class")
    depts = _filter_multiselect("Department", df["departmentcat"].unique(), "f_dept")
    sections = _filter_multiselect("Section", df["sectioncat"].unique(), "f_sec")

    filt = df.copy()
    if search:
        filt = filt[filt["itemnameenglish"].str.contains(search, case=False, na=False)]
    if classes:
        filt = filt[filt["classcat"].isin(classes)]
    if depts:
        filt = filt[filt["departmentcat"].isin(depts)]
    if sections:
        filt = filt[filt["sectioncat"].isin(sections)]

    return filt


# ──────────────────────────────────────────────────────────────────────────────
# main entry
# ──────────────────────────────────────────────────────────────────────────────
def home() -> None:
    """Render the Inventory Home page (single tab)."""
    _inject_css()
    st.title("🏠 Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # ── hero ──────────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='hero'>"
        "<img src='assets/logo.png' width='180'/>"
        "<h2>Inventory Portal</h2>"
        "<p>Stay on top of stock levels across your business.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── KPI row ───────────────────────────────────────────────────────────────
    items      = len(df)
    total_qty  = int(df["quantity"].sum())
    low_count  = (df["quantity"] < df["threshold"]).sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("🗃️ Items", items)
    c2.metric("📦 Total Stock", total_qty)
    c3.metric("⚠️ Low Stock", low_count)

    if low_count > 0:
        st.warning(f"{low_count} items are below their threshold.")

    # ── quick insight charts (two tabs) ───────────────────────────────────────
    tab_bar, tab_pie = st.tabs(["Top Classes", "Departments Share"])

    with tab_bar:
        top_classes = (
            df.groupby("classcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
            .head(10)
        )
        if not top_classes.empty:
            st.plotly_chart(
                px.bar(top_classes, x="classcat", y="quantity", color="classcat"),
                use_container_width=True,
            )

    with tab_pie:
        dept_pie = (
            df.groupby("departmentcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
        )
        if not dept_pie.empty:
            st.plotly_chart(
                px.pie(dept_pie, names="departmentcat", values="quantity"),
                use_container_width=True,
            )

    # ── details & actions ─────────────────────────────────────────────────────
    with st.expander("🔧 Details & Tables", expanded=False):
        show_images = st.sidebar.checkbox("Show Images", value=True, key="show_img")

        filtered = _apply_filters(df)

        # low-stock table
        low_df = (
            filtered.groupby("itemid", as_index=False)
            .agg({
                "itemnameenglish": "first",
                "quantity": "sum",
                "threshold": "first",
                "averagerequired": "first",
                "itempicture": "first",
            })
            .query("quantity < threshold")
        )
        if not low_df.empty:
            low_df["reorderamount"] = low_df["averagerequired"] - low_df["quantity"]
            cols = [
                "itempicture",
                "itemnameenglish",
                "quantity",
                "threshold",
                "reorderamount",
            ]
            if not show_images:
                cols.remove("itempicture")

            st.subheader("⚠️ Low Stock Items")
            st.data_editor(
                low_df[cols],
                column_config={
                    "itempicture": st.column_config.ImageColumn("Item Picture"),
                    "itemnameenglish": "Item Name",
                    "quantity": "Qty",
                    "threshold": "Threshold",
                    "reorderamount": "Reorder",
                }
                if show_images
                else None,
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("All stock levels are sufficient.")

        # full inventory table
        st.subheader("📋 Full Inventory")
        full_cols = [
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
            full_cols.remove("itempicture")

        st.data_editor(
            filtered[full_cols],
            column_config=(
                {"itempicture": st.column_config.ImageColumn("Item Picture")}
                if show_images
                else None
            ),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
        )

        # CSV download + toast
        if st.download_button(
            "Download CSV",
            data=filtered.to_csv(index=False),
            file_name="inventory_data.csv",
            mime="text/csv",
        ):
            st.toast("✅ Inventory CSV downloaded")

# End of file
