# cashier/price_check.py
import streamlit as st
from cashier.cashier_handler import CashierHandler

cashier_handler = CashierHandler()

# ────────────────────────── helpers ──────────────────────────
def _fmt_price(val) -> str:
    """Return price as '12.34' or 'N/A' when None / NULL."""
    return "N/A" if val is None else f"{float(val):.2f}"

# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def load_item_names():
    """
    Return catalogue (itemid, itemname, sellingprice) for name dropdown.
    """
    return cashier_handler.fetch_data(
        """
        SELECT  itemid,
                itemnameenglish AS itemname,
                sellingprice
        FROM    `item`
        ORDER BY itemnameenglish
        """
    )

# ─────────────────────────────────────────────────────────────
def display_price_check_tab():
    st.header("🔍 Check Item Prices")

    search_option = st.radio(
        "Search by:",
        ["Barcode", "Item Name", "Item ID"],
        horizontal=True,
    )

    # ---------- Item-Name dropdown ----------
    if search_option == "Item Name":
        items_df = load_item_names()
        item_names = items_df["itemname"].tolist()

        search_input = st.selectbox(
            "🔎 Select or type item name:",
            options=item_names,
            index=None,
        )

        if search_input:
            result = items_df[items_df["itemname"] == search_input].iloc[0]
            st.success("✅ Item Found:")
            st.write(
                f"""
                - **Item ID**: {result['itemid']}
                - **Name**: {result['itemname']}
                - **Selling Price**: {_fmt_price(result['sellingprice'])}
                """
            )

    # ---------- Barcode / Item-ID text box ----------
    else:
        search_input = st.text_input(f"Enter {search_option}:").strip()

        if search_input:
            if search_option == "Barcode":
                query = """
                    SELECT itemid, itemnameenglish AS itemname, sellingprice
                    FROM   `item`
                    WHERE  barcode = %s
                """
            else:  # Item ID
                query = """
                    SELECT itemid, itemnameenglish AS itemname, sellingprice
                    FROM   `item`
                    WHERE  itemid = %s
                """

            results = cashier_handler.fetch_data(query, (search_input,))

            if not results.empty:
                st.success("✅ Item Found:")
                for _, row in results.iterrows():
                    st.write(
                        f"""
                        - **Item ID**: {row['itemid']}
                        - **Name**: {row['itemname']}
                        - **Selling Price**: {_fmt_price(row['sellingprice'])}
                        """
                    )
            else:
                st.error("❌ No item found.")
