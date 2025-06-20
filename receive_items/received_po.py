# receive_items/received_po.py
import streamlit as st
import pandas as pd
import datetime                      # ← NEW
from receive_items.receive_handler import ReceiveHandler

receive_handler = ReceiveHandler()


def received_po_tab():
    st.header("📥 Received Purchase Orders")

    # ------------------------------------------------------------------
    pos_df = receive_handler.get_received_pos()
    if pos_df.empty:
        st.info("ℹ️ No received purchase orders pending inventory entry.")
        return

    poid = st.selectbox(
        "Select Received Purchase Order",
        options=pos_df["poid"],
        format_func=lambda x: f"PO #{x}",
    )

    po_items = receive_handler.get_po_items(poid)
    if po_items.empty:
        st.warning("⚠️ No items found for this PO.")
        return

    # ------------------------------------------------------------------
    st.write("### Enter Received Details")

    # entire input section in a single form
    with st.form("receive_po_form", clear_on_submit=True):
        inventory_entries = []

        for _, itm in po_items.iterrows():
            st.subheader(itm["itemnameenglish"])
            c_qty, c_exp, c_loc, c_cost, c_note = st.columns([1, 1, 1, 1, 2])

           # ---------- originals -----------------------------------------
            orig_qty   = int(itm["orderedquantity"])
            orig_cost  = float(itm.get("estimatedprice") or 0.0)
            sup_exp_dt = pd.to_datetime(itm.get("supexpirationdate")) \
                         if pd.notnull(itm.get("supexpirationdate")) else None
            exp_default = sup_exp_dt.date() if sup_exp_dt else datetime.date.today()

            # ---------- Qty Received ----------
            qty = c_qty.number_input(
                f"Qty Received ({orig_qty})",
                min_value=0,
                value=int(itm["receivedquantity"] or orig_qty),
                key=f"qty_{itm.itemid}",
            )

            # ---------- Expiration ----------
            exp_label = (
                f"Expiration ({sup_exp_dt.date()})" if sup_exp_dt else "Expiration"
            )
            exp_date = c_exp.date_input(
                exp_label,
                value=exp_default,
                key=f"exp_{itm.itemid}",
            )

            # ---------- Location ----------
            loc = c_loc.text_input("Location", key=f"loc_{itm.itemid}")

            # ---------- Cost / Unit ----------
            cost = c_cost.number_input(
                f"Cost/Unit ({orig_cost:.2f})",
                min_value=0.0,
                value=orig_cost,
                step=0.01,
                format="%.2f",
                key=f"cost_{itm.itemid}",
            )


            note = c_note.text_input("Note (optional)", key=f"note_{itm.itemid}")

            inventory_entries.append(
                {
                    "item_id": itm.itemid,
                    "quantity": qty,
                    "expiration_date": exp_date,
                    "storage_location": loc,
                    "cost_per_unit": cost,
                    "note": note,
                }
            )

        submitted = st.form_submit_button("📤 Confirm and Add to Inventory")

    # ------------------------------------------------------------------
    if submitted:
        # 1️⃣ update PO item received quantities
        for ent in inventory_entries:
            receive_handler.update_received_quantity(
                poid, ent["item_id"], ent["quantity"]
            )

        # 2️⃣ create cost rows first (need costid for inventory)
        for ent in inventory_entries:
            if ent["quantity"] > 0 and ent["cost_per_unit"] >= 0:
                costid = receive_handler.insert_poitem_cost(
                    poid,
                    ent["item_id"],
                    ent["cost_per_unit"],
                    ent["quantity"],
                    ent["note"],
                )
                ent["poid"] = poid
                ent["costid"] = costid

        # 3️⃣ insert enriched rows into Inventory
        receive_handler.add_items_to_inventory(inventory_entries)

        # 4️⃣ refresh PO total cost & mark completed
        receive_handler.refresh_po_total_cost(poid)
        receive_handler.mark_po_completed(poid)

        # feedback + rerun to clear PO selector
        st.session_state["recv_success"] = f"✅ PO #{poid} processed!"
        st.rerun()

    # show one‑time success message after rerun
    if "recv_success" in st.session_state:
        st.success(st.session_state.pop("recv_success"))


if __name__ == "__main__":
    received_po_tab()
