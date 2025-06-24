# cashier/pos.py  ─────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
from cashier.cashier_handler import CashierHandler

cashier_handler = CashierHandler()

# ───────────────────────── catalogue & helpers ───────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def get_item_catalogue() -> pd.DataFrame:
    return cashier_handler.fetch_data(
        """
        SELECT itemid,
               itemnameenglish AS itemname,
               sellingprice,
               COALESCE(barcode,'')       AS barcode,
               COALESCE(packetbarcode,'') AS packetbarcode,
               COALESCE(cartonbarcode,'') AS cartonbarcode,
               packetsize,
               cartonsize
        FROM item
        """
    )


def build_lookup(cat_df: pd.DataFrame):
    idx = {}
    for i, row in cat_df.iterrows():
        for col in ("barcode", "packetbarcode", "cartonbarcode"):
            code = row[col]
            if code:
                idx[code] = i
    return idx, cat_df.itemname.str.lower()


def resolve_scan(row, scanned: str):
    if scanned == row.packetbarcode:
        return row.packetsize or 1, "(packet)"
    if scanned == row.cartonbarcode:
        return row.cartonsize or 1, "(carton)"
    return 1, ""


def fetch_item(cat_df, barcode_idx, name_series, key: str, qty_input: int):
    key = key.strip()
    if key in barcode_idx:
        row = cat_df.loc[barcode_idx[key]]
        mult, label = resolve_scan(row, key)
    else:
        match = cat_df[name_series.str.contains(key.lower())]
        if match.empty:
            return None
        row, mult, label = match.iloc[0], 1, ""

    qty  = qty_input * mult
    price = float(row.sellingprice or 0.0)
    return {
        "barcode":  key,
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


# ───────────────────────── POS main tab ──────────────────────────────
def display_pos_tab():
    st.subheader("💳 Point of Sale")

    cat_df = get_item_catalogue()
    barcode_idx, name_series = build_lookup(cat_df)

    if "sales_table" not in st.session_state:
        clear_bill()

    col_left, col_right = st.columns([0.7, 0.3])

    # ---------- LEFT: item entry & bill preview ----------------------
    with col_left:
        st.markdown("### Scan / Add Items")
        with st.form("add_item_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            txt       = c1.text_input("Barcode or Item Name")
            qty_input = c2.number_input("Qty", min_value=1, value=1, step=1)

            if st.form_submit_button("➕ Add"):
                item = fetch_item(cat_df, barcode_idx, name_series, txt, int(qty_input))
                if item:
                    st.session_state.sales_table = pd.concat(
                        [st.session_state.sales_table, pd.DataFrame([item])],
                        ignore_index=True,
                    )
                    st.success(f"Added {item['itemname']} ×{item['quantity']}")
                else:
                    st.warning("No matching item found.")

        st.markdown("---")

        @st.fragment
        def bill_fragment():
            df = st.session_state.sales_table
            if df.empty:
                st.info("Bill is empty."); return

            df["total"] = df["quantity"] * df["price"]
            st.dataframe(
                df[["itemname", "quantity", "price", "total"]],
                hide_index=True, use_container_width=True
            )

            # editable quantities + remove
            for idx, row in df.iterrows():
                cols = st.columns([7, 2, 1])
                cols[0].markdown(f"**{row.itemname}**")
                new_q = cols[1].number_input(
                    "", min_value=1, value=int(row.quantity), step=1,
                    key=f"qty_{idx}", label_visibility="collapsed"
                )
                if new_q != row.quantity:
                    df.at[idx, "quantity"] = new_q
                    st.session_state.sales_table = df; st.rerun()
                if cols[2].button("🗑️", key=f"rm_{idx}"):
                    st.session_state.sales_table = df.drop(idx).reset_index(drop=True)
                    st.rerun()

        bill_fragment()

    # ---------- RIGHT: totals & pay buttons --------------------------
    with col_right:
        df = st.session_state.sales_table
        subtotal = float(df["total"].sum()) if not df.empty else 0.0

        disc_rate = st.number_input(
            "Discount (%)", 0.0, 100.0, step=0.5,
            value=st.session_state.get("discount_rate", 0.0),
            key="discount_rate",
        )
        disc_amt  = round(subtotal * disc_rate / 100, 2)
        final_amt = round(subtotal - disc_amt, 2)

        st.markdown(f"**Subtotal:** {subtotal:.2f}")
        st.markdown(f"**Discount ({disc_rate:.1f}%):** {disc_amt:.2f}")
        st.markdown(f"**Final Amount:** {final_amt:.2f}")

        bcols = st.columns(3)
        if bcols[0].button("💵 Cash"):
            finalize_sale("Cash", disc_rate, subtotal, disc_amt, final_amt)
        if bcols[1].button("💳 Card"):
            finalize_sale("Card", disc_rate, subtotal, disc_amt, final_amt)
        if bcols[2].button("❌ Cancel"):
            clear_bill()


# ───────────────────────── sale finaliser ────────────────────────────
def finalize_sale(method: str,
                  disc_rate: float,
                  subtotal: float,
                  disc_amt: float,
                  final_amt: float) -> None:

    df = st.session_state.sales_table
    if df.empty:
        st.error("Bill is empty."); return

    cart_items = [
        {"itemid": int(r.itemid),
         "quantity": int(r.quantity),
         "sellingprice": float(r.price)}
        for _, r in df.iterrows()
    ]

    # NEW: delegate the shortage-aware processing to the handler
    sale_id, shortages = cashier_handler.process_sale_with_shortage(
        cart_items   = cart_items,
        discount_rate= disc_rate,
        payment_method = method,
        cashier = st.session_state.get("user_email", "Unknown"),
        notes   = f"POS | Sub {subtotal:.2f} | Disc {disc_amt:.2f} | Final {final_amt:.2f}"
    )

    if sale_id:
        st.success(f"✅ Sale completed! ID {sale_id}")
        for s in shortages:
            st.toast(f"⚠ Shortage recorded: {s['itemname']} (−{s['qty']})",
                     icon="⚠️")
        clear_bill()
    else:
        st.error("Sale failed.")


if __name__ == "__main__":
    display_pos_tab()
