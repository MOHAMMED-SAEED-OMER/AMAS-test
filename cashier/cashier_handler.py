# cashier/pos.py  – POS front-end (Streamlit)

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from cashier.cashier_handler import CashierHandler


# ---------------------------------------------------------------------------
# Helpers / setup
# ---------------------------------------------------------------------------
def get_handler() -> CashierHandler:
    """Instantiate a CashierHandler using Streamlit secrets."""
    if "cashier_handler" not in st.session_state:
        st.session_state.cashier_handler = CashierHandler(**st.secrets["mysql"])
    return st.session_state.cashier_handler


def _empty_cart_df() -> pd.DataFrame:
    """Return the canonical empty sales_table frame."""
    return pd.DataFrame(
        columns=["itemid", "itemname", "quantity", "price", "total"]
    )


# ---------------------------------------------------------------------------
# Main POS page
# ---------------------------------------------------------------------------
def display_pos_tab() -> None:
    st.title("Point of Sale")

    # ------------------------------------------------------------------
    # Initialise session state
    # ------------------------------------------------------------------
    if "sales_table" not in st.session_state:
        st.session_state.sales_table = _empty_cart_df()

    if "discount_rate" not in st.session_state:
        st.session_state.discount_rate = 0.0

    # ------------------------------------------------------------------
    #  ①  Item entry section
    # ------------------------------------------------------------------
    with st.form("add_item_form"):
        cols = st.columns((4, 2, 2))
        item_id = cols[0].number_input("Item ID", min_value=1, step=1)
        qty     = cols[1].number_input("Qty",     min_value=1, value=1, step=1)
        price   = cols[2].number_input("Price",   min_value=0.0, format="%.2f")
        submitted = st.form_submit_button("Add")

    if submitted:
        # Fake item name lookup for demo purposes
        item_name = f"Item {int(item_id)}"

        new_row_df = pd.DataFrame(
            {
                "itemid": [int(item_id)],
                "itemname": [item_name],
                "quantity": [int(qty)],
                "price": [float(price)],
                "total": [round(qty * price, 2)],
            }
        )

        # Concatenate with existing cart
        st.session_state.sales_table = pd.concat(
            [st.session_state.sales_table, new_row_df], ignore_index=True
        )

        # 🔹 NORMALISE cart (fix for NaN / dtype issues + Pandas FutureWarning)
        tbl = st.session_state.sales_table
        tbl["quantity"] = tbl["quantity"].fillna(1).astype(int)
        tbl["price"]    = tbl["price"].fillna(0.0).astype(float)
        tbl["total"]    = tbl["quantity"] * tbl["price"]
        st.session_state.sales_table = tbl.reset_index(drop=True)

        st.success("Item added!")

    # ------------------------------------------------------------------
    #  ②  Bill fragment (editable cart)
    # ------------------------------------------------------------------
    def bill_fragment() -> None:
        st.subheader("Current Bill")

        subtotal = 0.0
        for idx, row in st.session_state.sales_table.iterrows():
            cols = st.columns((4, 2, 2, 2, 1))

            # Item name
            cols[0].markdown(row.itemname)

            # 🔹 Guard against NaN in quantity
            qty_default = 1 if pd.isna(row.quantity) else int(row.quantity)
            new_q = cols[1].number_input(
                "",
                min_value=1,
                value=qty_default,
                key=f"qty_{idx}",
                label_visibility="collapsed",
            )
            new_price = cols[2].number_input(
                "",
                min_value=0.0,
                value=float(row.price),
                key=f"price_{idx}",
                label_visibility="collapsed",
            )

            # Recalculate line total
            line_total = round(new_q * new_price, 2)
            cols[3].markdown(f"**{line_total:,.2f}**")

            # Remove button
            if cols[4].button("❌", key=f"del_{idx}"):
                st.session_state.sales_table.drop(index=idx, inplace=True)
                st.session_state.sales_table.reset_index(drop=True, inplace=True)
                st.experimental_rerun()

            # Persist edits
            st.session_state.sales_table.at[idx, "quantity"] = new_q
            st.session_state.sales_table.at[idx, "price"] = new_price
            st.session_state.sales_table.at[idx, "total"] = line_total

            subtotal += line_total

        # Summary + discount
        disc_rate = st.number_input(
            "Discount (%)", min_value=0.0, max_value=100.0,
            value=float(st.session_state.discount_rate),
            step=0.5,
        )
        st.session_state.discount_rate = disc_rate
        disc_amt = round(subtotal * disc_rate / 100, 2)
        final_amt = subtotal - disc_amt

        st.markdown(
            f"""
            **Subtotal:** {subtotal:,.2f}  
            **Discount:** {disc_amt:,.2f}  
            **Total:**    {final_amt:,.2f}
            """
        )

        # Action buttons
        btns = st.columns(4)
        if btns[0].button("💵 Cash"):
            finalize_sale("Cash", disc_rate, subtotal, disc_amt, final_amt)
        if btns[1].button("💳 Card"):
            finalize_sale("Card", disc_rate, subtotal, disc_amt, final_amt)
        if btns[2].button("❌ Cancel"):
            st.session_state.sales_table = _empty_cart_df()
            st.success("Bill cleared.")
        if btns[3].button("💾 Hold"):
            hold_label = st.text_input("Label for hold", value=f"Hold {dt.datetime.now():%H:%M}")
            if hold_label:
                handler = get_handler()
                handler.save_hold(
                    cashier_id=st.session_state.get("user_id", "anonymous"),
                    label=hold_label,
                    df_items=st.session_state.sales_table,
                )
                st.session_state.sales_table = _empty_cart_df()
                st.success(f"Bill held as '{hold_label}'")

    bill_fragment()


# ---------------------------------------------------------------------------
# Sale finalisation
# ---------------------------------------------------------------------------
def finalize_sale(
    method: str,
    disc_rate: float,
    subtotal: float,
    disc_amt: float,
    final_amt: float,
) -> None:
    """Commit the bill and show any shelf-shortage warnings."""
    if st.session_state.sales_table.empty:
        st.warning("No items to sell.")
        return

    handler = get_handler()

    saleid, shortages = handler.process_sale_with_shortage(
        cart_items=st.session_state.sales_table.to_dict("records"),
        discount_rate=disc_rate,
        payment_method=method,
        cashier=st.session_state.get("user_id", "anonymous"),
        notes="",
    )

    if saleid is None:
        st.error("Sale could not be completed.")
        return

    st.success(f"Sale #{saleid} completed for {final_amt:,.2f} ({method}).")

    if shortages:
        msg = ", ".join(f"{s['qty']}× {s['itemname']}" for s in shortages)
        st.warning(f"Stock shortage recorded for: {msg}")

    # Reset cart
    st.session_state.sales_table = _empty_cart_df()


# ---------------------------------------------------------------------------
# Entry point for Streamlit
# ---------------------------------------------------------------------------
def main() -> None:
    display_pos_tab()


if __name__ == "__main__":
    main()
