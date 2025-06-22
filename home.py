import base64
from typing import Iterable
import pandas as pd
import plotly.express as px
import streamlit as st
from db_handler import DatabaseManager

db = DatabaseManager()

# ---------- helpers ---------------------------------------------------------
def _inject_css() -> None:
    if st.session_state.get("_home_css_done"):
        return
    st.markdown("""
        <style>
        html,body,[class*="css"],.stApp{
            font-family:'Roboto',sans-serif;
            background:linear-gradient(to bottom right,#f8f9fb,#e3e6f0);
        }
        .hero{background:linear-gradient(90deg,#5c8df6,#a66ef6);
              color:white;border-radius:8px;padding:2rem 1rem;
              text-align:center;margin-bottom:2rem;}
        </style>
    """, unsafe_allow_html=True)
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else None


@st.cache_data(show_spinner="Loading inventory …")
def _load_inventory() -> pd.DataFrame:
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

    return (df.groupby(
        ["itemid", "expirationdate", "storagelocation"], as_index=False
    ).agg({
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
    }))


def _filter_multiselect(label: str, options: Iterable[str], key: str) -> list[str]:
    opts = sorted({o for o in options if pd.notna(o)})
    return st.multiselect(label, options=opts, key=key) if opts else []


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    search = st.text_input("🔍 Search Item Name", key="inv_search")
    c1, c2, c3 = st.columns(3)
    with c1:
        classes = _filter_multiselect("Class", df["classcat"].unique(), "f_class")
    with c2:
        depts = _filter_multiselect("Department", df["departmentcat"].unique(), "f_dept")
    with c3:
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


# ---------- main page -------------------------------------------------------
def home() -> None:
    _inject_css()
    st.title("🏠 Home")

    df = _load_inventory()
    if df.empty:
        st.info("No inventory data available.")
        return

    # --- hero ----------------------------------------------------------------
    st.markdown(
        "<div class='hero'>"
        "<img src='assets/logo.png' width='180'/>"
        "<h2>Inventory Portal</h2>"
        "<p>Stay on top of stock levels across your business.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # --- KPI row -------------------------------------------------------------
    items = len(df)
    total_qty = int(df["quantity"].sum())
    low_stock_cnt = (df["quantity"] < df["threshold"]).sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("Items", items)
    k2.metric("Total Stock", total_qty)
    k3.metric("Low Stock", low_stock_cnt)

    # --- quick insights (two tabs) ------------------------------------------
    t1, t2 = st.tabs(["Top Classes", "Departments Share"])

    with t1:
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

    with t2:
        dept_pie = (
            df.groupby("departmentcat", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
        )
        if not dept_pie.empty:
            st.plotly_chart(
                px.pie(dept_pie, values="quantity", names="departmentcat"),
                use_container_width=True,
            )

    # --- details (collapsible) ----------------------------------------------
    with st.expander("🔧 Details & Actions", expanded=False):
        show_images = st.checkbox("Show Images", value=True)
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
            .assign(reorderamount=lambda d: d["averagerequired"] - d["quantity"])
        )

        if not low_df.empty:
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

        # full inventory
        st.subheader("📦 Full Inventory")
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
            column_config={
                "itempicture": st.column_config.ImageColumn("Item Picture")
            }
            if show_images
            else None,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
        )

        st.download_button(
            "Download CSV",
            data=filtered.to_csv(index=False),
            file_name="inventory_data.csv",
            mime="text/csv",
        )
