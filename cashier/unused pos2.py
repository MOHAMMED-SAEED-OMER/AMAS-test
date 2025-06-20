import streamlit as st
import pandas as pd
from datetime import date
from cashier.cashier_handler import CashierHandler

cashier_handler = CashierHandler()

def display_pos_tab():
    st.subheader("💳 Point of Sale (Common Interface)")

    # Initialize session DataFrame for the bill if it doesn't exist.
    if "sales_table" not in st.session_state:
        columns = ["barcode", "itemid", "itemname", "quantity", "price", "total"]
        st.session_state.sales_table = pd.DataFrame(columns=columns)

    # Use separate scratch variables for inputs.
    if "barcode_scratch" not in st.session_state:
        st.session_state.barcode_scratch = ""
    if "quantity_scratch" not in st.session_state:
        st.session_state.quantity_scratch = 1

    # Create two columns for the top input row.
    col1, col2 = st.columns([3, 1])
    with col1:
        barcode_or_name = st.text_input(
            "Scan Barcode or Enter Item Name:",
            value=st.session_state.barcode_scratch,
            key="barcode_input_widget"
        )
    with col2:
        quantity_input = st.number_input(
            "Quantity",
            min_value=1,
            value=st.session_state.quantity_scratch,
            key="quantity_input_widget"
        )

    # Button to add the scanned/item-entered item.
    if st.button("➕ Add/Scan Item"):
        if barcode_or_name.strip():
            new_item = add_item_to_table(barcode_or_name.strip(), int(quantity_input))
            if new_item:
                # Append new item as a row to the sales table DataFrame.
                st.session_state.sales_table = pd.concat([
                    st.session_state.sales_table,
                    pd.DataFrame([new_item])
                ], ignore_index=True)
                st.success(f"Item '{new_item['itemname']}' added with quantity {new_item['quantity']}.")
            else:
                st.warning("❗ Item not found.")
        # Clear the scratch variables and refresh.
        st.session_state.barcode_scratch = ""
        st.session_state.quantity_scratch = 1
        st.rerun()

    st.markdown("---")

    # Display the current bill as a custom table with inline editing and remove buttons.
    if not st.session_state.sales_table.empty:
        st.markdown("### Current Bill")
        df = st.session_state.sales_table.copy()

        # Create header row.
        header_cols = st.columns([0.5, 3, 1, 1, 1, 1.5])
        header_cols[0].write("#")
        header_cols[1].write("Item")
        header_cols[2].write("Qty")
        header_cols[3].write("Price")
        header_cols[4].write("Total")
        header_cols[5].write("Action")

        new_rows = []  # to store updated rows
        # Iterate over each row and display with inline editing.
        for idx, row in df.iterrows():
            row_cols = st.columns([0.5, 3, 1, 1, 1, 1.5])
            row_cols[0].write(idx + 1)
            row_cols[1].write(row["itemname"])

            # Editable quantity (as number_input)
            new_qty = row_cols[2].number_input(
                label="",
                min_value=1.0,
                value=float(row["quantity"]),
                key=f"qty_{idx}"
            )
            # Editable price
            new_price = row_cols[3].number_input(
                label="",
                min_value=0.0,
                value=float(row["price"]),
                format="%.2f",
                key=f"price_{idx}"
            )
            # Computed total (read-only)
            total_val = float(new_qty) * float(new_price)
            row_cols[4].write(f"{total_val:.2f}")

            # Remove button:
            if row_cols[5].button("🗑️", key=f"remove_{idx}"):
                df = df.drop(idx).reset_index(drop=True)
                st.session_state.sales_table = df
                st.rerun()
            # Save the updated row values
            new_rows.append({
                "barcode": row["barcode"],
                "itemid": row["itemid"],
                "itemname": row["itemname"],
                "quantity": new_qty,
                "price": new_price,
                "total": total_val
            })

        # Save the updated table after inline edits.
        if new_rows:
            st.session_state.sales_table = pd.DataFrame(new_rows)

        subtotal = st.session_state.sales_table["total"].sum()
        st.info(f"**Subtotal:** {subtotal:.2f}")
    else:
        st.info("No items in the bill yet.")

    st.markdown("---")

    # Payment & Action Buttons
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        if st.button("💵 Cash"):
            finalize_sale("Cash")
    with col2:
        if st.button("💳 Visa Card"):
            finalize_sale("Credit Card")
    with col3:
        if st.button("❌ Cancel"):
            clear_bill()
            st.rerun()

def add_item_to_table(barcode_or_name, quantity):
    """
    Attempts to find an item using exact barcode match; if not found, performs a partial name search.
    Returns a dictionary with item details (using the provided quantity) or None if not found.
    """
    query_barcode = """
    SELECT itemid, barcode, ItemNameEnglish AS itemname, sellingprice
    FROM Item
    WHERE barcode = %s;
    """
    df_bar = cashier_handler.fetch_data(query_barcode, (barcode_or_name,))
    if not df_bar.empty:
        row = df_bar.iloc[0]
        price_val = float(row["sellingprice"] or 0.0)
        return {
            "barcode": row["barcode"],
            "itemid": row["itemid"],
            "itemname": row["itemname"],
            "quantity": quantity,
            "price": price_val,
            "total": price_val * quantity
        }
    query_name = """
    SELECT itemid, barcode, ItemNameEnglish AS itemname, sellingprice
    FROM Item
    WHERE ItemNameEnglish ILIKE %s
    ORDER BY itemname
    LIMIT 1;
    """
    df_name = cashier_handler.fetch_data(query_name, (f"%{barcode_or_name}%",))
    if not df_name.empty:
        row = df_name.iloc[0]
        price_val = float(row["sellingprice"] or 0.0)
        return {
            "barcode": row["barcode"],
            "itemid": row["itemid"],
            "itemname": row["itemname"],
            "quantity": quantity,
            "price": price_val,
            "total": price_val * quantity
        }
    return None

def finalize_sale(payment_method):
    df = st.session_state.sales_table.copy()
    if df.empty:
        st.error("Nothing to sell.")
        return

    # Build cart_items for finalize_sale from the updated table.
    cart_items = []
    for _, row in df.iterrows():
        cart_items.append({
            "itemid": int(row["itemid"]),
            "quantity": float(row["quantity"]),
            "sellingprice": float(row["price"])
        })

    sale_id = cashier_handler.finalize_sale(
        cart_items=cart_items,
        discount_rate=0.0,  # No discount for now.
        payment_method=payment_method,
        cashier=st.session_state.get("user_email", "Unknown"),
        notes="POS transaction"
    )
    if sale_id is not None:
        st.success(f"✅ Sale completed! Sale ID: {sale_id}")
        clear_bill()
        st.rerun()
    else:
        st.error("Sale failed.")

def clear_bill():
    st.session_state.sales_table = pd.DataFrame(
        columns=["barcode", "itemid", "itemname", "quantity", "price", "total"]
    )
    st.session_state.barcode_scratch = ""
    st.session_state.quantity_scratch = 1
