# receive_items/receive_items.py
import streamlit as st
import pandas as pd
from receive_items.receive_handler import ReceiveHandler

rh = ReceiveHandler()


def receive_items():
    """Manual receiving that auto-creates a synthetic PO for cost tracking."""

    st.header("➕ Manual Stock Receipt (creates synthetic PO)")

    # ── 1 : load item & supplier choices ───────────────────────────────
    items_df = rh.fetch_data(
        "SELECT itemid, itemnameenglish FROM item ORDER BY itemnameenglish"
    )
    supp_df = rh.get_suppliers()

    if items_df.empty or supp_df.empty:
        st.warning("Add items and suppliers first.")
        return

    item_lookup = dict(zip(items_df.itemnameenglish, items_df.itemid))
    sel_item_name = st.selectbox("Item", list(item_lookup.keys()))
    sel_item_id   = item_lookup[sel_item_name]

    supp_lookup = dict(zip(supp_df.suppliername, supp_df.supplierid))
    sel_supp_name = st.selectbox("Supplier", list(supp_lookup.keys()))
    sel_supp_id   = supp_lookup[sel_supp_name]

    # ── 2 : receipt details ────────────────────────────────────────────
    qty = st.number_input("Quantity", min_value=1, step=1)
    exp = st.date_input("Expiration Date")
    loc = st.text_input("Storage Location")

    # ── 3 : cost & note ────────────────────────────────────────────────
    cost = st.number_input("Cost per Unit", min_value=0.0, step=0.01, format="%.2f")
    note = st.text_input("Note (optional)")

    if st.button("Receive Item"):
        # 3.1 create synthetic PO header
        poid = rh.create_manual_po(sel_supp_id, "")   # suppliernote left blank

        # 3.2 add PO line
        rh.add_po_item(poid, sel_item_id, qty, cost)

        # 3.3 record cost in poitemcost  → must return costid
        costid = rh.insert_poitem_cost(poid, sel_item_id, cost, qty, note)

        # 3.4 refresh total cost in purchaseorders
        rh.refresh_po_total_cost(poid)

        # 3.5 add to inventory (now includes price_per_unit, poid, costid)
        rh.add_items_to_inventory([{
            "item_id":         sel_item_id,
            "quantity":        qty,
            "expiration_date": exp,
            "storage_location": loc,
            "cost_per_unit":  cost,      # NEW
            "poid":            poid,      # NEW
            "costid":          costid,    # NEW
        }])

        st.success(f"✅ Received {qty} × {sel_item_name}. Synthetic PO #{poid} recorded.")
        st.rerun()


# Stand-alone test
if __name__ == "__main__":
    receive_items()
