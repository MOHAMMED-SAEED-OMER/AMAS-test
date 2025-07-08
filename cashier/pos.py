# cashier/pos.py  – Point-of-Sale tab (MySQL backend)
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from cashier.cashier_handler import CashierHandler

cashier_handler = CashierHandler()

# ─────────── catalogue helpers ─────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def get_item_catalogue() -> pd.DataFrame:
    return cashier_handler.fetch_data(
        """
        SELECT  itemid,
                itemnameenglish AS itemname,
                sellingprice,
                COALESCE(barcode,'')        AS barcode,
                COALESCE(packetbarcode,'')  AS packetbarcode,
                COALESCE(cartonbarcode,'')  AS cartonbarcode,
                packetsize,
                cartonsize
        FROM    `item`
        """
    )


def build_lookup(cat_df: pd.DataFrame):
    idx = {}
    for i, row in cat_df.iterrows():
        for c in ("barcode", "packetbarcode", "cartonbarcode"):
            if row[c]:
                idx[row[c]] = i
    return idx, cat_df.itemname.str.lower()


def resolve_scan(row, scanned: str):
    if scanned == row.packetbarcode:
        return row.packetsize or 1, "(packet)"
    if scanned == row.cartonbarcode:
        return row.cartonsize or 1, "(carton)"
    return 1, ""


def fetch_item(cat_df, idx, names, key: str, qty_in: int):
    key = key.strip()
    if key in idx:
        row = cat_df.loc[idx[key]]
        mult, lab = resolve_scan(row, key)
    else:
        m = cat_df[names.str.contains(key.lower())]
        if m.empty:
            return None
        row, mult, lab = m.iloc[0], 1, ""
    qty = qty_in * mult
    price = float(row.sellingprice or 0.0)
    return {
        "barcode": key,
        "itemid": int(row.itemid),
        "itemname": f"{row.itemname} {lab}",
        "quantity": qty,
        "price": price,
        "total": price * qty,
    }


def clear_bill():
    st.session_state.sales_table = pd.DataFrame(
        columns=["barcode", "itemid", "itemname", "quantity", "price", "total"]
    )


