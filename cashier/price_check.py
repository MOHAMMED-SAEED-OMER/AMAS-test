import streamlit as st
from cashier.cashier_handler import CashierHandler

cashier_handler = CashierHandler()

@st.cache_data(ttl=600)
def load_item_names():
    query = """
        SELECT ItemID, ItemNameEnglish AS ItemName, sellingprice
        FROM item
        ORDER BY ItemNameEnglish;
    """
    return cashier_handler.fetch_data(query)

def display_price_check_tab():
    st.header("🔍 Check Item Prices")

    search_option = st.radio(
        "Search by:",
        ["Barcode", "Item Name", "Item ID"],
        horizontal=True
    )

    if search_option == "Item Name":
        items_df = load_item_names()
        item_names = items_df['itemname'].tolist()

        search_input = st.selectbox("🔎 Select or type item name:", options=item_names, index=None)

        if search_input:
            result = items_df[items_df["itemname"] == search_input].iloc[0]
            st.success("✅ Item Found:")
            st.write(f"""
                - **Item ID**: {result['itemid']}
                - **Name**: {result['itemname']}
                - **Selling Price**: {result['sellingprice']:.2f}
            """)

    else:
        search_input = st.text_input(f"Enter {search_option}:")

        if search_input:
            if search_option == "Barcode":
                query = """
                    SELECT ItemID, ItemNameEnglish AS ItemName, sellingprice
                    FROM item
                    WHERE Barcode = %s;
                """
            else:  # Item ID
                query = """
                    SELECT ItemID, ItemNameEnglish AS ItemName, sellingprice
                    FROM item
                    WHERE ItemID = %s;
                """

            results = cashier_handler.fetch_data(query, (search_input,))

            if not results.empty:
                st.success("✅ Item Found:")
                for _, row in results.iterrows():
                    st.write(f"""
                    - **Item ID**: {row['itemid']}
                    - **Name**: {row['itemname']}
                    - **Selling Price**: {row['sellingprice']:.2f}
                    """)
            else:
                st.error("❌ No item found.")
