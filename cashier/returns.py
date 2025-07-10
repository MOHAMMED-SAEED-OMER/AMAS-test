# cashier/returns.py  – POS Return flow (MySQL backend)
import pandas as pd
import streamlit as st

from cashier.cashier_handler import CashierHandler
from auth_utils             import verify_pin
from db_handler             import DatabaseManager

cashier_handler = CashierHandler()
db               = DatabaseManager()

# ───────────────────────── helpers ─────────────────────────
def _get_supervisor_pin_hashes() -> list[str]:
    df = db.fetch_data(
        """
        SELECT pin_hash
        FROM   `users`
        WHERE  role IN ('Admin', 'Supervisor')
          AND  pin_hash IS NOT NULL
        """
    )
    return [h for h in df["pin_hash"].tolist() if h]


def _pin_ok(pin_try: str) -> bool:
    return any(verify_pin(pin_try, h) for h in _get_supervisor_pin_hashes())


def _clear_return_state():
    for k in [
        "return_sale_id",
        "return_sale_details",
        "return_sale_items",
        "full_return_attempt",
        "pending_return",
        "pin_error",
    ]:
        st.session_state.pop(k, None)
    st.rerun()

# ───────────────────────── main tab ─────────────────────────
def display_return_tab() -> None:
    ss = st.session_state
    st.subheader("🔄 Return Sales Bill")

    # 0️⃣ PIN-confirmation page ───────────────────────────────
    if "pending_return" in ss:
        pending = ss.pending_return

        # Pretty list of items being returned
        name_map = {}
        if "return_sale_items" in ss:
            name_map = {
                int(r["itemid"]): (
                    r.get("itemname")
                    or r.get("itemnameenglish")
                    or f"Item {r['itemid']}"
                )
                for _, r in ss.return_sale_items.iterrows()
            }

        details_df = pd.DataFrame(
            [
                {
                    "Item":      name_map.get(it["itemid"], f"ID {it['itemid']}"),
                    "Quantity":  abs(int(it["quantity"])),
                    "Unit Price": f"{it['sellingprice']:.2f}",
                    "Line Total": f"{abs(it['quantity']*it['sellingprice']):.2f}",
                }
                for it in pending["items"]
            ]
        )

        st.info(
            f"### Confirm **{pending['mode']}** "
            f"for original Sale ID **{pending['orig_id']}**"
        )
        st.dataframe(details_df, use_container_width=True, hide_index=True)

        # PIN entry & buttons
        pin = st.text_input("Supervisor / Admin PIN", type="password")
        if ss.get("pin_error"):
            st.error("❌ PIN invalid")

        col_ok, col_cancel = st.columns(2)

        if col_ok.button("✅ Confirm return", key="pin_ok_btn"):
            if pin and _pin_ok(pin):
                # ---------- NEW: use process_sale_with_shortage -----------
                res = cashier_handler.process_sale_with_shortage(
                    cart_items=pending["items"],
                    discount_rate=pending["disc_rate"],
                    payment_method="Return",
                    cashier=ss.get("user_email", "Unknown"),
                    notes=pending["note"]
                          + f" | Original Sale {pending['orig_id']}",
                )
                if res:
                    new_id, _ = res     # ignore shortages for returns
                    st.success(f"Return processed. New Sale ID {new_id}")
                else:
                    st.error("Database error – return not saved.")
                _clear_return_state()
            else:
                ss["pin_error"] = True
                st.rerun()

        if col_cancel.button("❌ Cancel", key="pin_cancel_btn"):
            _clear_return_state()
        return

    # 1️⃣ Search original sale
    sale_id_input = st.text_input("Enter Sale ID to return")
    if st.button("Search"):
        if sale_id_input.strip():
            sd, si = cashier_handler.get_sale_details(sale_id_input.strip())
            if sd.empty:
                st.error(f"Sale ID {sale_id_input} not found.")
            else:
                ss.return_sale_id      = int(sale_id_input.strip())
                ss.return_sale_details = sd
                ss.return_sale_items   = si
                ss.full_return_attempt = False
                st.rerun()
        else:
            st.warning("Enter a Sale ID.")
        return

    if "return_sale_id" not in ss:
        return  # nothing loaded yet

    # 2️⃣ Show bill
    sale_items_df = ss.return_sale_items.copy()
    st.dataframe(ss.return_sale_details, use_container_width=True)
    st.dataframe(sale_items_df,        use_container_width=True)

    # Already-returned quantities
    ret_df = cashier_handler.fetch_data(
        """
        SELECT  itemid,
                SUM(ABS(quantity)) AS returned_qty
        FROM    `salesitems`
        WHERE   saleid IN (
                 SELECT saleid FROM `sales`
                 WHERE  original_saleid = %s
               )
        GROUP BY itemid
        """,
        (ss.return_sale_id,),
    )
    already_map = (
        ret_df.set_index("itemid")["returned_qty"].to_dict() if not ret_df.empty else {}
    )

    st.markdown("---")

    # 3️⃣ Entire-bill return
    if st.button("Return entire remaining amount"):
        cart_items, details, partial = [], [], False
        for _, row in sale_items_df.iterrows():
            sold    = int(row["quantity"])
            itemid  = int(row["itemid"])
            already = int(already_map.get(itemid, 0))
            allowed = max(sold - already, 0)
            name    = (
                row.get("itemname")
                or row.get("itemnameenglish")
                or "Item"
            )
            details.append((name, sold, already, allowed))
            if already:
                partial = True
            if allowed:
                cart_items.append(
                    {
                        "itemid": itemid,
                        "quantity": -allowed,
                        "sellingprice": float(row["unitprice"]),
                    }
                )

        if not cart_items:
            st.error("This bill was fully returned already.")
            return

        if partial and not ss.get("full_return_attempt"):
            st.warning(
                "Some items were already returned – press again to confirm "
                "the remaining items."
            )
            st.dataframe(
                pd.DataFrame(
                    details, columns=["Item", "Sold", "Returned", "Allowed"]
                ),
                use_container_width=True,
            )
            ss.full_return_attempt = True
            st.stop()

        ss.pending_return = dict(
            mode="ENTIRE-BILL return",
            orig_id=ss.return_sale_id,
            items=cart_items,
            disc_rate=float(
                ss.return_sale_details.iloc[0].get("discountrate", 0.0)
            ),
            note=f"Entire return for Sale ID {ss.return_sale_id}",
        )
        st.rerun()

    # 4️⃣ Partial return UI
    st.markdown("#### Partial Return")
    return_rows = []
    for idx, row in sale_items_df.iterrows():
        sold     = int(row["quantity"])
        itemid   = int(row["itemid"])
        already  = int(already_map.get(itemid, 0))
        allowed  = max(sold - already, 0)
        name     = (
            row.get("itemname")
            or row.get("itemnameenglish")
            or "Item"
        )

        c1, c2, c3, _ = st.columns([3, 2, 2, 1])
        c1.write(f"{name}  \n＊Sold {sold} / Max {allowed}")
        chk = c2.checkbox("Return", key=f"ret_chk_{idx}")
        qty = c3.number_input(
            "",
            0,
            allowed,
            allowed,
            1,
            key=f"ret_qty_{idx}"
        )
        return_rows.append((chk, qty, itemid, row["unitprice"]))

    if st.button("Return selected items"):
        cart_items = [
            {
                "itemid": iid,
                "quantity": -q,
                "sellingprice": float(price),
            }
            for chk, q, iid, price in return_rows
            if chk and q > 0
        ]
        if not cart_items:
            st.error("No items selected.")
        else:
            ss.pending_return = dict(
                mode="PARTIAL return",
                orig_id=ss.return_sale_id,
                items=cart_items,
                disc_rate=float(
                    ss.return_sale_details.iloc[0].get("discountrate", 0.0)
                ),
                note=f"Partial return for Sale ID {ss.return_sale_id}",
            )
            st.rerun()


# run direct
if __name__ == "__main__":
    display_return_tab()