# ─────────── POS main tab ──────────────────────────────────────────
def display_pos_tab():
    st.subheader("💳 Point of Sale")

    # ── Held bills list (Resume / Delete) ──────────────────────────
    held = cashier_handler.fetch_data(
        """
        SELECT  holdid,
                hold_label,
                created_at,
                JSON_LENGTH(items) AS line_count   -- safe alias
        FROM    `pos_holds`
        ORDER BY created_at
        """
    )
    if not held.empty:
        st.markdown("### ⏸ Held Bills")
        for r in held.itertuples():
            c1, c2, c3 = st.columns([5, 2, 1])
            c1.write(f"**{r.hold_label}** • {r.line_count} items • {r.created_at:%H:%M}")
            if c2.button("Resume", key=f"resume_{r.holdid}"):
                st.session_state.sales_table = cashier_handler.load_hold(r.holdid)
                cashier_handler.delete_hold(r.holdid)
                st.success(f"Hold “{r.hold_label}” restored.")
                st.rerun()
            if c3.button("✖️", key=f"del_{r.holdid}"):
                cashier_handler.delete_hold(r.holdid)
                st.info("Hold deleted.")
                st.rerun()
        st.markdown("---")

    # ── initialise bill df ─────────────────────────────────────────
    if "sales_table" not in st.session_state:
        clear_bill()

    cat_df = get_item_catalogue()
    bc_idx, name_series = build_lookup(cat_df)

    col_l, col_r = st.columns([0.7, 0.3])

    # ───────── LEFT: scan & bill preview ──────────────────────────
    with col_l:
        st.markdown("### Scan / Add Items")
        with st.form("add_item_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            txt = c1.text_input("Barcode or Item Name")
            qty = c2.number_input("Qty", 1, value=1)
            if st.form_submit_button("➕ Add"):
                itm = fetch_item(cat_df, bc_idx, name_series, txt, int(qty))
                if itm is None:
                    st.warning("No matching item.")
                    return
                st.session_state.sales_table = pd.concat(
                    [st.session_state.sales_table, pd.DataFrame([itm])],
                    ignore_index=True,
                )
                st.success(f"Added {itm['itemname']} ×{itm['quantity']}")

        st.markdown("---")

        @st.fragment
        def bill_fragment():
            df = st.session_state.sales_table
            if df.empty:
                st.info("Bill is empty.")
                return
            df["total"] = df["quantity"] * df["price"]
            st.dataframe(
                df[["itemname", "quantity", "price", "total"]],
                hide_index=True,
                use_container_width=True,
            )
            for idx, row in df.iterrows():
                cols = st.columns([7, 2, 1])
                cols[0].markdown(f"**{row.itemname}**")
                new_q = cols[1].number_input(
                    "",
                    min_value=1,
                    value=int(row.quantity),
                    key=f"qty_{idx}",
                    label_visibility="collapsed",
                )
                if new_q != row.quantity:
                    df.at[idx, "quantity"] = new_q
                    st.session_state.sales_table = df
                    st.rerun()
                if cols[2].button("🗑️", key=f"rm_{idx}"):
                    st.session_state.sales_table = df.drop(idx).reset_index(drop=True)
                    st.rerun()

        bill_fragment()

    # ───────── RIGHT: totals & actions ────────────────────────────
    with col_r:
        df = st.session_state.sales_table
        subtotal = float(df["total"].sum()) if not df.empty else 0.0
        disc_rate = st.number_input(
            "Discount (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            value=st.session_state.get("discount_rate", 0.0),
            key="discount_rate",
        )
        disc_amt = round(subtotal * disc_rate / 100, 2)
        final_amt = round(subtotal - disc_amt, 2)

        st.markdown(f"**Subtotal:** {subtotal:.2f}")
        st.markdown(f"**Discount ({disc_rate:.1f}%):** {disc_amt:.2f}")
        st.markdown(f"**Final Amount:** {final_amt:.2f}")

        btns = st.columns(4)
        if btns[0].button("💵 Cash"):
            finalize_sale("Cash", disc_rate, subtotal, disc_amt, final_amt)
        if btns[1].button("💳 Card"):
            finalize_sale("Card", disc_rate, subtotal, disc_amt, final_amt)
        if btns[2].button("❌ Cancel"):
            clear_bill()

        # F9 hot-key → click Hold
        components.html(
            """
            <script>
              (function () {
                const P = window.parent.document;
                if (P._f9HoldListener) P.removeEventListener('keydown', P._f9HoldListener);
                P._f9HoldListener = function (e) {
                  if (e.code === 'F9') {
                    e.preventDefault();
                    const btn = [...P.querySelectorAll('button')]
                                 .find(b => b.innerText.includes('Hold'));
                    if (btn) btn.click();
                  }
                };
                P.addEventListener('keydown', P._f9HoldListener);
              })();
            </script>
            """,
            height=0,
            width=0,
        )

        if btns[3].button("🕐 Hold (F9)"):
            if df.empty:
                st.warning("Bill is empty.")
            else:
                st.session_state.hold_form = True
                st.rerun()

        if st.session_state.get("hold_form"):
            st.markdown("---")
            st.markdown("#### Label this hold")
            label = st.text_input("Label", key="hold_label")
            col_save, col_cancel = st.columns(2)
            if col_save.button("Save & Clear"):
                hid = cashier_handler.save_hold(
                    cashier_id=st.session_state.get("user_email", "Unknown"),
                    label=label or "Unnamed",
                    df_items=df,
                )
                st.success(f"Held as “{label or 'Unnamed'}” (H{hid})")
                st.session_state.pop("hold_form")
                clear_bill()
                st.rerun()
            if col_cancel.button("Cancel"):
                st.session_state.pop("hold_form")
                st.rerun()


# ─────────── sale finaliser (unchanged) ────────────────────────────
def finalize_sale(method, disc_rate, subtotal, disc_amt, final_amt):
    df = st.session_state.sales_table
    if df.empty:
        st.error("Bill is empty.")
        return
    cart_items = [
        {
            "itemid": int(r.itemid),
            "quantity": int(r.quantity),
            "sellingprice": float(r.price),
        }
        for _, r in df.iterrows()
    ]
    res = cashier_handler.process_sale_with_shortage(
        cart_items=cart_items,
        discount_rate=disc_rate,
        payment_method=method,
        cashier=st.session_state.get("user_email", "Unknown"),
        notes=(
            f"POS | Sub {subtotal:.2f} | Disc {disc_amt:.2f} "
            f"| Final {final_amt:.2f}"
        ),
    )
    if not res:
        st.error("Sale failed.")
        return
    sale_id, shortages = res
    st.success(f"✅ Sale completed! ID {sale_id}")
    for s in shortages:
        st.toast(f"⚠ Shortage: {s['itemname']} (−{s['qty']})", icon="⚠️")
    clear_bill()


if __name__ == "__main__":
    display_pos_tab()
