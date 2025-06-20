import base64
from typing import Iterable

import pandas as pd
import plotly.express as px
import streamlit as st

from db_handler import DatabaseManager


db = DatabaseManager()


def _inject_css() -> None:
    """Add styling to make the dashboard feel modern."""
    if st.session_state.get("_home_css_done"):
        return

    st.markdown(
        """
        <style>
        html, body, [class*="css"], .stApp {
            font-family: 'Roboto', sans-serif;
            background: linear-gradient(to bottom right,#f8f9fb,#e3e6f0);
        }
        .section-card {
            background:white;
            padding:1.25rem;
            border-radius:10px;
            box-shadow:0 4px 8px rgba(0,0,0,0.05);
            margin-bottom:1.5rem;
        }
        .metric-card {
            background:#eef4fb;
            padding:0.6rem 1rem;
            border-radius:8px;
            text-align:center;
        }
        .hero {
            background:linear-gradient(90deg,#5c8df6,#a66ef6);
            color:white;
            border-radius:8px;
            padding:2rem 1rem;
            text-align:center;
            margin-bottom:2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_home_css_done"] = True


def _image_uri(data: bytes | None) -> str | None:
    if data:
        return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
    return None


def _load_inventory() -> pd.DataFrame:
    """Fetch inventory data and aggregate quantities."""
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
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    df["itempicture"] = df["itempicture"].apply(_image_uri)

    df = df.groupby(
        ["itemid", "expirationdate", "storagelocation"],
        as_index=False,
    ).agg(
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

    return df


def _filter_multiselect(label: str, options: Iterable[str], key: str) -> list[str]:
    opts = sorted({o for o in options if pd.notna(o)})
    if not opts:
        return []
    return st.multiselect(label, options=opts, key=key)


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    search = st.text_input("Search Item Name", key="inv_search")

    c1, c2, c3 = st.columns(3)
    with c1:
        classes = _filter_multiselect("Class", df["classcat"].unique(), "filter_class")
    with c2:
        depts = _filter_multiselect(
            "Department", df["departmentcat"].unique(), "filter_dept"
        )
    with c3:
        sections = _filter_multiselect(
            "Section", df["sectioncat"].unique(), "filter_section"
        )

    filtered = df.copy()
    if search:
        filtered = filtered[filtered["itemnameenglish"].str.contains(search, case=False, na=False)]
    if classes:
        filtered = filtered[filtered["classcat"].isin(classes)]
    if depts:
        filtered = filtered[filtered["departmentcat"].isin(depts)]
    if sections:
        filtered = filtered[filtered["sectioncat"].isin(sections)]

    return filtered


def _dashboard_tab(df: pd.DataFrame) -> None:
    _inject_css()
    with st.container():
        st.markdown(
            "<div class='hero'>"
            "<img src='assets/logo.png' width='200'/><h2>Inventory Portal</h2>"
            "<p>Stay on top of stock levels across your business.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    if df.empty:
        st.info("No inventory data available.")
        return

    total_qty = int(df["quantity"].sum()) if "quantity" in df.columns else 0
    classes = df["classcat"].nunique()

    col1, col2, col3 = st.columns(3)
    col1.metric("Items", len(df))
    col2.metric("Total Stock", total_qty)
    col3.metric("Classes", classes)

    chart_df = (
        df.groupby("classcat", as_index=False)["quantity"]
        .sum()
        .sort_values("quantity", ascending=False)
        .head(10)
    )
    if not chart_df.empty:
        fig = px.bar(
            chart_df,
            x="classcat",
            y="quantity",
            color="classcat",
            title="Top Classes by Stock",
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Highlights")
    st.markdown(
        "- **Live stock updates**\n"
        "- **Low stock** notifications\n"
        "- **Exportable reports**"
    )


def _inventory_tab(df: pd.DataFrame) -> None:
    _inject_css()
    if df.empty:
        st.info("No inventory data to display.")
        return

    total_qty = df["quantity"].sum()
    low_stock = (
        df["quantity"] < df["threshold"]
    ).sum() if "threshold" in df.columns else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Items", len(df))
    m2.metric("Total Stock", int(total_qty))
    m3.metric("Low Stock", int(low_stock))

    show_images = st.checkbox("Show Images", value=True)

    chart_df = (
        df.groupby("departmentcat", as_index=False)["quantity"].sum().sort_values(
            "quantity", ascending=False
        )
    )
    if not chart_df.empty:
        fig = px.pie(
            chart_df,
            values="quantity",
            names="departmentcat",
            title="Stock by Department",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Filters")
    filtered = _apply_filters(df)

    st.markdown("#### Low Stock Items")
    req = {"itemid", "quantity", "threshold", "averagerequired"}
    missing = req - set(filtered.columns)
    if missing:
        st.warning(f"Missing columns: {missing}")
    else:
        grouped = filtered.groupby("itemid", as_index=False).agg(
            {
                "itemnameenglish": "first",
                "quantity": "sum",
                "threshold": "first",
                "averagerequired": "first",
                "itempicture": "first",
            }
        )
        low_df = grouped[grouped["quantity"] < grouped["threshold"]].copy()
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
            column_config = {
                "itemnameenglish": "Item Name",
                "quantity": "Quantity",
                "threshold": "Threshold",
                "reorderamount": "Reorder Amount",
            }
            if show_images:
                column_config["itempicture"] = st.column_config.ImageColumn("Item Picture")

            st.data_editor(
                low_df[cols],
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("All stock levels are sufficient.")

    st.markdown("#### Full Inventory")
    columns = [
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
        columns.remove("itempicture")

    config = {
        "itemnameenglish": "Item Name",
        "classcat": "Class",
        "departmentcat": "Department",
        "sectioncat": "Section",
        "familycat": "Family",
        "subfamilycat": "Sub-Family",
        "quantity": "Quantity",
        "threshold": "Threshold",
        "averagerequired": "Average Required",
        "expirationdate": "Expiration Date",
        "storagelocation": "Storage Location",
    }
    if show_images:
        config["itempicture"] = st.column_config.ImageColumn("Item Picture")

    st.data_editor(
        filtered[columns],
        column_config=config,
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


def home() -> None:
    """Render the Home page with Welcome and Inventory tabs."""
    st.title("🏠 Home")

    df = _load_inventory()

    tab_dash, tab_inventory = st.tabs(["Welcome", "Inventory Data"])

    with tab_dash:
        _dashboard_tab(df)

    with tab_inventory:
        _inventory_tab(df)
