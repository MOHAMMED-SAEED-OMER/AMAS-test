# cashier/pos.py
import streamlit as st
import pandas as pd
from cashier.cashier_handler import CashierHandler
from functools import lru_cache

cashier_handler = CashierHandler()

# ───────────────────────── catalogue & helpers ─────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def get_item_catalogue() -> pd.DataFrame:
    """
    One table with every barcode + multipliers.
    """
    q = """
        SELECT itemid,
               itemnameenglish               AS itemname,
               sellingprice,
               COALESCE(barcode,'')          AS barcode,
               COALESCE(packetbarcode,'')    AS packetbarcode,
               COALESCE(cartonbarcode,'')    AS cartonbarcode,
               packetsize,
               cartonsize
        FROM item;
    """
    return cashier_handler.fetch_data(q)


def build_lookup(cat_df: pd.DataFrame):
    """
    Return two dicts:
      • barcode → row-index
      • lowercase name series for fuzzy search
    """
    idx = {}
    for i, row in cat_df.iterrows():
        for col in ("barcode", "packetbarcode", "cartonbarcode"):
            code = row[col]
            if code:                # skip blanks
                idx[code] = i
    return idx, cat_df.itemname.str.lower()


def resolve_scan(cat_df: pd.DataFrame, row, scanned: str):
    """
    Determine multiplier & user-facing label based on which barcode matched.
    """
    if scanned == row.packetbarcode:
        return row.packetsize or 1, "(packet)"
    if scanned == row.cartonbarcode:
        return row.cartonsize or 1, "(carton)"
    return 1, ""                       # unit barcode or name search


def fetch_item(cat_df, barcode_idx, name_series, key: str, qty_input: int):
    key = key.strip()

    # 1) exact barcode match (unit / packet / carton)
    if key in barcode_idx:
        row = cat_df.loc[barcode_idx[key]]
        multiplier, label = resolve_scan(cat_df, row, key)
    else:
        # 2) partial name search
        match = cat_df[name_series.str.contains(key.lower())]
        if match.empty:
            return None
        row = match.iloc[0]
        multiplier, label = 1, ""

    qty = qty_input * multiplier
    price = float(row.sellingprice or 0.0)

    return {
        "barcode":  key,                          # scanned value
        "itemid":   int(row.itemid),
        "itemname": f"{row.itemname} {label}",
        "quantity": qty,
        "price":    price,
        "total":    price * qty,
    }


def clear_bill():
    st.session_state.sales_table = pd.DataFrame(
        columns=["barcode", "itemid", "itemname", "quantity", "price", "total"]
    )


# ───────────────────────── main POS tab ─────────────────────────
def display_pos_tab():
    st.subheader("💳 Point of Sale")

    cat_df = get_item_catalogue()
    barcode_idx, name_series = build_lookup(cat_df)

    if "sales_table" not in st.session_state:
        clear_bill()

    col_left, col_right = st.columns([0.7, 0.3])

    # --------------- LEFT -----------------
    with col_left:
        st.markdown("### Scan / Add Items")
        with st.form("add_item_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            txt = c1.text_input("Barcode or Item Name")
            qty_input = c2.number_input("Qty", min_value=1, value=1, step=1)

            if st.form_submit_button("➕ Add"):
                item = fetch_item(
                    cat_df, barcode_idx, name_series, txt, int(qty_input)
                )
                if item:
                    st.session_state.sales_table = pd.concat(
                        [st.session_state.sales_table, pd.DataFrame([item])],
                        ignore_index=True,
                    )
                    st.success(f"Added {item['itemname']} (x{item['quantity']})")
                else:
                    st.warning("No matching item found.")

        st.markdown("---")

        # -------- bill fragment --------
        @st.fragment
        def bill_fragment():
            df = st.session_state.sales_table
            if df.empty:
                st.info("Bill is empty.")
                return

            df["total"] = df["quantity"].astype(float) * df["price"].astype(float)
            st.dataframe(
                df[["itemname", "quantity", "price", "total"]],
                use_container_width=True,
                hide_index=True,
            )

            # editable quantities & remove buttons
            for idx, row in df.iterrows():
                cols = st.columns([7, 2, 1])
                cols[0].markdown(f"**{row['itemname']}**")

                new_q = cols[1].number_input(
                    "",
                    min_value=1,
                    value=int(row["quantity"]),
                    step=1,
                    key=f"qty_{idx}",
                    label_visibility="collapsed",
                )
                if new_q != row["quantity"]:
                    df.at[idx, "quantity"] = new_q
                    st.session_state.sales_table = df
                    st.rerun()

                if cols[2].button("🗑️", key=f"rm_{idx}"):
                    st.session_state.sales_table = df.drop(idx).reset_index(drop=True)
                    st.rerun()

        bill_fragment()

    # --------------- RIGHT ----------------
    with col_right:
        df = st.session_state.sales_table
        subtotal = float(df["total"].sum()) if not df.empty else 0.0

        discount_rate = st.number_input(
            "Discount (%)",
            0.0,
            100.0,
            step=0.5,
            value=st.session_state.get("discount_rate", 0.0),
            key="discount_rate",
        )
        disc_amt = round(subtotal * discount_rate / 100, 2)
        final_amt = round(subtotal - disc_amt, 2)

        st.markdown(f"**Subtotal:** {subtotal:.2f}")
        st.markdown(f"**Discount ({discount_rate:.1f}%):** {disc_amt:.2f}")
        st.markdown(f"**Final Amount:** {final_amt:.2f}")

        pay_cols = st.columns(3)
        if pay_cols[0].button("💵 Cash"):
            finalize_sale("Cash", discount_rate, subtotal, disc_amt, final_amt)
        if pay_cols[1].button("💳 Card"):
            finalize_sale("Card", discount_rate, subtotal, disc_amt, final_amt)
        if pay_cols[2].button("❌ Cancel"):
            clear_bill()


# ───────────────────────── sale finaliser ─────────────────────────
def finalize_sale(method, disc_rate, subtotal, disc_amt, final_amt):
    df = st.session_state.sales_table
    if df.empty:
        st.error("Bill is empty.")
        return

    cart_items = [
        {"itemid": int(r.itemid), "quantity": float(r.quantity), "sellingprice": float(r.price)}
        for _, r in df.iterrows()
    ]
    sale_id = cashier_handler.finalize_sale(
        cart_items=cart_items,
        discount_rate=disc_rate,
        payment_method=method,
        cashier=st.session_state.get("user_email", "Unknown"),
        notes=f"POS | Sub {subtotal:.2f} | Disc {disc_amt:.2f} | Final {final_amt:.2f}",
    )
    if sale_id:
        st.success(f"✅ Sale completed! ID {sale_id}")
        clear_bill()
    else:
        st.error("Sale failed.")


if __name__ == "__main__":
    display_pos_tab()
