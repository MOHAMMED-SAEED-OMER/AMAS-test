import streamlit as st

from selling_area.shelf_handler   import ShelfHandler
from selling_area.scan_transfer   import scan_transfer_tab, BarcodeShelfHandler

shelf_handler   = ShelfHandler()
barcode_handler = BarcodeShelfHandler()


def transfer_tab():
    st.subheader("📤 Transfer Items from Inventory to Shelf")

    tabs = st.tabs(["📷 Barcode Scan", "✍️ Manual Transfer"])

    # ──────────────── Barcode Scan tab ──────────────────────────────
    with tabs[0]:
        scan_transfer_tab(barcode_handler)

    # ──────────────── Manual Transfer tab ───────────────────────────
    with tabs[1]:
        if "transfer_cart" not in st.session_state:
            st.session_state.transfer_cart = []

        inventory_items = shelf_handler.get_inventory_items()

        if inventory_items.empty:
            st.info("Inventory is empty. No items available for transfer.")
            return

        # --- search ---
        search_query = st.text_input("🔍 Search items by name:")

        if search_query:
            filtered_items = inventory_items[
                inventory_items["itemname"].str.contains(search_query, case=False, na=False)
            ]
        else:
            filtered_items = inventory_items.head(20)

        if filtered_items.empty:
            st.warning("No items match your search."); return

        st.write("### Select Item to Add to Transfer Cart")

        selected_row = st.selectbox(
            "Select item:",
            options=filtered_items.itertuples(),
            format_func=lambda x:
                f"{x.itemname} | Exp: {x.expirationdate} "
                f"| Cost: {x.cost_per_unit:.2f} "
                f"| Avail: {x.quantity} | Loc: {x.storagelocation or 'N/A'}"
        )

        quantity = st.number_input(
            "Transfer Quantity:",
            min_value=1,
            max_value=int(selected_row.quantity),
            value=1,
            step=1,
        )

        if st.button("➕ Add to Transfer Cart"):
            cart_item = {
                "itemid":         int(selected_row.itemid),
                "itemname":       selected_row.itemname,
                "expirationdate": selected_row.expirationdate,
                "quantity":       int(quantity),
                "available_qty":  int(selected_row.quantity),
                "cost_per_unit":  float(selected_row.cost_per_unit),   # NEW
            }

            already = any(
                ci["itemid"] == cart_item["itemid"]
                and ci["expirationdate"] == cart_item["expirationdate"]
                for ci in st.session_state.transfer_cart
            )
            if already:
                st.warning("⚠️ This item is already in the transfer cart.")
            else:
                st.session_state.transfer_cart.append(cart_item)
                st.success(f"✅ {cart_item['itemname']} added to the cart!")

        # --- cart display ---
        if st.session_state.transfer_cart:
            st.markdown("---")
            st.write("## 🛒 Transfer Cart")

            for idx, cart_item in enumerate(st.session_state.transfer_cart):
                cols = st.columns([4, 2, 2, 1])
                cols[0].write(
                    f"{cart_item['itemname']} (Exp: {cart_item['expirationdate']})"
                )
                cols[1].write(f"Qty: {cart_item['quantity']}")
                cols[2].write(f"Available: {cart_item['available_qty']}")

                if cols[3].button("🗑️", key=f"remove_{idx}"):
                    st.session_state.transfer_cart.pop(idx)
                    st.rerun()

            if st.button("🚚 Transfer All Items"):
                errors = [
                    f"Insufficient quantity for {ci['itemname']} "
                    f"(Available: {ci['available_qty']})."
                    for ci in st.session_state.transfer_cart
                    if ci["quantity"] > ci["available_qty"]
                ]

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    for ci in st.session_state.transfer_cart:
                        shelf_handler.transfer_from_inventory(
                            itemid=ci["itemid"],
                            expirationdate=ci["expirationdate"],
                            quantity=ci["quantity"],
                            cost_per_unit = ci["cost_per_unit"],      # NEW
                            created_by=st.session_state.get("user_email", "Unknown"),
                        )

                    st.success(
                        f"✅ Successfully transferred {len(st.session_state.transfer_cart)} items!"
                    )
                    st.session_state.transfer_cart.clear()
                    st.rerun()


# For manual test
if __name__ == "__main__":
    transfer_tab()
